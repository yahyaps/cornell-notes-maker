# Cornell Notes Maker

A bilingual (Arabic/English) Streamlit app that turns university lectures into
AI-explained Cornell study notes (A4 PDF) and offers an AI lecture assistant,
powered by Google Gemini.

## Features

- **AI Cornell Notes (A4 portrait).** Gemini explains every slide in Arabic. Each
  slide becomes a study unit: explanation and key points on the left; on the right,
  the original slide (kept as vector content), a review question and a summary.
  One or two slides per sheet. Long explanations continue on the next page and are
  never cut; a slide whose analysis fails keeps its place and can be retried alone.
- **AI Lecture Assistant.** A full study report (Arabic explanation, high-yield
  points, mind-map plans, MCQs) and a chat that answers from the lecture with page
  citations.
- **Built for long lectures.** Slides are analyzed in parallel with retries and a
  live progress bar (a 38-slide lecture takes about 1.5–2 minutes).
- **Correct Arabic + English text.** One bundled font for both scripts; English
  terms, numbers and units keep their order inside Arabic sentences; PDF text is
  selectable and searchable.
- Uploads: PDF, PPTX/PPT, DOCX/DOC, PNG/JPG, TXT (Office files are converted with
  LibreOffice; the original file is never modified).

## Project layout

| Path | Purpose |
|---|---|
| `app.py` | Streamlit interface |
| `ui_text.py` | Interface text in Arabic and English |
| `ai_assistant.py` | Gemini calls: per-slide analysis, study report, chat; retries and error kinds |
| `document_io.py` | Upload → PDF conversion and validation, preview rendering |
| `note_templates/` | PDF templates; `__init__.py` registers them, `ai_cornell.py` is the current one |
| `usage_limits.py` | Rate limits, daily budget, optional access code |
| `static/fonts/` | Almarai (SIL Open Font License) for the PDF and the interface |
| `static/previews/` | Template thumbnails (`scripts/make_template_previews.py`) |
| `.streamlit/config.toml` | Production settings and theme (no secrets) |
| `tests/` | Automated tests |

## Adding a template

1. Create a module in `note_templates/` exposing
   `build_pdf(source_pdf_bytes, page_notes, pages_per_sheet=1, lecture_title="")`.
2. Register it in `note_templates/__init__.py`; the app lists every registered template.
3. Run `python scripts/make_template_previews.py` to create its thumbnail.

## Run locally

Requires Python 3.12+ and, for Word/PowerPoint uploads, LibreOffice
(`libreoffice` on the PATH).

    python -m venv .venv
    .venv/bin/pip install -r requirements.txt

Put the Gemini key in `.streamlit/secrets.toml` (git-ignored; keep it readable
only by you: `chmod 600 .streamlit/secrets.toml`):

    GEMINI_API_KEY = "your-key"

Then:

    .venv/bin/streamlit run app.py

## Deploy (Render)

The repository includes a `Dockerfile` and a `render.yaml` Blueprint.

1. Check the image builds: `docker build -t cornell-notes-maker .`
2. In Render, create the service from the Blueprint (or a Docker web service).
3. In the service's **Environment** settings, add `GEMINI_API_KEY`. Never commit it.
4. Optional: set `APP_ACCESS_CODE` to require a code before AI features are used.

Plan: the free plan sleeps when idle; use at least **Starter**. In our
measurements one server stays around 250–350 MB while handling a 38-slide
lecture; choose **Standard** (2 GB) for many simultaneous users.

### Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | — | Required. Gemini API key |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Model name |
| `GEMINI_SLIDE_WORKERS` | 8 | Slides analyzed at once for one lecture |
| `GEMINI_MAX_CONCURRENT` | 12 | Gemini requests in flight across all users |
| `AI_RUNS_PER_HOUR` | 10 | AI jobs per visitor per hour |
| `CHAT_MESSAGES_PER_HOUR` | 60 | Chat questions per visitor per hour |
| `DAILY_SLIDE_BUDGET` | 3000 | Slides analyzed per day, all users |
| `MAX_AI_SLIDES` | 150 | Largest lecture accepted |
| `APP_ACCESS_CODE` | — | If set, required before using AI |

## Security

- The API key lives only in the host's environment (or the local, git-ignored
  `secrets.toml`). It is never sent to the browser, never logged (logs are
  redacted), and never passed to LibreOffice (which runs with a minimal
  environment because Streamlit copies secrets into `os.environ`).
- Visitors never see tracebacks (`showErrorDetails = "none"`); unexpected errors
  show a reference code that matches a server log line.
- Abuse limits protect the key's quota: per-visitor hourly limits (keyed on the
  address Render's proxy appends to `X-Forwarded-For`), a daily slide budget, a
  server-wide concurrency cap and an optional access code with attempt limiting.
- Uploads are capped at 50 MB; encrypted, corrupt and oversized-image files are
  rejected; the container runs as a non-root user.
- In Google AI Studio / Cloud Console, restrict the key to the Generative Language
  API and set a budget alert. **Rotate the key** if it is ever exposed.

## Tests

    .venv/bin/python -m unittest discover -s tests -t .

The suite runs offline (Gemini is mocked) and covers the template layout rules
(no clipped or lost text), Arabic/English text handling, the parallel analysis
with retries, usage limits, and the full interface through Streamlit's AppTest.

- After changing the design, run `python tests/render_samples.py` and review the
  PNGs in `tests/output/`.
- `tests/fixtures/sample_lecture.pdf` is synthetic (`python tests/make_fixtures.py`).
  Real lectures for manual checks go in `tests/fixtures/private/` (git-ignored).
