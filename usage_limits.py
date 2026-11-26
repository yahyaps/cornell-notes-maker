"""Limits on AI usage, so a public deployment cannot drain the Gemini quota.

All limits are per server process and reset when it restarts. Configure with
environment variables:

    AI_RUNS_PER_HOUR      AI jobs (notes or assistant report) per visitor/hour   (10)
    CHAT_MESSAGES_PER_HOUR assistant chat questions per visitor/hour            (60)
    DAILY_SLIDE_BUDGET    slides analyzed per day across all visitors          (3000)
    MAX_AI_SLIDES         slides allowed in one lecture                        (150)
    APP_ACCESS_CODE       if set, visitors must enter this code to use AI
"""

import hmac
import os
import threading
import time
from collections import defaultdict, deque
from datetime import date


def _int_env(name, default):
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


AI_RUNS_PER_HOUR = _int_env("AI_RUNS_PER_HOUR", 10)
CHAT_MESSAGES_PER_HOUR = _int_env("CHAT_MESSAGES_PER_HOUR", 60)
DAILY_SLIDE_BUDGET = _int_env("DAILY_SLIDE_BUDGET", 3000)
MAX_AI_SLIDES = _int_env("MAX_AI_SLIDES", 150)
ACCESS_ATTEMPTS_PER_HOUR = 10   # wrong access codes allowed per visitor
SUPPORT_TICKETS_PER_HOUR = 5    # support tickets per visitor

WINDOW_SECONDS = 3600


class LimitExceeded(Exception):
    """Raised when a request would exceed a limit.

    kind: "rate" (per visitor), "daily" (server budget) or "too_many_slides".
    retry_after: seconds until a per-visitor slot frees up (rate only).
    """

    def __init__(self, kind, retry_after=0):
        super().__init__(kind)
        self.kind = kind
        self.retry_after = retry_after


class UsageLimiter:
    def __init__(self, clock=time.monotonic, today=date.today):
        self._clock = clock
        self._today = today
        self._lock = threading.Lock()
        self._events = defaultdict(deque)   # (visitor, action) -> timestamps
        self._budget_day = None
        self._slides_today = 0

    def _check_rate(self, visitor, action, per_hour):
        now = self._clock()
        events = self._events[(visitor, action)]
        while events and now - events[0] >= WINDOW_SECONDS:
            events.popleft()
        if len(events) >= per_hour:
            # per_hour == 0 disables the action entirely (no event to wait for).
            wait = WINDOW_SECONDS - (now - events[0]) if events else WINDOW_SECONDS
            raise LimitExceeded("rate", int(wait) + 1)
        return events, now

    def start_ai_job(self, visitor, slides=0):
        """Reserve one AI job for `visitor` that will analyze `slides` slides."""
        if slides > MAX_AI_SLIDES:
            raise LimitExceeded("too_many_slides")
        with self._lock:
            events, now = self._check_rate(visitor, "job", AI_RUNS_PER_HOUR)
            if self._budget_day != self._today():
                self._budget_day, self._slides_today = self._today(), 0
            if self._slides_today + slides > DAILY_SLIDE_BUDGET:
                raise LimitExceeded("daily")
            self._slides_today += slides
            events.append(now)

    def refund_slides(self, slides):
        """Give back budget for slides that were never sent (e.g. a fatal error)."""
        with self._lock:
            self._slides_today = max(0, self._slides_today - slides)

    def access_attempt(self, visitor):
        """Count an access-code attempt; slows down guessing."""
        with self._lock:
            events, now = self._check_rate(visitor, "access", ACCESS_ATTEMPTS_PER_HOUR)
            events.append(now)

    def support_ticket(self, visitor):
        with self._lock:
            events, now = self._check_rate(visitor, "support", SUPPORT_TICKETS_PER_HOUR)
            events.append(now)

    def chat_message(self, visitor):
        with self._lock:
            events, now = self._check_rate(visitor, "chat", CHAT_MESSAGES_PER_HOUR)
            events.append(now)


limiter = UsageLimiter()


def visitor_id(context):
    """Best-effort visitor identity from a Streamlit `st.context`.

    Behind Render's proxy the real client address is the last entry its load
    balancer appended to X-Forwarded-For; earlier entries can be forged by the
    client, so they are ignored.
    """
    forwarded = ""
    try:
        forwarded = context.headers.get("X-Forwarded-For", "") or ""
    except Exception:  # noqa: BLE001 - headers unavailable outside a request
        pass
    if forwarded.strip():
        return forwarded.split(",")[-1].strip()
    return getattr(context, "ip_address", None) or "unknown"


def access_code_required():
    return bool(os.environ.get("APP_ACCESS_CODE"))


def access_code_ok(entered):
    expected = os.environ.get("APP_ACCESS_CODE", "")
    if not expected:
        return True
    return hmac.compare_digest(str(entered or "").encode(), expected.encode())
