import io
import hashlib
import streamlit as st
import fitz  # PyMuPDF
from PIL import Image

import os
import subprocess
import tempfile
from pathlib import Path

# --------------------------------------------------
# File conversion helper
# --------------------------------------------------

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



# --------------------------------------------------
# Page configuration
# --------------------------------------------------
st.set_page_config(
    page_title="Cornell Notes Maker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PAGE_W = 8.5 * 72
PAGE_H = 11 * 72


# --------------------------------------------------
# Language support
# --------------------------------------------------
TRANSLATIONS = {
    "en": {
        "title": "Cornell Notes Maker",
        "subtitle": "Turn lecture PDFs into clean Cornell notes.",
        "subtitle2": "Choose one or two source pages per sheet and preview before download.",
        "upload_title": "1. Upload your lecture",
        "upload_help": "Upload your file by dragging and dropping it below, or browse your device.",
        "drop_title": "Drop your file here",
        "drop_description": "Drag your lecture file into the upload area below",
        "drop_hint": "PDF, Word, PowerPoint, images, or TXT • Original file unchanged",
        "browse": "Click Browse files to choose a file",
        "template_title": "2. Choose your template",
        "template_help": "Choose the Cornell layout that suits your study style.",
        "template1": "Template 1 — Cue column + Notes + Summary",
        "template2": "Template 2 — Class / Date / Topic + Main Points + Notes",
        "create_title": "3. Create your notes",
        "create_help": "Your document will contain two vertically stacked elements per page, without writing lines behind them.",
        "create_button": "Create Cornell PDF",
        "download_button": "Download Cornell PDF",
        "select_pdf": "Please upload a file first.",
        "ready": "File ready",
        "creating": "Creating your Cornell PDF...",
        "success": "Your Cornell PDF is ready!",
        "error": "Could not create the PDF",
        "footer": "Cornell Notes Maker • Powered by PyMuPDF",
        "language": "Language",
        "english": "English",
        "arabic": "العربية",
    },
    "ar": {
        "title": "منشئ ملاحظات كورنيل",
        "subtitle": "حوّل ملفات المحاضرات والمستندات إلى ملاحظات كورنيل منظمة.",
        "subtitle2": "اختر صفحة أو صفحتين في كل ورقة، وشاهد المعاينة قبل التنزيل.",
        "upload_title": "١. ارفع ملف المحاضرة",
        "upload_help": "يمكنك سحب الملف (PDF، صور، أو نص) وإفلاته في منطقة الرفع أدناه، أو اختيار الملف من جهازك.",
        "drop_title": "أفلت الملف هنا",
        "drop_description": "اسحب ملف المحاضرة وأفلته داخل مساحة رفع الملف أدناه",
        "drop_hint": "ملفات PDF وWord وPowerPoint والصور وTXT • لن يتم تعديل الملف الأصلي",
        "browse": "أو اضغط على زر اختيار الملفات لتحديد المحاضرة",
        "template_title": "٢. اختر قالب كورنيل",
        "template_help": "اختر تصميم الملاحظات المناسب لطريقة دراستك.",
        "template1": "القالب الأول — عمود الأسئلة + الملاحظات + الملخص",
        "template2": "القالب الثاني — الصف والتاريخ والموضوع + النقاط الرئيسية والملاحظات",
        "create_title": "٣. أنشئ ملف الملاحظات",
        "create_help": "ستحتوي كل صفحة على محتوى مرتب عموديًا، دون خطوط كتابة خلف الشرائح.",
        "create_button": "إنشاء ملف كورنيل PDF",
        "download_button": "تنزيل ملف كورنيل PDF",
        "select_pdf": "يرجى رفع ملف أولًا.",
        "ready": "الملف جاهز",
        "creating": "جارٍ إنشاء ملف كورنيل...",
        "success": "أصبح ملف كورنيل جاهزًا!",
        "error": "تعذّر إنشاء ملف PDF",
        "footer": "منشئ ملاحظات كورنيل • يعمل باستخدام PyMuPDF",
        "language": "اللغة",
        "english": "English",
        "arabic": "العربية",
    },
}

# Keep the selected language when Streamlit reruns the app.
if "language" not in st.session_state:
    st.session_state.language = "en"

language_col, spacer_col = st.columns([1, 4])

with language_col:
    selected_language = st.selectbox(
        "Language / اللغة",
        options=["en", "ar"],
        format_func=lambda value: (
            "English" if value == "en" else "العربية"
        ),
        index=0 if st.session_state.language == "en" else 1,
        key="language_selector",
    )

st.session_state.language = selected_language
lang = TRANSLATIONS[selected_language]
is_arabic = selected_language == "ar"


# --------------------------------------------------
# Bilingual styling and header
# --------------------------------------------------
direction = "rtl" if is_arabic else "ltr"
text_align = "right" if is_arabic else "left"

st.markdown(
    f"""
    <style>
    .block-container {{
        max-width: 1050px;
        padding-top: 1.8rem;
        padding-bottom: 3rem;
    }}

    .hero {{
        direction: {direction};
        text-align: {text_align};
        padding: 2rem;
        border-radius: 20px;
        background: linear-gradient(135deg, #edf2f7, #f8fafc);
        border: 1px solid #dbe3eb;
        margin-bottom: 1.8rem;
    }}

    .hero h1 {{
        color: #243b53;
        margin-bottom: 0.7rem;
        font-size: 2.2rem;
        font-weight: 800;
    }}

    .hero p {{
        color: #526477;
        margin-bottom: 0;
        font-size: 1rem;
        line-height: 1.9;
    }}

    .section-title {{
        direction: {direction};
        text-align: {text_align};
        color: #334e68;
        font-weight: 750;
        font-size: 1.2rem;
        margin: 1.4rem 0 0.5rem 0;
    }}

    div[data-testid="stFileUploader"] {{
        border: 2px dashed #829ab1;
        border-radius: 18px;
        padding: 1.5rem;
        background: rgba(130, 154, 177, 0.08);
        direction: {direction};
    }}

    div[data-testid="stFileUploader"] section {{
        border: none;
        background: transparent;
        min-height: 120px;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button {{
        width: 100%;
        min-height: 3rem;
        border-radius: 10px;
        font-weight: 650;
    }}

    .footer {{
        direction: {direction};
        text-align: center;
        color: #829ab1;
        padding-top: 1rem;
    }}
    </style>

    <div class="hero">
        <h1>📚 {lang["title"]}</h1>
        <p>{lang["subtitle"]}<br>{lang["subtitle2"]}</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------
# PDF drawing helpers
# --------------------------------------------------
def draw_line(page, x1, y1, x2, y2,
              color=(0.75, 0.75, 0.75), width=0.5):
    page.draw_line((x1, y1), (x2, y2), color=color, width=width)


def add_label(page, x, y, text, size=9, font="helv"):
    page.insert_text((x, y), text, fontsize=size, fontname=font)


def get_content_clip(src_page, margin=12):
    """Find text/image block bounds to reduce excessive whitespace on Word pages."""
    blocks = src_page.get_text("blocks")
    rects = []
    for block in blocks:
        if len(block) >= 5:
            x0, y0, x1, y1 = block[:4]
            if x1 > x0 and y1 > y0:
                rects.append(fitz.Rect(x0, y0, x1, y1))
    if not rects:
        return src_page.rect
    clip = rects[0]
    for rect in rects[1:]:
        clip |= rect
    clip = fitz.Rect(
        max(src_page.rect.x0, clip.x0 - margin),
        max(src_page.rect.y0, clip.y0 - margin),
        min(src_page.rect.x1, clip.x1 + margin),
        min(src_page.rect.y1, clip.y1 + margin),
    )
    return clip if not clip.is_empty else src_page.rect


def place_source_page(page, rect, src, source_page_number, crop_whitespace=False):
    source_page = src[source_page_number]
    kwargs = {"keep_proportion": True}
    if crop_whitespace:
        kwargs["clip"] = get_content_clip(source_page)
    page.show_pdf_page(rect, src, source_page_number, **kwargs)


def make_page(out, src, first, second, number, total, template, crop_whitespace=False):
    page = out.new_page(width=PAGE_W, height=PAGE_H)

    if template == "Template 1":
        cue_w = 180
        top = 61
        summary_h = 144
        bottom = PAGE_H - summary_h

        # Cue column
        page.draw_rect(
            fitz.Rect(0, top, cue_w, bottom),
            color=None,
            fill=(0.91, 0.95, 0.88),
        )

        # Notes area outline
        page.draw_rect(
            fitz.Rect(cue_w, top, PAGE_W, bottom),
            color=(0.65, 0.68, 0.65),
            width=0.6,
        )

        # Summary area
        page.draw_rect(
            fitz.Rect(0, bottom, PAGE_W, PAGE_H),
            color=(0.65, 0.68, 0.65),
            fill=(0.98, 0.96, 0.88),
            width=0.6,
        )

        add_label(page, 12, 20, "CORNELL NOTES", 11, "hebo")
        add_label(page, cue_w + 8, top + 17, "NOTE-TAKING AREA", 9, "hebo")
        add_label(page, 12, bottom + 22, "SUMMARY", 10, "hebo")
        add_label(page, PAGE_W - 90, 20, f"Page {number}/{total}", 8)

        page.insert_textbox(
            fitz.Rect(5, 210, cue_w - 5, 390),
            "CUES / QUESTIONS",
            fontsize=12,
            fontname="hebo",
            rotate=90,
            align=1,
        )

        target = fitz.Rect(
            cue_w + 6,
            top + 30,
            PAGE_W - 6,
            bottom - 6,
        )

    else:
        margin = 28
        header_h = 66
        summary_h = 126
        main_w = 150

        # Header
        page.draw_rect(
            fitz.Rect(
                margin, margin,
                PAGE_W - margin, margin + header_h
            ),
            color=(0.55, 0.58, 0.55),
            width=0.6,
        )

        add_label(page, margin + 8, margin + 18, "Class:", 9, "hebo")
        add_label(page, margin + 8, margin + 47, "Topic:", 9, "hebo")
        add_label(page, PAGE_W - 165, margin + 18, "Date:", 9, "hebo")
        add_label(
            page, PAGE_W - 165, margin + 47,
            "Continued from page:", 7
        )

        body_top = margin + header_h + 12
        body_bottom = PAGE_H - margin - summary_h

        # Main Points and Notes columns
        page.draw_rect(
            fitz.Rect(margin, body_top, margin + main_w, body_bottom),
            color=(0.55, 0.58, 0.55),
            width=0.6,
        )
        page.draw_rect(
            fitz.Rect(
                margin + main_w, body_top,
                PAGE_W - margin, body_bottom
            ),
            color=(0.55, 0.58, 0.55),
            width=0.6,
        )

        # Column headings
        page.draw_rect(
            fitz.Rect(
                margin, body_top,
                margin + main_w, body_top + 24
            ),
            color=(0.65, 0.68, 0.65),
            fill=(0.91, 0.93, 0.90),
            width=0.6,
        )
        page.draw_rect(
            fitz.Rect(
                margin + main_w, body_top,
                PAGE_W - margin, body_top + 24
            ),
            color=(0.65, 0.68, 0.65),
            fill=(0.91, 0.93, 0.90),
            width=0.6,
        )

        add_label(page, margin + 10, body_top + 16, "Main Points", 9, "hebo")
        add_label(
            page, margin + main_w + 10,
            body_top + 16, "Notes", 9, "hebo"
        )

        target = fitz.Rect(
            margin + main_w + 5,
            body_top + 29,
            PAGE_W - margin - 5,
            body_bottom - 5,
        )

        # Summary section
        sy = PAGE_H - margin - summary_h
        page.draw_rect(
            fitz.Rect(margin, sy, PAGE_W - margin, PAGE_H - margin),
            color=(0.55, 0.58, 0.55),
            width=0.6,
        )
        add_label(page, margin + 10, sy + 16, "Summary:", 9, "hebo")
        add_label(page, PAGE_W - 90, PAGE_H - 8, f"Page {number}/{total}", 7)

    
    # Place one or two source pages inside the Cornell notes area.
    if second is None:
        if first is not None:
            place_source_page(
                page, target, src, first,
                crop_whitespace=crop_whitespace,
            )
    else:
        middle = (target.y0 + target.y1) / 2
        upper = fitz.Rect(target.x0, target.y0, target.x1, middle - 4)
        lower = fitz.Rect(target.x0, middle + 4, target.x1, target.y1)
        draw_line(
            page, target.x0, middle, target.x1, middle,
            color=(0.78, 0.80, 0.78), width=0.5,
        )
        if first is not None:
            place_source_page(
                page, upper, src, first,
                crop_whitespace=crop_whitespace,
            )
        place_source_page(
            page, lower, src, second,
            crop_whitespace=crop_whitespace,
        )



# --------------------------------------------------
# PDF conversion
# --------------------------------------------------

def build_pdf(input_bytes, template, pages_per_sheet=1, crop_whitespace=False):
    src = fitz.open(stream=input_bytes, filetype="pdf")
    out = fitz.open()
    try:
        if src.page_count == 0:
            raise ValueError("The uploaded document contains no pages.")
        if pages_per_sheet not in (1, 2):
            raise ValueError("Choose 1 or 2 pages per sheet.")
        total = (src.page_count + pages_per_sheet - 1) // pages_per_sheet
        for i in range(total):
            first = i * pages_per_sheet
            second = (
                first + 1
                if pages_per_sheet == 2 and first + 1 < src.page_count
                else None
            )
            make_page(
                out, src, first, second, i + 1, total, template,
                crop_whitespace=crop_whitespace,
            )
        return out.tobytes(garbage=4, deflate=True)
    finally:
        out.close()
        src.close()


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


# --------------------------------------------------
# Bilingual web interface with live preview
# --------------------------------------------------
st.markdown(
    f'<div class="section-title">{lang["upload_title"]}</div>',
    unsafe_allow_html=True,
)
st.write(lang["upload_help"])

uploaded_file = st.file_uploader(
    label=lang["drop_title"],
    type=["pdf", "png", "jpg", "jpeg", "txt", "docx", "doc", "pptx", "ppt"],
    accept_multiple_files=False,
    help=lang["upload_help"],
)
st.caption("📄 " + lang["drop_description"] + " · " + lang["drop_hint"])

st.markdown(
    f'<div class="section-title">{lang["template_title"]}</div>',
    unsafe_allow_html=True,
)
st.write(lang["template_help"])

template_labels = {
    "Template 1": lang["template1"],
    "Template 2": lang["template2"],
}
template = st.radio(
    lang["template_title"],
    ["Template 1", "Template 2"],
    format_func=lambda value: template_labels[value],
    horizontal=False,
    label_visibility="collapsed",
    key="template_choice",
)

default_pages = 2 if (
    uploaded_file is not None
    and uploaded_file.name.lower().endswith((".ppt", ".pptx"))
) else 1
pages_per_sheet = st.radio(
    "عدد الصفحات في الورقة" if is_arabic else "Source pages per sheet",
    options=[1, 2],
    format_func=lambda value: (
        ("صفحة واحدة — محتوى أكبر" if is_arabic else "One page — larger content")
        if value == 1
        else ("صفحتان — توفير الورق" if is_arabic else "Two pages — save paper")
    ),
    horizontal=True,
    index=0 if default_pages == 1 else 1,
    key="pages_per_sheet_choice",
)

if uploaded_file is None:
    st.info(
        "ارفع ملفًا لعرض المعاينة هنا تلقائيًا."
        if is_arabic
        else "Upload a file to see its preview here automatically."
    )
    st.session_state.pop("cornell_pdf", None)
    st.session_state.pop("cornell_filename", None)
    st.session_state.pop("cornell_signature", None)
else:
    st.success(
        f'{lang["ready"]}: {uploaded_file.name} '
        f'({uploaded_file.size / 1024:.1f} KB)'
    )
    file_bytes = uploaded_file.getvalue()
    crop_whitespace = uploaded_file.name.lower().endswith((".docx", ".doc"))
    signature = hashlib.sha256(
        uploaded_file.name.encode("utf-8", errors="replace")
        + file_bytes
        + template.encode("utf-8")
        + str(pages_per_sheet).encode("ascii")
        + str(crop_whitespace).encode("ascii")
    ).hexdigest()

    if st.session_state.get("cornell_signature") != signature:
        try:
            with st.spinner(
                "جارٍ إنشاء المعاينة..." if is_arabic else "Generating preview..."
            ):
                source_pdf = convert_to_pdf(uploaded_file)
                output_pdf = build_pdf(
                    source_pdf,
                    template,
                    pages_per_sheet=pages_per_sheet,
                    crop_whitespace=crop_whitespace,
                )
            base_name = uploaded_file.name.rsplit(".", 1)[0]
            st.session_state["cornell_pdf"] = output_pdf
            st.session_state["cornell_filename"] = f"{base_name}_cornell.pdf"
            st.session_state["cornell_signature"] = signature
            st.session_state["cornell_preview_page"] = 1
        except Exception as exc:
            st.session_state.pop("cornell_pdf", None)
            st.session_state.pop("cornell_filename", None)
            st.session_state.pop("cornell_signature", None)
            st.error(f'{lang["error"]}: {exc}')

    if (
        st.session_state.get("cornell_signature") == signature
        and "cornell_pdf" in st.session_state
    ):
        output_pdf = st.session_state["cornell_pdf"]
        with fitz.open(stream=output_pdf, filetype="pdf") as output_doc:
            output_page_count = output_doc.page_count

        st.markdown(
            f'<div class="section-title">{"المعاينة المباشرة" if is_arabic else "Live preview"}</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"عدد الصفحات الناتجة: {output_page_count}"
            if is_arabic
            else f"Output pages: {output_page_count}"
        )
        selected_preview_page = st.slider(
            "صفحة المعاينة" if is_arabic else "Preview page",
            min_value=1,
            max_value=max(1, output_page_count),
            value=min(
                st.session_state.get("cornell_preview_page", 1),
                max(1, output_page_count),
            ),
            key="cornell_preview_slider",
        )
        st.session_state["cornell_preview_page"] = selected_preview_page
        st.image(
            render_pdf_page(output_pdf, selected_preview_page - 1),
            caption=(
                f"صفحة {selected_preview_page} من {output_page_count}"
                if is_arabic
                else f"Page {selected_preview_page} of {output_page_count}"
            ),
            use_container_width=True,
        )
        st.download_button(
            label=f"⬇️ {lang['download_button']}",
            data=output_pdf,
            file_name=st.session_state["cornell_filename"],
            mime="application/pdf",
            type="primary",
            use_container_width=True,
            key="download_cornell_pdf",
        )


st.divider()
st.markdown(
    f'<div class="footer">{lang["footer"]}</div>',
    unsafe_allow_html=True,
)