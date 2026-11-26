"""Usage limits that protect the Gemini quota."""

import os
import unittest
from datetime import date
from unittest import mock

import usage_limits
from usage_limits import LimitExceeded, UsageLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class UsageLimiterTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.day = date(2026, 11, 26)
        self.limiter = UsageLimiter(clock=self.clock, today=lambda: self.day)

    def test_hourly_job_limit_per_visitor(self):
        with mock.patch.object(usage_limits, "AI_RUNS_PER_HOUR", 2):
            self.limiter.start_ai_job("a")
            self.limiter.start_ai_job("a")
            with self.assertRaises(LimitExceeded) as ctx:
                self.limiter.start_ai_job("a")
            self.assertEqual(ctx.exception.kind, "rate")
            self.assertGreater(ctx.exception.retry_after, 0)
            self.limiter.start_ai_job("b")   # other visitors unaffected
            self.clock.now += 3601
            self.limiter.start_ai_job("a")   # window has passed

    def test_zero_disables_action(self):
        with mock.patch.object(usage_limits, "CHAT_MESSAGES_PER_HOUR", 0):
            with self.assertRaises(LimitExceeded):
                self.limiter.chat_message("a")

    def test_daily_slide_budget_and_refund(self):
        with mock.patch.object(usage_limits, "DAILY_SLIDE_BUDGET", 100):
            self.limiter.start_ai_job("a", slides=80)
            with self.assertRaises(LimitExceeded) as ctx:
                self.limiter.start_ai_job("b", slides=30)
            self.assertEqual(ctx.exception.kind, "daily")
            self.limiter.refund_slides(80)
            self.limiter.start_ai_job("b", slides=30)
            self.day = date(2026, 11, 27)
            self.limiter.start_ai_job("c", slides=100)   # new day, new budget

    def test_too_many_slides(self):
        with mock.patch.object(usage_limits, "MAX_AI_SLIDES", 10), \
                self.assertRaises(LimitExceeded) as ctx:
            self.limiter.start_ai_job("a", slides=11)
        self.assertEqual(ctx.exception.kind, "too_many_slides")

    def test_access_attempts_are_limited(self):
        for _ in range(usage_limits.ACCESS_ATTEMPTS_PER_HOUR):
            self.limiter.access_attempt("a")
        with self.assertRaises(LimitExceeded):
            self.limiter.access_attempt("a")


class VisitorAndAccessTest(unittest.TestCase):
    def context(self, forwarded=None, ip="10.0.0.1"):
        headers = {"X-Forwarded-For": forwarded} if forwarded else {}
        return type("Ctx", (), {"headers": headers, "ip_address": ip})()

    def test_uses_last_forwarded_address(self):
        ctx = self.context("6.6.6.6, 203.0.113.9")   # first entry is client-supplied
        self.assertEqual(usage_limits.visitor_id(ctx), "203.0.113.9")

    def test_falls_back_to_ip(self):
        self.assertEqual(usage_limits.visitor_id(self.context()), "10.0.0.1")

    def test_access_code(self):
        with mock.patch.dict(os.environ, {"APP_ACCESS_CODE": "s3cret"}):
            self.assertTrue(usage_limits.access_code_required())
            self.assertTrue(usage_limits.access_code_ok("s3cret"))
            self.assertFalse(usage_limits.access_code_ok("nope"))
            self.assertFalse(usage_limits.access_code_ok(None))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(usage_limits.access_code_required())


if __name__ == "__main__":
    unittest.main()
