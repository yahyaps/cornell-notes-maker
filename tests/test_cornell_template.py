"""Template 1 (Cornell) must render pixel-identical to the approved design.

Golden images were generated from the original app.py code before it was
moved into note_templates/cornell.py. To accept an intentional design change:

    UPDATE_GOLDEN=1 python -m unittest tests.test_cornell_template
"""

import io
import itertools
import os
import unittest

import pymupdf
from PIL import Image, ImageChops

from tests.helpers import GOLDEN, OUTPUT, SAMPLE_PDF
from note_templates.cornell import PAGE_H, PAGE_W, build_pdf

# Anti-aliasing can differ slightly between machines; anything beyond this
# share of visibly changed pixels is a real layout change.
MAX_CHANGED_PIXEL_RATIO = 0.0005
VISIBLE_DIFF = 16


def render_pages(pdf_bytes):
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return [
            Image.open(io.BytesIO(
                page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False).tobytes("png")
            )).convert("RGB")
            for page in doc
        ]


def changed_ratio(a, b):
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > VISIBLE_DIFF else 0)
    return diff.histogram()[255] / (a.width * a.height)


class CornellTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SAMPLE_PDF.read_bytes()

    def test_matches_golden_images(self):
        update = os.environ.get("UPDATE_GOLDEN") == "1"
        for pps, hide, crop in itertools.product((1, 2), (False, True), (False, True)):
            with self.subTest(pages_per_sheet=pps, hide_notes=hide, crop_whitespace=crop):
                out = build_pdf(self.source, "Template 1", pages_per_sheet=pps,
                                crop_whitespace=crop, hide_notes=hide)
                for number, image in enumerate(render_pages(out), start=1):
                    name = f"t1_pps{pps}_hide{int(hide)}_crop{int(crop)}_p{number}.png"
                    golden_path = GOLDEN / name
                    if update:
                        image.save(golden_path)
                        continue
                    self.assertTrue(golden_path.exists(), f"missing golden image {name}")
                    golden = Image.open(golden_path).convert("RGB")
                    self.assertEqual(image.size, golden.size, name)
                    ratio = changed_ratio(image, golden)
                    if ratio > MAX_CHANGED_PIXEL_RATIO:
                        OUTPUT.mkdir(exist_ok=True)
                        image.save(OUTPUT / name)
                    self.assertLessEqual(
                        ratio, MAX_CHANGED_PIXEL_RATIO,
                        f"{name} differs from golden ({ratio:.4%}); actual saved to tests/output/",
                    )

    def test_page_count_and_size(self):
        for pps, expected in ((1, 4), (2, 2)):
            with self.subTest(pages_per_sheet=pps):
                out = build_pdf(self.source, "Template 1", pages_per_sheet=pps)
                with pymupdf.open(stream=out, filetype="pdf") as doc:
                    self.assertEqual(doc.page_count, expected)
                    self.assertAlmostEqual(doc[0].rect.width, PAGE_W)
                    self.assertAlmostEqual(doc[0].rect.height, PAGE_H)

    def test_rejects_invalid_pages_per_sheet(self):
        with self.assertRaises(ValueError):
            build_pdf(self.source, "Template 1", pages_per_sheet=3)


if __name__ == "__main__":
    unittest.main()
