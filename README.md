# Cornell Notes Maker

A bilingual (Arabic/English) Streamlit app that turns university lecture files into
AI-explained Cornell study notes (A4 PDF) and offers an AI lecture assistant powered
by Google Gemini.

## Features

- **AI Cornell Notes (A4 portrait):** Gemini explains every slide in Arabic. Each slide
  becomes a study unit: explanation and key points on the left, the original slide
  (kept as vector content) on the right with a review question, and a summary below.
  One or two slides per sheet; long explanations continue on the next page, never cut.
- **AI Lecture Assistant:** Arabic explanation, high-yield points, and practice MCQs
  for the whole lecture, downloadable as Markdown.
- Live preview before download.
- Uploads: PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG, TXT (Office files are converted
  with LibreOffice; the original file is never modified).

## Adding a template

Create a module in `note_templates/` exposing
`build_pdf(source_pdf_bytes, page_notes, pages_per_sheet=1, lecture_title="")` and
register it in `note_templates/__init__.py`. The app lists every registered template.

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Streamlit interface |
| `document_io.py` | Upload → PDF conversion, preview rendering |
| `note_templates/` | PDF templates; `__init__.py` registers them, `ai_cornell.py` is the current one |
| `ai_assistant.py` | Gemini calls: per-slide analysis and the lecture assistant |
| `assets/fonts/` | Almarai (SIL OFL), one font for Arabic and English text |
| `tests/` | Automated tests (see below) |

## Setup

Requires Python 3.12+ and, for Word/PowerPoint uploads, LibreOffice
(`libreoffice` on the PATH).

    python -m venv .venv
    .venv/bin/pip install -r requirements.txt

Provide a Gemini API key either as the environment variable `GEMINI_API_KEY` or in
`.streamlit/secrets.toml` (git-ignored):

    GEMINI_API_KEY = "your-key"

Run:

    .venv/bin/streamlit run app.py

### Docker

    docker build -t cornell-notes-maker .
    docker run --rm -p 8501:8501 -e PORT=8501 -e GEMINI_API_KEY=your-key cornell-notes-maker

## Tests

    .venv/bin/python -m unittest discover -s tests -t .

The suite runs offline: Gemini is replaced by a fake client.

- `test_ai_cornell_template.py` checks the layout rules, including that long
  explanations are never clipped or dropped. After changing the design, run
  `python tests/render_samples.py` and review the PNGs in `tests/output/`.
- Tests marked `expectedFailure` document known bugs that are scheduled to be fixed.
- `tests/fixtures/sample_lecture.pdf` is synthetic (rebuild with
  `python tests/make_fixtures.py`). Real lectures for manual checks go in
  `tests/fixtures/private/`, which is git-ignored.
