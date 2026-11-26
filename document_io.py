"""Shared document helpers: turn uploads into PDF and render preview images."""

import io
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image


def convert_to_pdf(uploaded_file):
    """Convert supported uploads to PDF bytes."""
    filename = uploaded_file.name.lower()
    file_bytes = uploaded_file.getvalue()

    if filename.endswith(".pdf"):
        return file_bytes

    if filename.endswith((".png", ".jpg", ".jpeg")):
        with Image.open(io.BytesIO(file_bytes)) as image:
            image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="PDF")
            return output.getvalue()

    if filename.endswith(".txt"):
        text = file_bytes.decode("utf-8-sig", errors="replace")
        pdf = fitz.open()
        try:
            pdf.new_page(width=595, height=842).insert_textbox(
                fitz.Rect(45, 45, 550, 795),
                text,
                fontsize=10,
                fontname="helv",
                lineheight=1.4,
            )
            return pdf.tobytes(garbage=4, deflate=True)
        finally:
            pdf.close()

    office_extensions = (".docx", ".doc", ".pptx", ".ppt")

    if filename.endswith(office_extensions):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / Path(uploaded_file.name).name
            input_path.write_bytes(file_bytes)

            subprocess.run(
                [
                    "libreoffice",
                    "-env:UserInstallation=file://"
                    + str(Path(temp_dir) / "lo_profile"),
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    temp_dir,
                    str(input_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )

            output_path = input_path.with_suffix(".pdf")

            if not output_path.exists():
                raise ValueError("Office file conversion failed.")

            return output_path.read_bytes()

    raise ValueError(
        "Unsupported file type. Upload PDF, PNG, JPG, JPEG, TXT, "
        "DOC, DOCX, PPT, or PPTX."
    )


def render_pdf_page(pdf_bytes, page_number, zoom=1.35):
    """Render a PDF page to PNG for an in-app preview."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        if document.page_count == 0:
            raise ValueError("The generated PDF contains no pages.")
        page_number = max(0, min(page_number, document.page_count - 1))
        pixmap = document[page_number].get_pixmap(
            matrix=fitz.Matrix(zoom, zoom),
            alpha=False,
        )
        return pixmap.tobytes("png")
