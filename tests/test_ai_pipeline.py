"""AI analysis in ai_assistant.py: per-slide notes and the lecture assistant.

Gemini is replaced by FakeGemini, so these tests cost nothing and run offline.
Retry back-off sleeps are patched out.
"""

import json
import re
import unittest
from unittest import mock

import pymupdf
from google.genai import errors as genai_errors

import ai_assistant
from ai_assistant import AIError
from tests.helpers import SAMPLE_PDF, FakeGemini

# The synthetic lecture's slide headings identify which page a prompt is for.
HEADINGS = {
    "Bioethics: Core Principles": 1,
    "Informed Consent\n": 2,
    "Pharmacokinetics (ADME)": 3,
}


def page_of(contents):
    slide_text = contents[0].split("Extracted slide text:", 1)[1].strip()
    for heading, page in HEADINGS.items():
        if slide_text.startswith(heading.strip()):
            return page
    return 4  # the Arabic page


def slide_json(page):
    return json.dumps({
        "title": f"Slide {page}",
        "explanation_ar": f"شرح الشريحة {page} مع مصطلح (Informed Consent).",
        "key_points": [f"Point {page}.1", f"Point {page}.2"],
        "review_question_ar": f"سؤال الشريحة {page}؟",
        "summary_ar": f"خلاصة الشريحة {page}.",
    }, ensure_ascii=False)


def by_page(contents):
    return slide_json(page_of(contents))


def server_error(code=503):
    return genai_errors.ServerError(code, {"error": {"code": code, "message": "overloaded",
                                                     "status": "UNAVAILABLE"}})


def client_error(code, message, status):
    return genai_errors.ClientError(code, {"error": {"code": code, "message": message,
                                                     "status": status}})


def make_text_pdf(pages, chars_per_page):
    doc = pymupdf.open()
    for number in range(1, pages + 1):
        body = f"Page {number} marker. " + ("lorem ipsum " * (chars_per_page // 12))
        doc.new_page().insert_textbox(pymupdf.Rect(20, 20, 575, 820), body, fontsize=5)
    data = doc.tobytes()
    doc.close()
    return data


class PatchedGeminiTest(unittest.TestCase):
    def setUp(self):
        sleep = mock.patch.object(ai_assistant.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.source = SAMPLE_PDF.read_bytes()

    def analyze(self, responses, **kwargs):
        fake = FakeGemini(responses)
        with mock.patch.object(ai_assistant, "get_gemini_client", return_value=fake):
            return ai_assistant.analyze_pages(self.source, **kwargs), fake


class AnalyzePagesTest(PatchedGeminiTest):
    def test_every_page_is_analyzed_in_order_in_parallel(self):
        notes, fake = self.analyze(by_page, workers=4)
        self.assertEqual([n["source_page"] for n in notes], [1, 2, 3, 4])
        self.assertEqual([n["title"] for n in notes], [f"Slide {n}" for n in (1, 2, 3, 4)])
        self.assertEqual(len(fake.calls), 4)

    def test_markdown_fences_are_tolerated(self):
        notes, _ = self.analyze(["```json\n" + slide_json(1) + "\n```"], max_pages=1)
        self.assertEqual(notes[0]["title"], "Slide 1")

    def test_slide_image_and_structured_config_are_sent(self):
        notes, fake = self.analyze(by_page, max_pages=1)
        call = fake.calls[0]
        self.assertEqual(len(call["contents"]), 2)
        self.assertEqual(call["contents"][1].inline_data.mime_type, "image/jpeg")
        self.assertEqual(call["config"].response_mime_type, "application/json")
        self.assertEqual(notes[0]["review_question_ar"], "سؤال الشريحة 1؟")
        self.assertEqual(notes[0]["summary_ar"], "خلاصة الشريحة 1.")
        self.assertNotIn("_image_bytes", notes[0])

    def test_missing_optional_fields_become_empty(self):
        minimal = json.dumps({"title": "T", "explanation_ar": "شرح", "key_points": []})
        notes, _ = self.analyze([minimal], max_pages=1)
        self.assertEqual(notes[0]["review_question_ar"], "")
        self.assertEqual(notes[0]["summary_ar"], "")

    def test_transient_errors_are_retried(self):
        attempts = {"n": 0}

        def flaky(contents):
            attempts["n"] += 1
            return server_error() if attempts["n"] < 3 else slide_json(1)

        notes, fake = self.analyze(flaky, max_pages=1)
        self.assertEqual(notes[0]["title"], "Slide 1")
        self.assertEqual(len(fake.calls), 3)

    def test_a_failing_page_is_kept_and_marked(self):
        def page_two_fails(contents):
            return "not json" if page_of(contents) == 2 else by_page(contents)

        notes, fake = self.analyze(page_two_fails, workers=2)
        self.assertEqual([n["source_page"] for n in notes], [1, 2, 3, 4])
        self.assertEqual(notes[1]["error"], "bad_response")
        self.assertNotIn("error", notes[0])
        page_two_calls = [c for c in fake.calls if page_of(c["contents"]) == 2]
        self.assertEqual(len(page_two_calls), ai_assistant.MAX_ATTEMPTS)

    def test_quota_exhaustion_marks_page_after_retries(self):
        quota = client_error(429, "Resource exhausted", "RESOURCE_EXHAUSTED")
        notes, _ = self.analyze([quota], max_pages=1)
        self.assertEqual(notes[0]["error"], "quota")

    def test_invalid_key_stops_the_whole_run(self):
        bad_key = client_error(400, "API key not valid. Please pass a valid API key.",
                               "INVALID_ARGUMENT")
        with self.assertRaises(AIError) as ctx:
            self.analyze([bad_key], workers=1)
        self.assertEqual(ctx.exception.kind, "invalid_key")

    def test_retry_only_selected_pages(self):
        notes, fake = self.analyze(by_page, pages=[3, 1])
        self.assertEqual([n["source_page"] for n in notes], [1, 3])
        self.assertEqual(len(fake.calls), 2)

    def test_rejects_pages_outside_document(self):
        with self.assertRaises(ValueError):
            self.analyze(by_page, pages=[9])

    def test_progress_reports_each_page(self):
        seen = []
        self.analyze(by_page, progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(seen, [(1, 4), (2, 4), (3, 4), (4, 4)])

    def test_redaction_happens_before_truncation(self):
        key = "AIzaTESTKEY1234567890"
        with mock.patch.dict(ai_assistant.os.environ, {"GEMINI_API_KEY": key}):
            text = "x" * 290 + key
            self.assertNotIn("AIzaTEST", ai_assistant.redact(text, limit=300))

    def test_api_key_is_redacted_from_logs(self):
        key = "AIzaTESTKEY1234567890"
        leaking = server_error()
        leaking.message = f"failure for key {key}"
        with mock.patch.dict(ai_assistant.os.environ, {"GEMINI_API_KEY": key}), \
                self.assertLogs(ai_assistant.logger, "WARNING") as logs:
            self.analyze([leaking, slide_json(1)], max_pages=1)
        self.assertTrue(logs.output)
        self.assertFalse(any(key in line for line in logs.output))


class ClassifyErrorTest(unittest.TestCase):
    def test_kinds(self):
        cases = [
            (server_error(503), "unavailable"),
            (client_error(429, "Quota", "RESOURCE_EXHAUSTED"), "quota"),
            (client_error(400, "API key not valid.", "INVALID_ARGUMENT"), "invalid_key"),
            (client_error(403, "Permission denied", "PERMISSION_DENIED"), "invalid_key"),
            (client_error(404, "model not found", "NOT_FOUND"), "invalid_model"),
            (TimeoutError(), "timeout"),
            (AIError("too_long", "x"), "too_long"),
            (RuntimeError("boom"), "unknown"),
        ]
        for exc, kind in cases:
            with self.subTest(exc=exc):
                self.assertEqual(ai_assistant.classify_error(exc), kind)


class MissingKeyTest(unittest.TestCase):
    def test_missing_key_is_reported_clearly(self):
        # Patch secrets first: loading real secrets copies them into os.environ.
        with mock.patch("streamlit.secrets") as secrets, \
                mock.patch.dict(ai_assistant.os.environ, {}, clear=True):
            secrets.get.return_value = None
            with self.assertRaises(AIError) as ctx:
                ai_assistant.get_gemini_client()
        self.assertEqual(ctx.exception.kind, "missing_key")


class AnalyzeLectureTest(PatchedGeminiTest):
    def run_lecture(self, pdf, responses, **kwargs):
        fake = FakeGemini(responses)
        with mock.patch.object(ai_assistant, "get_gemini_client", return_value=fake):
            return ai_assistant.analyze_lecture(pdf, **kwargs), fake

    def test_question_count_bounds(self):
        for bad in (4, 21):
            with self.subTest(question_count=bad), self.assertRaises(ValueError):
                ai_assistant.analyze_lecture(self.source, question_count=bad)

    def test_returns_model_text(self):
        result, fake = self.run_lecture(self.source, ["# 1. Lecture Overview\n..."],
                                        question_count=5)
        self.assertTrue(result.startswith("# 1."))
        self.assertIn("exactly 5 MCQs", fake.calls[0]["contents"])

    def test_long_lecture_reaches_the_model_in_full(self):
        pdf = make_text_pdf(pages=40, chars_per_page=2500)
        _, fake = self.run_lecture(pdf, ["ok"], question_count=5)
        prompt = fake.calls[0]["contents"]
        self.assertEqual(re.findall(r"SOURCE PAGE (\d+)", prompt)[-1], "40")

    def test_oversized_lecture_is_rejected_not_cut(self):
        pdf = make_text_pdf(pages=3, chars_per_page=2500)
        with mock.patch.object(ai_assistant, "MAX_INPUT_CHARS", 1000), \
                self.assertRaises(AIError) as ctx:
            self.run_lecture(pdf, ["ok"], question_count=5)
        self.assertEqual(ctx.exception.kind, "too_long")

    def test_transient_error_is_retried(self):
        result, fake = self.run_lecture(self.source, [server_error(), "report"],
                                        question_count=5)
        self.assertEqual(result, "report")
        self.assertEqual(len(fake.calls), 2)


if __name__ == "__main__":
    unittest.main()
