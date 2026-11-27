"""One lock for every PyMuPDF call in this process.

PyMuPDF is not thread-safe, even across separate Document objects: MuPDF
keeps process-wide state (font caches, error stack). The app touches it from
several threads at once: each visitor's script thread, and the background
analysis job rendering slide images. Unserialized, two PDF builds running
together produced a text measurement of 0 pt (a box then "did not fit"),
seen in a concurrent test on 2026-11-27.

Hold LOCK (re-entrant) around anything that opens, renders, measures or
writes a PDF. Keep slow non-MuPDF work (network, LibreOffice) outside it.
"""

import functools
import threading

LOCK = threading.RLock()


def serialized(func):
    """Decorator: run `func` while holding the PyMuPDF lock."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with LOCK:
            return func(*args, **kwargs)
    return wrapper


class open_document:
    """Context manager: open and close a PyMuPDF document under the lock, but
    leave the body unlocked, for long-lived documents that are only touched
    in short, separately locked calls (e.g. one slide at a time)."""

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.document = None

    def __enter__(self):
        import pymupdf
        with LOCK:
            self.document = pymupdf.open(*self.args, **self.kwargs)
        return self.document

    def __exit__(self, *exc):
        with LOCK:
            self.document.close()
        return False
