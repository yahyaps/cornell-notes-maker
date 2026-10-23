import io
import streamlit as st
import fitz  # PyMuPDF

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
        "subtitle2": "Two slides per page, organized vertically.",
        "upload_title": "1. Upload your lecture",
        "upload_help": "Upload your PDF by dragging and dropping it below, or browse your device.",
        "drop_title": "Drop your PDF here",
        "drop_description": "Drag your lecture PDF into the upload area below",
        "drop_hint": "PDF files only • Your original file will not be modified",
        "browse": "Click Browse files to choose a PDF",
        "template_title": "2. Choose your template",
        "template_help": "Choose the Cornell layout that suits your study style.",
        "template1": "Template 1 — Cue column + Notes + Summary",
        "template2": "Template 2 — Class / Date / Topic + Main Points + Notes",
        "create_title": "3. Create your notes",
        "create_help": "Your PDF will contain two vertically stacked slides per page, without writing lines behind them.",
        "create_button": "Create Cornell PDF",
        "download_button": "Download Cornell PDF",
        "select_pdf": "Please upload a PDF file first.",
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
        "subtitle": "حوّل ملفات المحاضرات PDF إلى ملاحظات كورنيل منظمة.",
        "subtitle2": "شريحتان في كل صفحة، مرتبتان عموديًا.",
        "upload_title": "١. ارفع ملف المحاضرة",
        "upload_help": "يمكنك سحب ملف PDF وإفلاته في منطقة الرفع أدناه، أو اختيار الملف من جهازك.",
        "drop_title": "أفلت ملف PDF هنا",
        "drop_description": "اسحب ملف المحاضرة وأفلته داخل مساحة رفع الملف أدناه",
        "drop_hint": "ملفات PDF فقط • لن يتم تعديل الملف الأصلي",
        "browse": "أو اضغط على زر اختيار الملفات لتحديد المحاضرة",
        "template_title": "٢. اختر قالب كورنيل",
        "template_help": "اختر تصميم الملاحظات المناسب لطريقة دراستك.",
        "template1": "القالب الأول — عمود الأسئلة + الملاحظات + الملخص",
        "template2": "القالب الثاني — الصف والتاريخ والموضوع + النقاط الرئيسية والملاحظات",
        "create_title": "٣. أنشئ ملف الملاحظات",
        "create_help": "ستحتوي كل صفحة على شريحتين مرتبتين عموديًا، دون خطوط كتابة خلف الشرائح.",
        "create_button": "إنشاء ملف كورنيل PDF",
        "download_button": "تنزيل ملف كورنيل PDF",
        "select_pdf": "يرجى رفع ملف PDF أولًا.",
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


def make_page(out, src, first, second, number, total, template):
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

    # Clean slide area: no writing lines behind the slides.
    middle = (target.y0 + target.y1) / 2

    # Subtle divider between the slides
    draw_line(
        page,
        target.x0, middle,
        target.x1, middle,
        color=(0.78, 0.80, 0.78),
        width=0.5,
    )

    upper = fitz.Rect(
        target.x0, target.y0,
        target.x1, middle - 4,
    )
    lower = fitz.Rect(
        target.x0, middle + 4,
        target.x1, target.y1,
    )

    if first is not None:
        page.show_pdf_page(
            upper, src, first, keep_proportion=True
        )

    if second is not None:
        page.show_pdf_page(
            lower, src, second, keep_proportion=True
        )


# --------------------------------------------------
# PDF conversion
# --------------------------------------------------
def build_pdf(input_bytes, template):
    src = fitz.open(stream=input_bytes, filetype="pdf")
    out = fitz.open()

    try:
        if src.page_count == 0:
            raise ValueError("The uploaded PDF contains no pages.")

        total = (src.page_count + 1) // 2

        for i in range(total):
            first = i * 2
            second = first + 1 if first + 1 < src.page_count else None

            make_page(
                out, src, first, second,
                i + 1, total, template,
            )

        return out.tobytes(garbage=4, deflate=True)

    finally:
        out.close()
        src.close()


# --------------------------------------------------
# Bilingual web interface
# --------------------------------------------------
st.markdown(
    f'<div class="section-title">{lang["upload_title"]}</div>',
    unsafe_allow_html=True,
)

st.write(lang["upload_help"])

# Actual upload area — Streamlit handles drag and drop here.
uploaded_file = st.file_uploader(
    label=lang["drop_title"],
    type=["pdf"],
    accept_multiple_files=False,
    help=lang["upload_help"],
)

st.caption(
    "📄 " + lang["drop_description"] + " · " + lang["drop_hint"]
)

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
)

st.markdown(
    f'<div class="section-title">{lang["create_title"]}</div>',
    unsafe_allow_html=True,
)
st.write(lang["create_help"])

if uploaded_file is not None:
    st.success(
        f'{lang["ready"]}: {uploaded_file.name} '
        f'({uploaded_file.size / 1024:.1f} KB)'
    )

if st.button(
    f'✨ {lang["create_button"]}',
    type="primary",
    use_container_width=True,
):
    if uploaded_file is None:
        st.warning(lang["select_pdf"])
    else:
        try:
            with st.spinner(lang["creating"]):
                pdf_bytes = build_pdf(
                    uploaded_file.getvalue(),
                    template,
                )

            original_name = uploaded_file.name.rsplit(".", 1)[0]
            output_name = f"{original_name}_cornell.pdf"

            st.session_state["cornell_pdf"] = pdf_bytes
            st.session_state["cornell_filename"] = output_name
            st.session_state["cornell_language"] = selected_language

            st.success(lang["success"])

        except Exception as exc:
            st.error(f'{lang["error"]}: {exc}')

# Keep the generated PDF available after changing language.
if "cornell_pdf" in st.session_state:
    download_language = st.session_state.get(
        "cornell_language", selected_language
    )
    download_text = TRANSLATIONS[download_language]["download_button"]

    st.download_button(
        label=f"⬇️ {download_text}",
        data=st.session_state["cornell_pdf"],
        file_name=st.session_state["cornell_filename"],
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )

st.divider()
st.markdown(
    f'<div class="footer">{lang["footer"]}</div>',
    unsafe_allow_html=True,
)