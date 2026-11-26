"""Upload conversion and preview rendering shared by every template."""

import io
import shutil
import unittest

import pymupdf
from PIL import Image

from tests.helpers import SAMPLE_PDF, FakeUpload
from document_io import convert_to_pdf, render_pdf_page


def page_count(pdf_bytes):
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


class ConvertToPdfTest(unittest.TestCase):
    def test_pdf_passes_through_unchanged(self):
        data = SAMPLE_PDF.read_bytes()
        self.assertEqual(convert_to_pdf(FakeUpload("Lecture.PDF", data)), data)

    def test_image_becomes_single_page_pdf(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (800, 450), (40, 90, 160, 255)).save(buffer, format="PNG")
        pdf = convert_to_pdf(FakeUpload("slide.png", buffer.getvalue()))
        self.assertEqual(page_count(pdf), 1)

    def test_text_file_keeps_its_text(self):
        pdf = convert_to_pdf(FakeUpload("notes.txt", "Pharmacokinetics notes\nADME".encode()))
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:
            self.assertIn("Pharmacokinetics", doc[0].get_text())

    def test_unsupported_type_is_rejected(self):
        with self.assertRaises(ValueError):
            convert_to_pdf(FakeUpload("archive.zip", b"PK"))

    @unittest.skipUnless(shutil.which("libreoffice"), "LibreOffice not installed")
    def test_office_document_converts(self):
        # A minimal DOCX is built by LibreOffice itself from plain text.
        import subprocess
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp) / "doc.txt"
            txt.write_text("Informed consent")
            subprocess.run(["libreoffice", "--headless", "--convert-to", "docx",
                            "--outdir", tmp, str(txt)], check=True, capture_output=True, timeout=120)
            docx = (Path(tmp) / "doc.docx").read_bytes()
        self.assertGreaterEqual(page_count(convert_to_pdf(FakeUpload("doc.docx", docx))), 1)


class RenderPreviewTest(unittest.TestCase):
    def test_returns_png_and_clamps_page_number(self):
        data = SAMPLE_PDF.read_bytes()
        for requested in (0, 3, 99, -5):
            with self.subTest(page=requested):
                png = render_pdf_page(data, requested)
                self.assertTrue(png.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
