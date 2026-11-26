import hashlib
import streamlit as st
import fitz  # PyMuPDF

from document_io import convert_to_pdf, render_pdf_page
from note_templates import TEMPLATES


# --------------------------------------------------
# Page configuration
# --------------------------------------------------
st.set_page_config(
    page_title="Cornell Notes Maker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
)


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
        "template_title": "2. Template",
        "template_help": "Your lecture becomes a printable A4 study guide.",
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
        "template_title": "٢. القالب",
        "template_help": "تتحول محاضرتك إلى دليل مذاكرة جاهز للطباعة بحجم A4.",
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

template_keys = list(TEMPLATES)
if len(template_keys) > 1:
    template_key = st.radio(
        lang["template_title"],
        template_keys,
        format_func=lambda key: (
            TEMPLATES[key].name_ar if is_arabic else TEMPLATES[key].name_en
        ),
        label_visibility="collapsed",
        key="template_choice",
    )
else:
    template_key = template_keys[0]
template = TEMPLATES[template_key]
st.markdown(
    f"**{template.name_ar if is_arabic else template.name_en}** — "
    f"{template.description_ar if is_arabic else template.description_en}"
)

pages_per_sheet = st.radio(
    "عدد الشرائح في الورقة" if is_arabic else "Slides per sheet",
    options=[1, 2],
    format_func=lambda value: (
        ("شريحة واحدة — خط أكبر" if is_arabic else "One slide — larger text")
        if value == 1
        else ("شريحتان — توفير الورق" if is_arabic else "Two slides — save paper")
    ),
    horizontal=True,
    index=1,
    key="pages_per_sheet_choice",
)

st.markdown(
    f'<div class="section-title">{"إنشاء ملاحظات المحاضرة بالذكاء الاصطناعي" if is_arabic else "Create AI Lecture Notes"}</div>',
    unsafe_allow_html=True,
)
st.write(
    "سيحلّل Gemini كل شريحة عند الضغط على الزر فقط، ثم ينشئ ملف PDF جديدًا."
    if is_arabic
    else "Gemini will analyze each slide only after you press the button, then create a separate PDF."
)

if uploaded_file is not None:
    st.success(
        f'{lang["ready"]}: {uploaded_file.name} '
        f'({uploaded_file.size / 1024:.1f} KB)'
    )

ai_current_signature = None
if uploaded_file is not None:
    ai_current_signature = hashlib.sha256(
        uploaded_file.name.encode("utf-8", errors="replace")
        + uploaded_file.getvalue()
        + template_key.encode("utf-8")
        + str(pages_per_sheet).encode("ascii")
    ).hexdigest()

if st.button(
    "✨ إنشاء ملاحظات المحاضرة بالذكاء الاصطناعي"
    if is_arabic
    else "✨ Create AI Lecture Notes",
    type="primary",
    use_container_width=True,
    key="create_ai_lecture_notes_button",
):
    if uploaded_file is None:
        st.warning(lang["select_pdf"])
    else:
        try:
            from ai_assistant import analyze_pages

            with st.spinner(
                "جارٍ تحليل الشرائح وإنشاء ملف الملاحظات..."
                if is_arabic
                else "Analyzing slides and creating your notes PDF..."
            ):
                source_pdf = convert_to_pdf(uploaded_file)
                page_notes = analyze_pages(source_pdf)
                base_name = uploaded_file.name.rsplit(".", 1)[0]
                ai_pdf = template.build_pdf(
                    source_pdf,
                    page_notes,
                    pages_per_sheet=pages_per_sheet,
                    lecture_title=base_name,
                )

            st.session_state["ai_notes_pdf"] = ai_pdf
            st.session_state["ai_notes_filename"] = f"{base_name}_ai_lecture_notes.pdf"
            st.session_state["ai_notes_source_name"] = uploaded_file.name
            st.session_state["ai_notes_signature"] = ai_current_signature
            st.session_state["ai_notes_preview_page"] = 1
            st.success(
                "تم إنشاء ملاحظات المحاضرة بنجاح."
                if is_arabic
                else "AI lecture notes created successfully."
            )
        except Exception as exc:
            st.error(
                f"تعذّر إنشاء ملاحظات الذكاء الاصطناعي: {exc}"
                if is_arabic
                else f"Could not create AI lecture notes: {exc}"
            )

if (
    st.session_state.get("ai_notes_pdf")
    and ai_current_signature
    and st.session_state.get("ai_notes_signature") == ai_current_signature
):
    ai_pdf = st.session_state["ai_notes_pdf"]
    with fitz.open(stream=ai_pdf, filetype="pdf") as ai_doc:
        ai_page_count = ai_doc.page_count

    st.markdown(
        f'<div class="section-title">{"معاينة ملاحظات الذكاء الاصطناعي" if is_arabic else "AI Notes Preview"}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"عدد الصفحات: {ai_page_count}"
        if is_arabic
        else f"Output pages: {ai_page_count}"
    )
    ai_preview_page = st.slider(
        "صفحة المعاينة" if is_arabic else "Preview page",
        min_value=1,
        max_value=max(1, ai_page_count),
        value=min(
            st.session_state.get("ai_notes_preview_page", 1),
            max(1, ai_page_count),
        ),
        key="ai_notes_preview_slider",
    )
    st.session_state["ai_notes_preview_page"] = ai_preview_page
    st.image(
        render_pdf_page(ai_pdf, ai_preview_page - 1),
        caption=(
            f"صفحة {ai_preview_page} من {ai_page_count}"
            if is_arabic
            else f"Page {ai_preview_page} of {ai_page_count}"
        ),
        use_container_width=True,
    )
    st.download_button(
        label="⬇️ تنزيل ملاحظات المحاضرة"
        if is_arabic
        else "⬇️ Download AI Lecture Notes",
        data=ai_pdf,
        file_name=st.session_state.get(
            "ai_notes_filename", "ai_lecture_notes.pdf"
        ),
        mime="application/pdf",
        type="primary",
        use_container_width=True,
        key="download_ai_notes_pdf",
    )


st.divider()
st.markdown(
    f'<div class="footer">{lang["footer"]}</div>',
    unsafe_allow_html=True,
)


# --------------------------------------------------
# AI Assistant — optional lecture analysis
# --------------------------------------------------
from ai_assistant import analyze_lecture

st.divider()
st.subheader(
    "المساعد الذكي للمحاضرات"
    if is_arabic
    else "AI Lecture Assistant"
)

st.write(
    "حلّل محاضرتك للحصول على شرح عربي ونقاط مهمة وأسئلة اختبار."
    if is_arabic
    else "Analyze your lecture to generate Arabic explanations, "
         "high-yield points, and practice questions."
)

question_count = st.selectbox(
    "عدد أسئلة MCQ" if is_arabic else "Number of MCQs",
    options=[5, 10, 15, 20],
    index=1,
    key="ai_question_count",
)

if st.button(
    "✨ حلّل المحاضرة بالذكاء الاصطناعي"
    if is_arabic
    else "✨ Analyze Lecture with AI",
    type="primary",
    use_container_width=True,
    key="analyze_lecture_button",
):
    if uploaded_file is None:
        st.warning(
            "ارفع ملف المحاضرة أولًا."
            if is_arabic
            else "Please upload a lecture file first."
        )
    else:
        try:
            with st.spinner(
                "جارٍ تحليل المحاضرة... قد يستغرق ذلك بعض الوقت."
                if is_arabic
                else "Analyzing lecture... this may take a moment."
            ):
                source_pdf = convert_to_pdf(uploaded_file)
                analysis = analyze_lecture(
                    source_pdf,
                    question_count=question_count,
                )

            st.session_state["ai_lecture_analysis"] = analysis
            st.session_state["ai_lecture_filename"] = uploaded_file.name

        except Exception as exc:
            st.error(
                f"تعذّر تحليل المحاضرة: {exc}"
                if is_arabic
                else f"Lecture analysis failed: {exc}"
            )

if st.session_state.get("ai_lecture_analysis"):
    st.markdown("---")
    st.markdown(
        "### نتائج تحليل المحاضرة"
        if is_arabic
        else "### Lecture Analysis Results"
    )
    st.caption(
        st.session_state.get("ai_lecture_filename", "")
    )
    st.markdown(st.session_state["ai_lecture_analysis"])

    st.download_button(
        label="تنزيل الشرح النصي"
        if is_arabic
        else "Download Study Notes",
        data=st.session_state["ai_lecture_analysis"].encode("utf-8"),
        file_name="lecture_study_notes.md",
        mime="text/markdown",
        use_container_width=True,
        key="download_ai_study_notes",
    )