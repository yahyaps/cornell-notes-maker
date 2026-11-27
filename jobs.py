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

# Lectures analyzed at once across the whole server. Measured on 2026-11-27
# with two real 70-slide lectures analyzed together: the server peaked at
# 509 MB, at the free plan's 512 MB limit. One at a time peaked at ~378 MB,
# so further lectures wait in a queue and start automatically.
MAX_ACTIVE_JOBS = int(os.environ.get("MAX_ACTIVE_JOBS", "1"))
# Waiting lectures beyond this are refused with "try again shortly".
MAX_QUEUED_JOBS = int(os.environ.get("MAX_QUEUED_JOBS", "5"))

_jobs_lock = threading.Lock()
_running = []     # jobs currently analyzing
_queue = []       # jobs waiting for a free slot, oldest first


class ServerBusy(Exception):
    """Raised when the waiting queue is already full."""


@dataclass
class SlideJob:
    sig: str                      # file signature the job belongs to
    pages: list                   # 1-based pages to analyze
    pdf_bytes: bytes = field(default=b"", repr=False)
    retry: bool = False           # True when re-running failed slides only
    workers: int = 0
    status: str = "queued"        # queued, running, done, cancelled, failed
    done: int = 0
    failed: int = 0
    in_flight: list = field(default_factory=list)
    notes: list = None            # analyze_pages() result once finished
    error_kind: str = ""          # AIError kind when status == "failed"
    error_ref: str = ""           # log reference for unexpected errors
    started: float = 0.0          # when analysis began (after any wait)
    finished: float = 0.0
    consumed: bool = False        # results merged into the session's notes
    cancel_event: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total(self):
        return len(self.pages)

    @property
    def running(self):
        """True until the job ends (queued or analyzing)."""
        return self.status in ("queued", "running")

    @property
    def queued(self):
        return self.status == "queued"

    def queue_position(self):
        """1 = next to start; None when not waiting."""
        with _jobs_lock:
            return _queue.index(self) + 1 if self in _queue else None

    def elapsed(self):
        if not self.started:
            return 0.0
        return (self.finished or time.monotonic()) - self.started

    def eta(self):
        """Seconds left, estimated from the pace so far (None until known)."""
        with self._lock:
            done, total = self.done, self.total
        if self.status != "running" or done == 0 or done >= total:
            return None
        return self.elapsed() / done * (total - done)

    def snapshot(self):
        with self._lock:
            return {"status": self.status, "done": self.done, "total": self.total,
                    "failed": self.failed, "in_flight": sorted(self.in_flight)}

    def cancel(self):
        """Stop the job. A waiting job leaves the queue and ends at once."""
        self.cancel_event.set()
        with _jobs_lock:
            if self in _queue:
                _queue.remove(self)
                self._end_unstarted()

    # Internals ------------------------------------------------------------
    def _end_unstarted(self):
        with self._lock:
            self.notes = [ai_assistant.failed_note(n, "cancelled") for n in self.pages]
            self.status = "cancelled"
            self.started = self.finished = time.monotonic()
        self.pdf_bytes = b""

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

    def _run(self):
        try:
            notes = ai_assistant.analyze_pages(
                self.pdf_bytes, pages=self.pages, cancel=self.cancel_event,
                on_slide_start=self._on_start, on_slide_done=self._on_done,
                workers=self.workers or ai_assistant.SLIDE_WORKERS,
            )
            with self._lock:
                self.notes = notes
                self.status = "cancelled" if self.cancel_event.is_set() else "done"
        except AIError as exc:
            with self._lock:
                self.status, self.error_kind = "failed", exc.kind
        except Exception as exc:  # noqa: BLE001 - shown to the visitor as a reference
            ref = uuid.uuid4().hex[:8]
            logger.error("Slide analysis job crashed [ref %s]: %s", ref,
                         ai_assistant.redact(repr(exc), 1000))
            with self._lock:
                self.status, self.error_kind, self.error_ref = "failed", "unknown", ref
        finally:
            self.finished = time.monotonic()
            with self._lock:
                self.in_flight.clear()
            self.pdf_bytes = b""   # the session keeps its own copy
            logger.info("Job %s: %s, %d/%d slides in %.0fs", self.sig[:8], self.status,
                        self.done, self.total, self.elapsed())
            _finished(self)


def _launch(job):
    """Start a job's thread. Call with _jobs_lock held."""
    job.status, job.started = "running", time.monotonic()
    _running.append(job)
    threading.Thread(target=job._run, name=f"slides-{job.sig[:8]}", daemon=True).start()


def _finished(job):
    with _jobs_lock:
        if job in _running:
            _running.remove(job)
        while _queue and len(_running) < MAX_ACTIVE_JOBS:
            _launch(_queue.pop(0))


def start_job(pdf_bytes, sig, pages, retry=False, workers=None):
    """Analyze `pages` of the lecture on a background thread.

    Starts at once when a slot is free, otherwise waits in a queue (status
    "queued", see queue_position()) and starts automatically. Raises
    ServerBusy when MAX_QUEUED_JOBS lectures are already waiting.
    """
    job = SlideJob(sig=sig, pages=list(pages), pdf_bytes=pdf_bytes, retry=retry,
                   workers=workers or 0)
    with _jobs_lock:
        if len(_running) < MAX_ACTIVE_JOBS:
            _launch(job)
        elif len(_queue) < MAX_QUEUED_JOBS:
            _queue.append(job)
            logger.info("Job %s queued at position %d", sig[:8], len(_queue))
        else:
            raise ServerBusy()
    return job
