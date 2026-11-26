"""The unified AI Cornell template (note_templates/ai_cornell.py).

Rendered pages should also be checked by eye after layout changes:
    python tests/render_samples.py   (writes PNGs to tests/output/)
"""

import unittest

import pymupdf

from note_templates import DEFAULT_TEMPLATE, TEMPLATES, ai_cornell
from tests.helpers import SAMPLE_PDF


def note(page, sentences=2, points=2, **extra):
    data = {
        "source_page": page,
        "title": f"Slide {page} title",
        "explanation_ar": " ".join(
            f"الجملة {page}-{i} تشرح الموافقة المستنيرة (Informed Consent) للمريض."
            for i in range(1, sentences + 1)
        ),
        "key_points": [f"النقطة {page}-{i} عن مبدأ (Autonomy)." for i in range(1, points + 1)],
        "review_question_ar": f"ما أهمية الشريحة {page}؟",
        "summary_ar": f"خلاصة الشريحة {page}.",
    }
    data.update(extra)
    return data


def plan(notes, pages_per_sheet):
    """Run the layout planner directly, returning its PagePlans."""
    source = pymupdf.open(SAMPLE_PDF)
    typesetter = ai_cornell.Typesetter()
    try:
        units = [ai_cornell.Unit.from_note(n) for n in notes]
        layout = ai_cornell.Layout(typesetter, source)
        return ai_cornell.Planner(layout).plan(units, pages_per_sheet)
    finally:
        typesetter.close()
        source.close()


class BuildPdfTest(unittest.TestCase):
    def setUp(self):
        self.source = SAMPLE_PDF.read_bytes()
        self.notes = [note(n) for n in range(1, 5)]

    def build(self, notes=None, pages_per_sheet=2, **kwargs):
        out = ai_cornell.build_pdf(self.source, notes or self.notes,
                                   pages_per_sheet=pages_per_sheet, **kwargs)
        return pymupdf.open(stream=out, filetype="pdf")

    def test_a4_portrait(self):
        with self.build() as doc:
            for page in doc:
                self.assertAlmostEqual(page.rect.width, 595.28, places=1)
                self.assertAlmostEqual(page.rect.height, 841.89, places=1)

    def test_two_short_slides_share_a_page(self):
        with self.build(pages_per_sheet=2) as doc:
            self.assertEqual(doc.page_count, 2)
        with self.build(pages_per_sheet=1) as doc:
            self.assertEqual(doc.page_count, 4)

    def test_text_is_real_and_selectable(self):
        with self.build() as doc:
            text = doc[0].get_text()
        self.assertIn("Informed", text)
        self.assertIn("Slide 1 title", text)

    def test_original_slide_is_embedded_as_vector(self):
        # The fixture's slide 1 heading must be findable as text, not pixels.
        with self.build() as doc:
            self.assertTrue(doc[0].search_for("Bioethics: Core Principles"))

    def test_header_shows_lecture_title_and_page_numbers(self):
        with self.build(lecture_title="Bioethics-I") as doc:
            self.assertIn("Bioethics-I", doc[0].get_text())
            self.assertIn("1 / 2", doc[0].get_text())

    def test_optional_fields_may_be_missing(self):
        sparse = [{"source_page": 1, "title": "", "explanation_ar": "", "key_points": []},
                  {"source_page": 2, "explanation_ar": "شرح فقط."}]
        with self.build(sparse) as doc:
            self.assertGreaterEqual(doc.page_count, 1)

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            ai_cornell.build_pdf(self.source, [], pages_per_sheet=1)
        with self.assertRaises(ValueError):
            ai_cornell.build_pdf(self.source, self.notes, pages_per_sheet=3)
        with self.assertRaises(ValueError):
            ai_cornell.build_pdf(self.source, [note(9)], pages_per_sheet=1)


class NoContentLossTest(unittest.TestCase):
    """Long explanations move to more space; nothing is clipped or dropped."""

    def placed(self, plans, page):
        sentences, points = [], []
        for page_plan in plans:
            for unit_plan in page_plan.units:
                if unit_plan.unit.source_page == page:
                    sentences += unit_plan.sentences
                    points += unit_plan.points
        return sentences, points

    def test_long_unit_continues_in_order_without_loss(self):
        long_note = note(2, sentences=60, points=8)
        notes = [note(1), long_note, note(3)]
        for pps in (1, 2):
            with self.subTest(pages_per_sheet=pps):
                plans = plan(notes, pps)
                sentences, points = self.placed(plans, 2)
                self.assertEqual(sentences, ai_cornell.split_sentences(long_note["explanation_ar"]))
                self.assertEqual(points, long_note["key_points"])
                continued = [u for p in plans for u in p.units
                             if u.unit.source_page == 2 and u.unit.continued]
                self.assertTrue(continued, "long unit should continue on another page")
                summaries = [u.unit.summary for p in plans for u in p.units
                             if u.unit.source_page == 2 and u.unit.summary]
                self.assertEqual(summaries, [long_note["summary_ar"]],
                                 "summary appears exactly once, at the end")

    def test_long_unit_renders(self):
        notes = [note(1), note(2, sentences=60, points=8), note(3)]
        out = ai_cornell.build_pdf(SAMPLE_PDF.read_bytes(), notes, pages_per_sheet=2)
        with pymupdf.open(stream=out, filetype="pdf") as doc:
            self.assertGreater(doc.page_count, 2)

    def test_scale_never_below_minimum(self):
        plans = plan([note(n, sentences=12, points=5) for n in range(1, 5)], 2)
        for page_plan in plans:
            for unit_plan in page_plan.units:
                self.assertGreaterEqual(unit_plan.scale, ai_cornell.MIN_SCALE)


class TextDirectionTest(unittest.TestCase):
    def test_direction_rules(self):
        cases = {
            "شرح عربي فقط": "rtl",
            "English only point.": "ltr",
            "تُشير الرسومات إلى Ethics وAccountability وPrinciples وIntegrity": "rtl",
            "(Autonomy) تعني احترام قرار المريض في العلاج": "rtl",
            "Half-life t1/2 = 0.693 x Vd / CL": "ltr",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ai_cornell.text_direction(text), expected)


class RegistryTest(unittest.TestCase):
    def test_default_template_is_registered(self):
        template = TEMPLATES[DEFAULT_TEMPLATE]
        self.assertIs(template.build_pdf, ai_cornell.build_pdf)
        self.assertTrue(template.name_ar and template.name_en)


if __name__ == "__main__":
    unittest.main()
