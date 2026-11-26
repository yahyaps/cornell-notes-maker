cd /home/yahya/cornell_notes_mvp

cat > README.md <<'EOF'
# Cornell Notes Maker

A bilingual Arabic/English Streamlit application that converts lecture documents into organized Cornell-style PDF notes with a live preview.

## Features

- Two selectable Cornell note templates.
- Choose between one or two source pages per output sheet.
- Live PDF preview that updates when the uploaded file or layout settings change.
- Download the same PDF displayed in the preview.
- Supports PDF, DOC, DOCX, PPT, PPTX, PNG, JPG, JPEG, and TXT files.
- Converts Microsoft Word and PowerPoint documents to PDF using LibreOffice.
- Supports Arabic and English interface languages.
- Preserves the original uploaded file without modifying it.
- Exports US Letter pages (8.5 x 11 inches).

## Technology Stack

- Python 3.12
- Streamlit
- PyMuPDF
- Pillow
- LibreOffice Writer and Impress

## Requirements

- Python 3.12 or a compatible version.
- Python packages listed in requirements.txt.
- LibreOffice Writer and Impress for Office document conversion.
- Docker (recommended).

## Run with Docker

Build the image:

    docker build -t cornell-notes-maker .

Start the application:

    docker run --rm -p 8501:8501 -e PORT=8501 cornell-notes-maker

Open http://localhost:8501 in your browser.

## Run Locally

Install dependencies:

    python -m pip install -r requirements.txt

For Word and PowerPoint conversion, install LibreOffice and ensure the `libreoffice` command is available.

Run the application:

    streamlit run app.py

## How to Use

1. Upload a lecture file.
2. Choose one of the two Cornell templates.
3. Select one or two source pages per output sheet.
4. Review the live preview.
5. Adjust the template or page layout as needed.
6. Download the generated Cornell PDF.

## Notes and Limitations

- Source pages are scaled to fit the available content area in the selected Cornell template.
- Dense slides or documents may require one source page per sheet for improved readability.
- Cue and summary areas are available for handwritten study notes.
- Office document conversion may vary depending on formatting and available fonts.
- Review the preview before printing.
EOF

Template 2 update

Replace these two files in ~/cornell_notes_mvp:
- app.py
- educational_pdf.py

Back up your current files first. Keep ai_assistant.py unchanged.
Template 1 processing remains in the same branch; Template 2 calls analyze_pages only after the user presses Create AI Lecture Notes.
