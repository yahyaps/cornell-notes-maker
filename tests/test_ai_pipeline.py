"""AI analysis (ai_assistant.py) and the Template 2 PDF (educational_pdf.py).

Gemini is replaced by FakeGemini, so these tests cost nothing and run offline.
Tests marked expectedFailure document known bugs scheduled for a later phase;
when a fix lands, the marker must be removed.
"""

import json
import unittest
from unittest import mock

import pymupdf

import ai_assistant
from educational_pdf import make_ai_lecture_notes_pdf
from tests.helpers import SAMPLE_PDF, FakeGemini

A4 = (595.28, 841.89)


def slide_json(page):
    return json.dumps({
        "title": f"Slide {page}",
        "explanation_ar": f"شرح الشريحة {page} مع مصطلح (Informed Consent).",
        "key_points": [f"Point {page}.1", f"Point {page}.2"],
    }, ensure_ascii=False)


def make_text_pdf(pages, chars_per_page):
    doc = pymupdf.open()
    for number in range(1, pages + 1):
        body = f"Page {number} marker. " + ("lorem ipsum " * (chars_per_page // 12))
        doc.new_page().insert_textbox(pymupdf.Rect(20, 20, 575, 820), body, fontsize=5)
    data = doc.tobytes()
    doc.close()
    return data


class AnalyzePagesTest(unittest.TestCase):
    def setUp(self):
        self.source = SAMPLE_PDF.read_bytes()

    def run_with(self, responses):
        fake = FakeGemini(responses)
        with mock.patch.object(ai_assistant, "get_gemini_client", return_value=fake):
            return ai_assistant.analyze_pages(self.source), fake

    def test_every_page_is_analyzed_in_order(self):
        notes, fake = self.run_with([slide_json(n) for n in range(1, 5)])
        self.assertEqual([n["source_page"] for n in notes], [1, 2, 3, 4])
        self.assertEqual(len(fake.calls), 4)
        self.assertEqual(notes[2]["key_points"], ["Point 3.1", "Point 3.2"])

    def test_markdown_fences_are_tolerated(self):
        fenced = "```json\n" + slide_json(1) + "\n```"
        notes, _ = self.run_with([fenced])
        self.assertEqual(notes[0]["title"], "Slide 1")

    def test_invalid_json_names_the_failing_page(self):
        with self.assertRaisesRegex(RuntimeError, "source page 2"):
            self.run_with([slide_json(1), "not json"])

    def test_slide_image_is_sent_with_prompt(self):
        _, fake = self.run_with([slide_json(1)])
        parts = fake.calls[0]["contents"]
        self.assertEqual(len(parts), 2)


class AnalyzeLectureTest(unittest.TestCase):
    def test_question_count_bounds(self):
        for bad in (4, 21):
            with self.subTest(question_count=bad), self.assertRaises(ValueError):
                ai_assistant.analyze_lecture(SAMPLE_PDF.read_bytes(), question_count=bad)

    def test_returns_model_text(self):
        fake = FakeGemini(["# 1. Lecture Overview\n..."])
        with mock.patch.object(ai_assistant, "get_gemini_client", return_value=fake):
            result = ai_assistant.analyze_lecture(SAMPLE_PDF.read_bytes(), question_count=5)
        self.assertTrue(result.startswith("# 1."))
        self.assertIn("exactly 5 MCQs", fake.calls[0]["contents"])

    @unittest.expectedFailure  # Known bug: input is cut at MAX_INPUT_CHARS (Phase 2).
    def test_long_lecture_reaches_the_model_in_full(self):
        pdf = make_text_pdf(pages=40, chars_per_page=2500)
        fake = FakeGemini(["ok"])
        with mock.patch.object(ai_assistant, "get_gemini_client", return_value=fake):
            ai_assistant.analyze_lecture(pdf, question_count=5)
        self.assertIn("SOURCE PAGE 40", fake.calls[0]["contents"])


class AiLectureNotesPdfTest(unittest.TestCase):
    def setUp(self):
        self.source = SAMPLE_PDF.read_bytes()
        self.notes = [json.loads(slide_json(n)) | {"source_page": n} for n in range(1, 5)]

    def test_a4_portrait_and_page_count(self):
        for pps, expected in ((1, 4), (2, 2)):
            with self.subTest(pages_per_sheet=pps):
                out = make_ai_lecture_notes_pdf(self.source, self.notes, pages_per_sheet=pps)
                with pymupdf.open(stream=out, filetype="pdf") as doc:
                    self.assertEqual(doc.page_count, expected)
                    self.assertAlmostEqual(doc[0].rect.width, A4[0], places=1)
                    self.assertAlmostEqual(doc[0].rect.height, A4[1], places=1)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            make_ai_lecture_notes_pdf(self.source, [], pages_per_sheet=1)
        with self.assertRaises(ValueError):
            make_ai_lecture_notes_pdf(self.source, self.notes, pages_per_sheet=3)
        with self.assertRaises(ValueError):
            make_ai_lecture_notes_pdf(self.source, [{"source_page": 9}], pages_per_sheet=1)


if __name__ == "__main__":
    unittest.main()
