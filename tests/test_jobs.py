"""Background slide-analysis jobs (jobs.py)."""

import json
import threading
import time
import unittest
from unittest import mock

import pymupdf
from google.genai import errors as genai_errors

import ai_assistant
import jobs
from tests.helpers import FakeGemini


def lecture(pages):
    doc = pymupdf.open()
    for number in range(1, pages + 1):
        doc.new_page().insert_text((72, 72), f"Slide {number} heading", fontsize=20)
    data = doc.tobytes()
    doc.close()
    return data


def answer(contents):
    return json.dumps({"title": "T", "explanation_ar": "شرح", "key_points": [],
                       "review_question_ar": "", "summary_ar": ""})


def wait_until(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class JobTest(unittest.TestCase):
    def run_job(self, fake, pages, **kwargs):
        patcher = mock.patch.object(ai_assistant, "get_gemini_client", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return jobs.start_job(lecture(pages), "sig-" + str(id(fake)), range(1, pages + 1),
                              **kwargs)

    def test_runs_in_background_and_finishes(self):
        job = self.run_job(FakeGemini(answer), 6, workers=3)
        self.assertTrue(wait_until(lambda: not job.running))
        self.assertEqual(job.status, "done")
        self.assertEqual(job.done, 6)
        self.assertEqual(job.failed, 0)
        self.assertEqual(job.in_flight, [])
        self.assertEqual([n["source_page"] for n in job.notes], list(range(1, 7)))
        self.assertIsNone(job.eta())

    def test_cancel_stops_remaining_api_calls(self):
        release = threading.Event()

        def slow(contents):
            release.wait(5)   # hold every request until the test releases them
            return answer(contents)

        fake = FakeGemini(slow)
        job = self.run_job(fake, 20, workers=2)
        self.assertTrue(wait_until(lambda: len(fake.calls) == 2))
        job.cancel()
        release.set()
        self.assertTrue(wait_until(lambda: not job.running))
        self.assertEqual(job.status, "cancelled")
        self.assertEqual(len(fake.calls), 2, "no request may start after Cancel")
        kinds = [n.get("error") for n in job.notes]
        self.assertEqual(kinds[:2], [None, None], "in-flight results are kept")
        self.assertEqual(set(kinds[2:]), {"cancelled"})
        self.assertEqual(job.failed, 0, "cancelled slides are not failures")

    def test_cancel_interrupts_retry_wait(self):
        overloaded = genai_errors.ServerError(503, {"error": {"code": 503, "message": "x",
                                                               "status": "UNAVAILABLE"}})
        job = self.run_job(FakeGemini([overloaded]), 1, workers=1)
        self.assertTrue(wait_until(lambda: len(job.notes or []) == 0 and job.running))
        time.sleep(0.2)          # now in the back-off wait (2+ seconds)
        started = time.monotonic()
        job.cancel()
        self.assertTrue(wait_until(lambda: not job.running, timeout=2))
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(job.notes[0]["error"], "cancelled")

    def test_fatal_error_marks_job_failed(self):
        bad_key = genai_errors.ClientError(400, {"error": {
            "code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}})
        job = self.run_job(FakeGemini([bad_key]), 3, workers=1)
        self.assertTrue(wait_until(lambda: not job.running))
        self.assertEqual((job.status, job.error_kind), ("failed", "invalid_key"))

    def test_server_wide_job_limit(self):
        release = threading.Event()

        def slow(contents):
            release.wait(5)
            return answer(contents)

        with mock.patch.object(jobs, "MAX_ACTIVE_JOBS", 1):
            first = self.run_job(FakeGemini(slow), 2, workers=1)
            with self.assertRaises(jobs.ServerBusy):
                self.run_job(FakeGemini(answer), 2)
            release.set()
            self.assertTrue(wait_until(lambda: not first.running))
            # The slot frees up once the first job ends.
            second = self.run_job(FakeGemini(answer), 2)
            self.assertTrue(wait_until(lambda: not second.running))


if __name__ == "__main__":
    unittest.main()
