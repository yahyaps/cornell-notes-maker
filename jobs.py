"""Background slide-analysis jobs.

A job runs ai_assistant.analyze_pages() on its own thread, so the Streamlit
script never blocks: tab clicks, language switches and other reruns leave the
job running, and the page polls its state. The job object lives in the
visitor's session state (server-side), and only plain Python happens on the
worker thread; no Streamlit calls.
"""

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field

import ai_assistant
from ai_assistant import AIError

logger = logging.getLogger(__name__)

# Jobs running at once across the whole server. Each holds the lecture PDF
# and a few slide images in memory; on a 512 MB instance two is the safe
# ceiling (see README "Limits on the free plan").
MAX_ACTIVE_JOBS = int(os.environ.get("MAX_ACTIVE_JOBS", "2"))

_active_lock = threading.Lock()
_active = 0


class ServerBusy(Exception):
    """Raised when MAX_ACTIVE_JOBS jobs are already running."""


@dataclass
class SlideJob:
    sig: str                      # file signature the job belongs to
    pages: list                   # 1-based pages to analyze
    retry: bool = False           # True when re-running failed slides only
    status: str = "running"       # running, done, cancelled, failed
    done: int = 0
    failed: int = 0
    in_flight: list = field(default_factory=list)
    notes: list = None            # analyze_pages() result once finished
    error_kind: str = ""          # AIError kind when status == "failed"
    error_ref: str = ""           # log reference for unexpected errors
    started: float = field(default_factory=time.monotonic)
    finished: float = 0.0
    consumed: bool = False        # results merged into the session's notes
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total(self):
        return len(self.pages)

    @property
    def running(self):
        return self.status == "running"

    def elapsed(self):
        return (self.finished or time.monotonic()) - self.started

    def eta(self):
        """Seconds left, estimated from the pace so far (None until known)."""
        with self._lock:
            done, total = self.done, self.total
        if not self.running or done == 0 or done >= total:
            return None
        return self.elapsed() / done * (total - done)

    def snapshot(self):
        with self._lock:
            return {"status": self.status, "done": self.done, "total": self.total,
                    "failed": self.failed, "in_flight": sorted(self.in_flight)}

    def cancel(self):
        self.cancel_event.set()

    # Callbacks from the worker thread ---------------------------------
    def _on_start(self, page):
        with self._lock:
            self.in_flight.append(page)

    def _on_done(self, page, note):
        with self._lock:
            if page in self.in_flight:
                self.in_flight.remove(page)
            self.done += 1
            if note.get("error") and note["error"] != "cancelled":
                self.failed += 1


def start_job(pdf_bytes, sig, pages, retry=False, workers=None):
    """Start analyzing `pages` of the lecture on a background thread.

    Raises ServerBusy when the server already runs MAX_ACTIVE_JOBS jobs.
    """
    global _active
    with _active_lock:
        if _active >= MAX_ACTIVE_JOBS:
            raise ServerBusy()
        _active += 1

    job = SlideJob(sig=sig, pages=list(pages), retry=retry)

    def run():
        global _active
        try:
            notes = ai_assistant.analyze_pages(
                pdf_bytes, pages=job.pages, cancel=job.cancel_event,
                on_slide_start=job._on_start, on_slide_done=job._on_done,
                workers=workers or ai_assistant.SLIDE_WORKERS,
            )
            with job._lock:
                job.notes = notes
                job.status = "cancelled" if job.cancel_event.is_set() else "done"
        except AIError as exc:
            with job._lock:
                job.status, job.error_kind = "failed", exc.kind
        except Exception as exc:  # noqa: BLE001 - shown to the visitor as a reference
            ref = uuid.uuid4().hex[:8]
            logger.error("Slide analysis job crashed [ref %s]: %s", ref,
                         ai_assistant.redact(repr(exc), 1000))
            with job._lock:
                job.status, job.error_kind, job.error_ref = "failed", "unknown", ref
        finally:
            job.finished = time.monotonic()
            with job._lock:
                job.in_flight.clear()
            with _active_lock:
                _active -= 1
            logger.info("Job %s: %s, %d/%d slides in %.0fs", sig[:8], job.status,
                        job.done, job.total, job.elapsed())

    threading.Thread(target=run, name=f"slides-{sig[:8]}", daemon=True).start()
    return job
