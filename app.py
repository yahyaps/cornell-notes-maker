"""Streamlit interface for Cornell Notes Maker.

Flow: upload a lecture -> "PDF notes" tab (AI analysis per slide, rendered by
a note template) or "AI assistant" tab (study report and chat). Expensive
results are cached in the session per file, so changing a layout option or
the language never repeats AI work.
"""

import hashlib
import logging
import time
import uuid

import streamlit as st

import ai_assistant
import support
import usage_limits
from ai_assistant import AIError
from document_io import DocumentError, load_document, render_pdf_page
from note_templates import DEFAULT_TEMPLATE, TEMPLATES
from ui_text import TEXT
from usage_limits import LimitExceeded, limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("app")

UPLOAD_TYPES = ["pdf", "pptx", "ppt", "docx", "doc", "png", "jpg", "jpeg", "txt"]


# --------------------------------------------------
# Language and page setup
# --------------------------------------------------
def initial_language():
    requested = st.query_params.get("lang")
    if requested in TEXT:
        return requested
    locale = (st.context.locale or "").lower()
    return "ar" if locale.startswith("ar") or not locale else "en"


if "lang" not in st.session_state:
    st.session_state.lang = initial_language()
if st.session_state.get("lang_select") in TEXT:
    st.session_state.lang = st.session_state.lang_select

lang = st.session_state.lang
T = TEXT[lang]
rtl = lang == "ar"

st.set_page_config(page_title=T["app_title"], page_icon="📘", layout="centered")
st.query_params["lang"] = lang

def css_text(text):
    """Text for a CSS `content:` value (quotes and backslashes escaped)."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


st.html(f"""
<style>
  /* Layout: fluid on phones, comfortable width on tablets and laptops. */
  [data-testid="stMainBlockContainer"] {{
    max-width: 1120px; padding: 2.4rem 2rem 3rem;
    direction: {"rtl" if rtl else "ltr"}; text-align: {"right" if rtl else "left"};
  }}
  @media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{ padding: 1.2rem .9rem 2rem; }}
  }}
  /* Sliders and file names read left-to-right in both languages. */
  [data-testid="stSlider"], [data-testid="stFileUploaderFileName"] {{ direction: ltr; }}

  .brand {{ display: flex; align-items: center; gap: .7rem; }}
  .brand-mark {{ width: 2.1rem; height: auto; flex-shrink: 0; }}
  .brand-name {{ font-size: 1.15rem; font-weight: 800; color: #2F5A47; }}
  .tagline {{ color: #5E6063; font-size: 1.1rem; line-height: 1.8; margin: .6rem 0 0;
    max-width: 38rem; }}

  /* Hero: the copy and a real page of the output, side by side. */
  .hero {{ display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, .85fr);
    gap: clamp(1.5rem, 4vw, 3.5rem); align-items: center; margin: 1.6rem 0 .6rem; }}
  .hero h1 {{ font-size: clamp(2rem, 4.6vw, 2.9rem); font-weight: 800; line-height: 1.3;
    color: #2F5A47; margin: 0 0 1rem; padding: 0; }}
  .hero-text {{ font-size: clamp(1.08rem, 1.6vw, 1.25rem); line-height: 1.9; color: #404042;
    max-width: 34rem; margin: 0 0 1.6rem; }}
  .hero h2 {{ font-size: 1.05rem; font-weight: 800; color: #404042; margin: 0 0 .7rem;
    padding: 0; }}
  .parts {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .65rem; }}
  .parts li {{ display: grid; grid-template-columns: .9rem 1fr; gap: .7rem;
    align-items: start; }}
  .parts p {{ margin: 0; font-size: 1.02rem; line-height: 1.75; }}
  .parts b {{ color: #2F5A47; }}
  .part-text {{ color: #5E6063; }}
  /* Swatches echo the boxes on the PDF page so the legend maps onto the image. */
  .swatch {{ width: .9rem; height: .9rem; border-radius: .15rem; margin-top: .45rem; }}
  .swatch-explain {{ background: #404042; }}
  .swatch-points {{ background: #EEF4F1; border-inline-start: 3px solid #4D7D67; }}
  .swatch-review {{ background: #FFFFFF; border: 1.5px solid #CFDDD5; }}
  .swatch-summary {{ background: #F6F6F4; border: 1.5px solid #CFDDD5; }}
  .hero-after {{ color: #5E6063; font-size: 1rem; margin: 1.1rem 0 0; }}
  .hero-sheet {{ margin: 0; justify-self: center; width: min(100%, 25rem); }}
  .hero-sheet img {{ display: block; width: 100%; height: auto; border-radius: .35rem;
    border: 1px solid #DCE5E0; box-shadow: 0 1.2rem 2.4rem -1.4rem rgba(47, 90, 71, .45); }}
  /* Phones: the template card right below shows the same page, so the hero
     keeps only the words and the upload area moves up. */
  @media (max-width: 760px) {{
    .hero {{ grid-template-columns: 1fr; }}
    .hero-sheet {{ display: none; }}
  }}

  .step {{ font-weight: 800; font-size: clamp(1.2rem, 2.2vw, 1.45rem); color: #404042;
    margin: 1.6rem 0 .7rem; }}
  .muted {{ color: #5E6063; font-size: 1rem; line-height: 1.85; }}
  .template-name {{ font-weight: 800; font-size: 1.2rem; color: #4D7D67; margin-bottom: .4rem; }}

  /* Upload area: larger target, translated instructions. */
  /* The one bold element: the upload area is a Cornell notebook sheet, with
     ruled lines and the sage margin rule of the cue column. */
  [data-testid="stFileUploaderDropzone"] {{ position: relative; min-height: 10rem;
    padding-block: 1.8rem; padding-inline: 5.4rem 1.6rem;
    border: 1.5px solid #CFDDD5; border-radius: .5rem;
    background-color: #FFFFFF;
    background-image: linear-gradient({"to left" if rtl else "to right"},
        transparent 4.2rem, #4D7D67 4.2rem, #4D7D67 calc(4.2rem + 2px), transparent calc(4.2rem + 2px)),
      repeating-linear-gradient(to bottom, transparent 0 1.95rem, #E3ECE7 1.95rem 2rem); }}
  [data-testid="stFileUploaderDropzone"]:hover {{ border-color: #4D7D67; }}
  [data-testid="stFileUploaderDropzoneInstructions"] > div {{ display: none; }}
  [data-testid="stFileUploaderDropzoneInstructions"]::before {{
    content: "{css_text(T["upload_drop"])}"; font-size: 1.1rem; font-weight: 700;
    color: #404042; }}
  /* Only the browse button (kind=secondary); the file's delete button keeps its icon. */
  [data-testid="stFileUploaderDropzone"] button[kind="secondary"] {{ min-height: 2.8rem;
    padding: 0 1.4rem; border-radius: .7rem; }}
  [data-testid="stFileUploaderDropzone"] button[kind="secondary"] > div {{ display: none; }}
  [data-testid="stFileUploaderDropzone"] button[kind="secondary"]::after {{
    content: "{css_text(T["upload_button"])}"; font-size: 1rem; font-weight: 700; }}

  /* Tabs, buttons and messages sized for touch screens. */
  [data-testid="stTab"] p {{ font-size: 1.1rem; font-weight: 700; }}
  [data-testid="stButtonGroup"] button p {{ font-size: 1rem; }}
  /* Segmented controls draw their joined borders for left-to-right only. */
  [data-testid="stButtonGroup"] [role="radiogroup"] {{ direction: ltr; }}
  .stButton button, .stDownloadButton button, .stFormSubmitButton button {{
    min-height: 3rem; font-size: 1.05rem; border-radius: .75rem; }}
  [data-testid="stImage"] img {{ border: 1px solid #DCE5E0; border-radius: .6rem; }}

  .footer {{ color: #7A7C80; font-size: .95rem; text-align: center; margin-top: 3rem;
    padding-top: 1.4rem; border-top: 1px solid #E6ECE8; line-height: 2; }}

  /* AI text: lists follow the interface direction, and each paragraph takes
     the direction of its own first letter (Arabic or English). */
  [data-testid="stChatMessage"], [data-testid="stMarkdownContainer"] {{
    direction: {"rtl" if rtl else "ltr"}; }}
  [data-testid="stMarkdownContainer"] :is(p, li, h1, h2, h3, h4, td, th) {{
    unicode-bidi: plaintext; text-align: start; }}
</style>
""")


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def show_error(kind, **fields):
    message = T["errors"].get(kind) or T["errors"]["unknown"]
    if "{ref}" in message and "ref" not in fields:
        fields["ref"] = "-"
    st.error(message.format(**fields), icon="⚠️")


def show_unexpected(exc, what):
    ref = uuid.uuid4().hex[:8]
    logger.error("%s failed [ref %s]: %s", what, ref, ai_assistant.redact(repr(exc), 1000))
    show_error("unknown", ref=ref)


def show_limit(exc, pages=0):
    if exc.kind == "rate":
        show_error("rate", minutes=max(1, round(exc.retry_after / 60)))
    elif exc.kind == "too_many_slides":
        show_error("too_many_slides", pages=pages, limit=usage_limits.MAX_AI_SLIDES)
    else:
        show_error(exc.kind)


def plain_markdown(text):
    """AI text for st.markdown with math rendering off: "$...$" would become
    left-to-right KaTeX that scrambles formulas inside Arabic sentences."""
    return text.replace("$", "\\$")


def isolate(text):
    return chr(0x2068) + text + chr(0x2069)


def human_size(size):
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"


def human_duration(seconds):
    if seconds < 60:
        return T["seconds"].format(n=max(1, round(seconds)))
    return T["minutes"].format(n=round(seconds / 60))


def visitor():
    return usage_limits.visitor_id(st.context)


def cache(name):
    """Per-session dict keyed by file signature (and options)."""
    return st.session_state.setdefault(name, {})


def forget_other_files(sig):
    """Keep memory bounded: drop cached results that belong to older uploads."""
    for name in ("notes", "pdfs", "reports", "chats", "lecture_text"):
        store = cache(name)
        for key in list(store):
            if (key[0] if isinstance(key, tuple) else key) != sig:
                del store[key]


@st.cache_data(max_entries=64, show_spinner=False)
def preview_png(pdf_bytes, page_index):
    return render_pdf_page(pdf_bytes, page_index, zoom=1.6)


# --------------------------------------------------
# Header
# --------------------------------------------------
# The logo is a Cornell sheet in miniature (static/brand/logo.svg); served as a
# file because st.html strips inline SVG.
LOGO = '<img class="brand-mark" src="app/static/brand/logo.svg" alt="" width="34" height="41">'

title_col, lang_col = st.columns([4, 1.4], vertical_alignment="center")
with title_col:
    st.html(f'<div class="brand">{LOGO}<span class="brand-name">{T["app_title"]}</span></div>')
with lang_col:
    st.segmented_control(
        T["language"], options=["ar", "en"], default=lang, key="lang_select",
        format_func=lambda code: "العربية" if code == "ar" else "English",
        label_visibility="collapsed",
    )

# First visit: show the product itself, a real page of the notes PDF, with
# what each part of the page is for. Once a file is loaded the hero steps
# aside so the working steps sit near the top.
if st.session_state.get("upload") is None and not st.session_state.get("_test_document"):
    parts = "".join(
        f'<li><span class="swatch swatch-{key}"></span>'
        f'<p><b>{name}</b> <span class="part-text">{text}</span></p></li>'
        for key, name, text in T["page_parts"])
    st.html(f"""
<section class="hero">
  <div class="hero-copy">
    <h1>{T["hero_title"]}</h1>
    <p class="hero-text">{T["hero_text"]}</p>
    <h2>{T["page_parts_title"]}</h2>
    <ul class="parts">{parts}</ul>
    <p class="hero-after">{T["hero_after"]}</p>
  </div>
  <figure class="hero-sheet">
    <img src="app/static/previews/ai_cornell.png" alt="{T["hero_image_alt"]}" loading="eager">
  </figure>
</section>
""")
else:
    st.html(f'<p class="tagline">{T["tagline"]}</p>')


# --------------------------------------------------
# Step 1: upload
# --------------------------------------------------
st.html(f'<div class="step">{T["step_upload"]}</div>')
uploaded = st.file_uploader(T["upload_label"], type=UPLOAD_TYPES, help=T["upload_help"],
                            label_visibility="collapsed", key="upload")
st.caption(T["upload_help"])

doc = None
if uploaded is not None:
    data = uploaded.getvalue()
    sig = hashlib.sha256(uploaded.name.encode("utf-8", "replace") + b"\0" + data).hexdigest()
    doc = st.session_state.get("doc")
    if not doc or doc["sig"] != sig:
        try:
            with st.spinner(T["converting"]):
                pdf_bytes, pages = load_document(uploaded)
            doc = {"sig": sig, "name": uploaded.name, "pdf": pdf_bytes, "pages": pages,
                   "size": len(data)}
            st.session_state.doc = doc
            forget_other_files(sig)
        except DocumentError as exc:
            st.session_state.pop("doc", None)
            doc = None
            show_error(exc.kind)
        except Exception as exc:  # noqa: BLE001 - shown as a reference code
            st.session_state.pop("doc", None)
            doc = None
            show_unexpected(exc, "Upload")
    if doc:
        # File names and sizes are isolated so they keep their own direction
        # inside Arabic text (U+2068 first-strong isolate ... U+2069 pop).
        st.success(T["file_info"].format(name=isolate(doc["name"]), pages=doc["pages"],
                                         size=isolate(human_size(doc["size"]))), icon="📄")
else:
    # Tests cannot drive st.file_uploader, so tests/test_app_flow.py places a
    # document in session state directly (visitors cannot set session state).
    doc = st.session_state.get("doc") if st.session_state.get("_test_document") else None
    if doc is None:
        st.session_state.pop("doc", None)


# --------------------------------------------------
# Access code (optional, set APP_ACCESS_CODE)
# --------------------------------------------------
def ai_allowed(place):
    if not usage_limits.access_code_required() or st.session_state.get("access_ok"):
        return True
    st.html(f'<div class="step">{T["access_title"]}</div>')
    st.caption(T["access_hint"])
    with st.form(f"access_form_{place}", border=False):
        code = st.text_input(T["access_title"], type="password", label_visibility="collapsed")
        submitted = st.form_submit_button(T["access_button"])
    if submitted:
        try:
            limiter.access_attempt(visitor())
        except LimitExceeded as exc:
            show_limit(exc)
            return False
        if usage_limits.access_code_ok(code):
            st.session_state.access_ok = True
            st.rerun()
        st.error(T["access_wrong"])
    return False


# --------------------------------------------------
# Tab: PDF notes
# --------------------------------------------------
def run_slide_analysis(pages=None):
    """Analyze all slides (or just `pages`) and store the notes for this file."""
    count = len(pages) if pages else doc["pages"]
    try:
        limiter.start_ai_job(visitor(), slides=count)
    except LimitExceeded as exc:
        show_limit(exc, pages=count)
        return
    bar = st.progress(0.0, text=T["analyzing"].format(done=0, total=count))
    started = time.monotonic()

    def progress(done, total):
        elapsed = time.monotonic() - started
        text = (T["analyzing_eta"].format(done=done, total=total,
                                          eta=human_duration(elapsed / done * (total - done)))
                if 0 < done < total else T["analyzing"].format(done=done, total=total))
        bar.progress(done / total, text=text)

    try:
        notes = ai_assistant.analyze_pages(doc["pdf"], pages=pages, progress=progress)
    except AIError as exc:
        limiter.refund_slides(count)
        bar.empty()
        show_error(exc.kind)
        return
    except Exception as exc:  # noqa: BLE001
        bar.empty()
        show_unexpected(exc, "Slide analysis")
        return
    logger.info("Analyzed %d slides in %.0fs", count, time.monotonic() - started)

    store = cache("notes")
    if pages and doc["sig"] in store:
        by_page = {note["source_page"]: note for note in store[doc["sig"]]}
        by_page.update({note["source_page"]: note for note in notes})
        notes = [by_page[number] for number in sorted(by_page)]
    store[doc["sig"]] = notes
    pdfs = cache("pdfs")
    for key in [k for k in pdfs if k[0] == doc["sig"]]:
        del pdfs[key]
    st.rerun()


def notes_pdf(template_key, per_sheet):
    key = (doc["sig"], template_key, per_sheet)
    pdfs = cache("pdfs")
    if key not in pdfs:
        with st.spinner(T["building_pdf"]):
            pdfs[key] = TEMPLATES[template_key].build_pdf(
                doc["pdf"], cache("notes")[doc["sig"]], pages_per_sheet=per_sheet,
                lecture_title=doc["name"].rsplit(".", 1)[0],
            )
    return pdfs[key]


def show_preview(pdf_bytes, file_name):
    import pymupdf

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as output:
        total = output.page_count
    st.html(f'<div class="step">{T["preview"]}</div>')
    page = 1
    if total > 1:
        page = st.slider(T["preview_page"], 1, total, 1, key="preview_page",
                         label_visibility="collapsed")
        page = min(page, total)
    st.image(preview_png(pdf_bytes, page - 1),
             caption=T["page_of"].format(page=page, total=total), width="stretch")
    st.download_button(f"⬇️ {T['download']}", data=pdf_bytes, file_name=file_name,
                       mime="application/pdf", type="primary", width="stretch",
                       key="download_notes")


def notes_tab():
    st.html(f'<div class="step">{T["step_template"]}</div>')
    keys = list(TEMPLATES)
    template_key = DEFAULT_TEMPLATE
    if len(keys) > 1:
        template_key = st.radio(
            T["step_template"], keys, horizontal=True, label_visibility="collapsed",
            format_func=lambda k: TEMPLATES[k].name_ar if rtl else TEMPLATES[k].name_en,
            key="template_choice",
        )
    template = TEMPLATES[template_key]
    with st.container(border=True):
        image_col, text_col = st.columns([1, 1.6], vertical_alignment="center")
        if template.preview_image:
            image_col.image(str(template.preview_image), width="stretch")
        text_col.html(
            f'<div class="template-name">{template.name_ar if rtl else template.name_en}</div>'
            f'<div class="muted">{template.description_ar if rtl else template.description_en}</div>'
        )
        per_sheet = text_col.segmented_control(
            T["per_sheet"], options=[2, 1], default=2, key="per_sheet",
            format_func=lambda n: T["per_sheet_1"] if n == 1 else T["per_sheet_2"],
        ) or 2

    st.html(f'<div class="step">{T["step_create"]}</div>')
    if doc is None:
        st.info(T["upload_first"], icon="📄")
        return
    if not ai_allowed("notes"):
        return

    notes = cache("notes").get(doc["sig"])
    if notes is None:
        st.caption(T["create_hint"])
        if st.button(f"✨ {T['create_button']}", type="primary", width="stretch",
                     key="create_notes"):
            run_slide_analysis()
        return

    failed = [n["source_page"] for n in notes if n.get("error")]
    if failed:
        st.warning(T["failed_slides"].format(n=len(failed), pages=", ".join(map(str, failed))),
                   icon="⚠️")
        if st.button(T["retry_failed"], key="retry_failed"):
            run_slide_analysis(pages=failed)
    else:
        st.success(T["analysis_done"].format(n=len(notes)), icon="✅")

    try:
        pdf_bytes = notes_pdf(template_key, per_sheet)
    except Exception as exc:  # noqa: BLE001
        show_unexpected(exc, "PDF build")
        return
    show_preview(pdf_bytes, f"{doc['name'].rsplit('.', 1)[0]}_notes.pdf")


# --------------------------------------------------
# Tab: AI assistant
# --------------------------------------------------
def lecture_text():
    store = cache("lecture_text")
    if doc["sig"] not in store:
        store[doc["sig"]] = ai_assistant.extract_pdf_text(doc["pdf"])
    return store[doc["sig"]]


def report_section():
    st.html(f'<div class="step">{T["report_title"]}</div>')
    st.caption(T["report_hint"])
    reports = cache("reports")
    count_col, button_col = st.columns([1, 1.4], vertical_alignment="bottom")
    question_count = count_col.selectbox(T["mcq_count"], [5, 10, 15, 20], index=1,
                                         key="ai_question_count")
    if button_col.button(f"✨ {T['report_button']}", type="primary", width="stretch",
                         key="analyze_lecture_button"):
        try:
            limiter.start_ai_job(visitor())
            with st.spinner(T["report_working"]):
                reports[doc["sig"]] = ai_assistant.analyze_lecture(
                    doc["pdf"], question_count=question_count)
        except LimitExceeded as exc:
            show_limit(exc)
        except AIError as exc:
            show_error(exc.kind)
        except Exception as exc:  # noqa: BLE001
            show_unexpected(exc, "Lecture report")

    report = reports.get(doc["sig"])
    if report:
        with st.container(border=True):
            st.markdown(plain_markdown(report))
        st.download_button(f"⬇️ {T['report_download']}", data=report.encode("utf-8"),
                           file_name=f"{doc['name'].rsplit('.', 1)[0]}_study_report.md",
                           mime="text/markdown", width="stretch",
                           key="download_ai_study_notes")


def chat_section():
    st.html(f'<div class="step">{T["chat_title"]}</div>')
    history = cache("chats").setdefault(doc["sig"], [])
    for turn in history:
        with st.chat_message(turn["role"], avatar="🧑‍🎓" if turn["role"] == "user" else "📘"):
            st.markdown(plain_markdown(turn["content"]))

    if not history:
        # A chosen suggestion is queued once; the widget is cleared so a later
        # rerun (e.g. switching language) cannot send it again.
        def queue_suggestion():
            st.session_state.pending_question = st.session_state.chat_suggestion
            st.session_state.chat_suggestion = None

        st.pills(T["chat_title"], T["chat_suggestions"], key="chat_suggestion",
                 label_visibility="collapsed", on_change=queue_suggestion)
    question = (st.chat_input(T["chat_placeholder"], key="chat_input",
                              max_chars=ai_assistant.MAX_QUESTION_CHARS)
                or st.session_state.pop("pending_question", None))
    if question:
        try:
            limiter.chat_message(visitor())
            text = lecture_text()
            with st.chat_message("user", avatar="🧑‍🎓"):
                st.markdown(plain_markdown(question))
            with st.chat_message("assistant", avatar="📘"), st.spinner(T["chat_thinking"]):
                answer = ai_assistant.ask_about_lecture(text, history, question)
            history += [{"role": "user", "content": question},
                        {"role": "assistant", "content": answer}]
            st.rerun()
        except LimitExceeded as exc:
            show_limit(exc)
        except AIError as exc:
            show_error(exc.kind)
        except Exception as exc:  # noqa: BLE001
            show_unexpected(exc, "Lecture chat")

    if history and st.button(T["chat_clear"], key="chat_clear"):
        history.clear()
        st.rerun()


def assistant_tab():
    st.caption(T["assistant_intro"])
    if doc is None:
        st.info(T["upload_first"], icon="📄")
        return
    if not ai_allowed("assistant"):
        return
    report_section()
    st.divider()
    chat_section()


# --------------------------------------------------
# Tab: support
# --------------------------------------------------
def support_tab():
    st.html(f'<p class="muted">{T["support_intro"]}</p>')
    categories = T["support_categories"]
    with st.form("support_form", clear_on_submit=False, border=True):
        category = st.selectbox(T["support_category"], list(categories),
                                format_func=categories.get, key="support_category")
        name_col, email_col = st.columns(2)
        name = name_col.text_input(T["support_name"], max_chars=support.MAX_NAME_CHARS,
                                   key="support_name")
        email = email_col.text_input(T["support_email"], max_chars=254, key="support_email")
        message = st.text_area(T["support_message"], help=T["support_message_help"],
                               max_chars=support.MAX_MESSAGE_CHARS, height=170,
                               key="support_message")
        submitted = st.form_submit_button(f"✉️ {T['support_send']}", type="primary",
                                          width="stretch")
    if not submitted:
        return
    try:
        support.validate(email, message, name)
        limiter.support_ticket(visitor())
        context = {"Language": lang}
        if doc:
            context["Lecture"] = f"{doc['name']} ({doc['pages']} pages)"
        ticket = support.send_ticket(category, email, message, name, context)
    except support.TicketError as exc:
        st.error(T["support_errors"][exc.kind], icon="⚠️")
    except LimitExceeded as exc:
        show_limit(exc)
    else:
        st.success(T["support_sent"].format(ticket=ticket), icon="✅")


notes_view, assistant_view, support_view = st.tabs(
    [T["tab_notes"], T["tab_assistant"], T["tab_support"]])
with notes_view:
    notes_tab()
with assistant_view:
    assistant_tab()
with support_view:
    support_tab()

st.html(f'<div class="footer">{T["privacy"]}<br>{T["footer_help"]}</div>')
