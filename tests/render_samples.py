"""Render sample pages of every template to tests/output/ for visual review.

    python tests/render_samples.py

Uses the synthetic fixture, plus the real lecture and cached Gemini notes in
tests/fixtures/private/ when they exist (that folder is git-ignored).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from note_templates import TEMPLATES  # noqa: E402
from tests.test_ai_cornell_template import note  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
OUTPUT = ROOT / "tests" / "output"


def samples():
    yield "synthetic", (FIXTURES / "sample_lecture.pdf").read_bytes(), [
        note(1), note(2, sentences=30, points=6), note(3), note(4, sentences=1, points=0),
    ]
    private_pdf = FIXTURES / "private" / "bioethics_lecture.pdf"
    private_notes = FIXTURES / "private" / "bioethics_page_notes.json"
    if private_pdf.exists() and private_notes.exists():
        yield "bioethics", private_pdf.read_bytes(), json.loads(private_notes.read_text())["pages"]


def main():
    OUTPUT.mkdir(exist_ok=True)
    for key, template in TEMPLATES.items():
        for name, source, notes in samples():
            for pps in (1, 2):
                pdf = template.build_pdf(source, notes, pages_per_sheet=pps, lecture_title=name)
                stem = f"{key}_{name}_pps{pps}"
                (OUTPUT / f"{stem}.pdf").write_bytes(pdf)
                with pymupdf.open(stream=pdf, filetype="pdf") as doc:
                    for page in doc:
                        page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).save(
                            OUTPUT / f"{stem}_p{page.number + 1}.png")
                    print(f"{stem}: {doc.page_count} pages")
    print(f"Open {OUTPUT} to review.")


if __name__ == "__main__":
    main()
