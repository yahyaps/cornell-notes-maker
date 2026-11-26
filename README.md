# Cornell Notes Maker

A bilingual (Arabic/English) Streamlit app that turns university lecture files into
study notes: printable Cornell sheets, AI-explained lecture notes, and an AI lecture
assistant powered by Google Gemini.

## Features

- **Template 1 – Cornell notes:** course details, Key Points column, the original
  lecture pages, and a personal notes area. One or two source pages per sheet.
- **Template 2 – AI lecture notes:** Gemini explains every slide in Arabic and lists
  its key points; the PDF places the explanation beside the original slide (A4 portrait).
- **AI Lecture Assistant:** Arabic explanation, high-yield points, and practice MCQs
  for the whole lecture, downloadable as Markdown.
- Live preview before download.
- Uploads: PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG, TXT (Office files are converted
  with LibreOffice; the original file is never modified).

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Streamlit interface |
| `document_io.py` | Upload → PDF conversion, preview rendering |
| `note_templates/cornell.py` | Template 1 PDF layout |
| `educational_pdf.py` | Template 2 PDF layout |
| `ai_assistant.py` | Gemini calls: per-slide analysis and the lecture assistant |
| `tests/` | Automated tests (see below) |

## Setup

Requires Python 3.12+ and, for Word/PowerPoint uploads, LibreOffice
(`libreoffice` on the PATH). Template 2 needs the Noto Sans Arabic and DejaVu Sans fonts.

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

- `test_cornell_template.py` compares Template 1 against approved images in
  `tests/golden/`. After an **intentional** design change, regenerate them with
  `UPDATE_GOLDEN=1` and review the new images before committing.
- Tests marked `expectedFailure` document known bugs that are scheduled to be fixed.
- `tests/fixtures/sample_lecture.pdf` is synthetic (rebuild with
  `python tests/make_fixtures.py`). Real lectures for manual checks go in
  `tests/fixtures/private/`, which is git-ignored.
