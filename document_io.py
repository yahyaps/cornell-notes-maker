"""Shared document helpers: turn uploads into PDF and render preview images."""

import io
import os
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from PIL import Image


# Only these variables reach LibreOffice. Streamlit copies secrets such as
# GEMINI_API_KEY into os.environ, and a converter handling untrusted files
# must never inherit them.
_SAFE_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ")


def _subprocess_env(home_dir):
    env = {key: os.environ[key] for key in _SAFE_ENV_KEYS if key in os.environ}
    env["HOME"] = str(home_dir)
    return env


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
        pdf = pymupdf.open()
        try:
            pdf.new_page(width=595, height=842).insert_textbox(
                pymupdf.Rect(45, 45, 550, 795),
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
                env=_subprocess_env(temp_dir),
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
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        if document.page_count == 0:
            raise ValueError("The generated PDF contains no pages.")
        page_number = max(0, min(page_number, document.page_count - 1))
        pixmap = document[page_number].get_pixmap(
            matrix=pymupdf.Matrix(zoom, zoom),
            alpha=False,
        )
        return pixmap.tobytes("png")


# --------------------------------------------------
# Validated loading for the app
# --------------------------------------------------
# Refuse decompression bombs: images above ~60 megapixels.
Image.MAX_IMAGE_PIXELS = 60_000_000


class DocumentError(Exception):
    """An upload that cannot be used, with a `kind` the interface explains.

    Kinds: unsupported, office_unavailable, conversion_failed, encrypted,
    corrupt, empty, image_too_large.
    """

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


def load_document(uploaded_file):
    """Convert an upload to PDF and validate it. Returns (pdf_bytes, page_count)."""
    try:
        pdf_bytes = convert_to_pdf(uploaded_file)
    except FileNotFoundError as exc:  # libreoffice binary missing
        raise DocumentError("office_unavailable") from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise DocumentError("conversion_failed") from exc
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise DocumentError("image_too_large") from exc
    except ValueError as exc:
        kind = "unsupported" if "Unsupported" in str(exc) else "conversion_failed"
        raise DocumentError(kind) from exc
    except OSError as exc:  # unreadable image data
        raise DocumentError("corrupt") from exc

    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
            if document.needs_pass:
                raise DocumentError("encrypted")
            page_count = document.page_count
    except DocumentError:
        raise
    except Exception as exc:  # noqa: BLE001 - any MuPDF parse failure
        raise DocumentError("corrupt") from exc
    if page_count == 0:
        raise DocumentError("empty")
    return pdf_bytes, page_count
