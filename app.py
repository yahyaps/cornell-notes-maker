"""Streamlit interface for Cornell Notes Maker.

Flow: upload a lecture -> "PDF notes" tab (AI analysis per slide, rendered by
a note template) or "AI assistant" tab (study report and chat). Expensive
results are cached in the session per file, so changing a layout option or
the language never repeats AI work.
"""

import hashlib
import logging
import uuid

import streamlit as st

import ai_assistant
import jobs
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
  /* Type scale (root 18px, steps of ~1.25): 0.9 small, 1 body, 1.35 lead,
     1.55 section, up to 3.8rem for the hero headline. */
  [data-testid="stMainBlockContainer"] {{
    max-width: 1180px; padding: 2.2rem 2.2rem 3.5rem;
    direction: {"rtl" if rtl else "ltr"}; text-align: {"right" if rtl else "left"};
  }}
  @media (max-width: 640px) {{
    [data-testid="stMainBlockContainer"] {{ padding: 1.1rem 1rem 2.2rem; }}
  }}
  /* Sliders and file names read left-to-right in both languages. */
  [data-testid="stSlider"], [data-testid="stFileUploaderFileName"] {{ direction: ltr; }}
  /* Keyboard users always see where they are; the accent earns its place here. */
  button:focus-visible, [role="tab"]:focus-visible, input:focus-visible,
  textarea:focus-visible {{ outline: 3px solid #FF6200 !important; outline-offset: 2px; }}

  .brand {{ display: flex; align-items: center; gap: .75rem; }}
  .brand-mark {{ width: 2.4rem; height: auto; flex-shrink: 0; }}
  .brand-name {{ font-size: 1.3rem; font-weight: 800; color: #003366; }}
  .tagline {{ color: #5F5C66; font-size: 1.2rem; line-height: 1.8; margin: .8rem 0 0;
    max-width: 36rem; }}

  /* Hero: the copy and a real page of the output, side by side. */
  .hero {{ display: grid; grid-template-columns: minmax(0, 1.22fr) minmax(0, .78fr);
    gap: clamp(2rem, 5vw, 4.5rem); align-items: center; margin: 2.4rem 0 1rem; }}
  /* Balanced wrapping keeps the headline to two even lines, no orphan word. */
  .hero h1 {{ font-size: clamp(2.2rem, 4.3vw, 3.35rem); font-weight: 800; line-height: 1.3;
    color: #003366; margin: 0 0 1.3rem; padding: 0; text-wrap: balance; }}
  .hero-text {{ font-size: clamp(1.15rem, 1.9vw, 1.35rem); line-height: 1.9; color: #2B2D38;
    max-width: 36rem; margin: 0 0 2.2rem; }}
  .hero h2 {{ font-size: 1.15rem; font-weight: 800; color: #2B2D38; margin: 0 0 1rem;
    padding: 0; }}
  .parts {{ list-style: none; margin: 0; padding: 0; display: grid; gap: .9rem; }}
  .parts li {{ display: grid; grid-template-columns: 1.15rem 1fr; gap: .85rem;
    align-items: start; }}
  .parts p {{ margin: 0; font-size: 1.12rem; line-height: 1.75; text-wrap: pretty; }}
  .parts b {{ color: #003366; }}
  .part-text {{ color: #5F5C66; }}
  /* Swatches echo the boxes on the PDF page so the legend maps onto the image. */
  .swatch {{ width: 1.15rem; height: 1.15rem; border-radius: .2rem; margin-top: .4rem; }}
  .swatch-explain {{ background: #404042; }}
  .swatch-points {{ background: #EEF4F1; border-inline-start: 4px solid #4D7D67; }}
  .swatch-review {{ background: #FFFFFF; border: 1.5px solid #CFDDD5; }}
  .swatch-summary {{ background: #F6F6F4; border: 1.5px solid #CFDDD5; }}
  .hero-after {{ color: #5F5C66; font-size: 1.05rem; margin: 1.6rem 0 0; padding-top: 1.2rem;
    border-top: 1px solid #E5DCD5; max-width: 36rem; }}
  .hero-sheet {{ margin: 0; justify-self: center; width: min(100%, 27rem); }}
  .hero-sheet img {{ display: block; width: 100%; height: auto; border-radius: .4rem;
    border: 1px solid #E5DCD5; background: #FFFFFF;
    box-shadow: 0 1.6rem 3rem -1.8rem rgba(0, 51, 102, .45); }}
  /* Phones: the template card right below shows the same page, so the hero
     keeps only the words and the upload area moves up. */
  @media (max-width: 760px) {{
    .hero {{ grid-template-columns: 1fr; margin-top: 1.4rem; }}
    .hero-sheet {{ display: none; }}
    .hero-text {{ margin-bottom: 1.6rem; }}
  }}

  .step {{ font-weight: 800; font-size: clamp(1.45rem, 2.6vw, 1.85rem); color: #003366;
    margin: 2.8rem 0 1rem; }}
  .muted {{ color: #5F5C66; font-size: 1.1rem; line-height: 1.85; }}
  .template-name {{ font-weight: 800; font-size: 1.35rem; color: #004488; margin-bottom: .5rem; }}
  [data-testid="stCaptionContainer"] p {{ font-size: .95rem; line-height: 1.8; }}

  /* The one bold element: the upload area is a Cornell notebook sheet, with
     blue-grey rules and the orange margin of a ruled pad. */
  [data-testid="stFileUploaderDropzone"] {{ position: relative; min-height: 12rem;
    padding-block: 2rem; padding-inline: 5.6rem 1.8rem;
    border: 1.5px solid #E5DCD5; border-radius: .6rem;
    background-color: #FFFFFF;
    background-image: linear-gradient({"to left" if rtl else "to right"},
        transparent 4.4rem, #FF6200 4.4rem, #FF6200 calc(4.4rem + 2px), transparent calc(4.4rem + 2px)),
      repeating-linear-gradient(to bottom, transparent 0 2.2rem, #C9D3DE 2.2rem calc(2.2rem + 1px));
    box-shadow: 0 1rem 2rem -1.6rem rgba(0, 51, 102, .3); }}
  [data-testid="stFileUploaderDropzone"]:hover {{ border-color: #004488; }}
  [data-testid="stFileUploaderDropzoneInstructions"] > div {{ display: none; }}
  [data-testid="stFileUploaderDropzoneInstructions"]::before {{
    content: "{css_text(T["upload_drop"])}"; font-size: 1.3rem; font-weight: 800;
    color: #003366; }}
  /* Only the browse button (kind=secondary); the file's delete button keeps its icon. */
  [data-testid="stFileUploaderDropzone"] button[kind="secondary"] {{ min-height: 3.2rem;
    padding: 0 1.6rem; border-radius: .75rem; border-color: #004488; }}
  [data-testid="stFileUploaderDropzone"] button[kind="secondary"] > div {{ display: none; }}
  [data-testid="stFileUploaderDropzone"] button[kind="secondary"]::after {{
    content: "{css_text(T["upload_button"])}"; font-size: 1.1rem; font-weight: 800;
    color: #004488; }}
  @media (max-width: 640px) {{
    [data-testid="stFileUploaderDropzone"] {{ padding-inline: 3.6rem 1rem; min-height: 10rem;
      background-image: linear-gradient({"to left" if rtl else "to right"},
          transparent 2.6rem, #FF6200 2.6rem, #FF6200 calc(2.6rem + 2px), transparent calc(2.6rem + 2px)),
        repeating-linear-gradient(to bottom, transparent 0 2.2rem, #C9D3DE 2.2rem calc(2.2rem + 1px)); }}
    [data-testid="stFileUploaderDropzoneInstructions"]::before {{ font-size: 1.12rem; }}
  }}

  /* Tabs, buttons and messages sized for touch screens. */
  [data-testid="stTab"] p {{ font-size: 1.22rem; font-weight: 800; }}
  [data-testid="stTab"] {{ padding-block: .6rem; }}
  [data-testid="stButtonGroup"] button p {{ font-size: 1.05rem; }}
  /* Segmented controls draw their joined borders for left-to-right only. */
  [data-testid="stButtonGroup"] [role="radiogroup"] {{ direction: ltr; }}
  .stButton button, .stDownloadButton button, .stFormSubmitButton button {{
    min-height: 3.4rem; border-radius: .8rem; }}
  .stButton button p, .stDownloadButton button p, .stFormSubmitButton button p {{
    font-size: 1.15rem; font-weight: 800; }}
  [data-testid="stAlertContentInfo"] p, [data-testid="stAlertContentSuccess"] p,
  [data-testid="stAlertContentWarning"] p, [data-testid="stAlertContentError"] p {{
    font-size: 1.08rem; }}
  [data-testid="stImage"] img {{ border: 1px solid #E5DCD5; border-radius: .6rem; }}

  .footer {{ color: #5F5C66; font-size: 1rem; text-align: center; margin-top: 3.5rem;
    padding-top: 1.6rem; border-top: 1px solid #E5DCD5; line-height: 2; }}

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
    seconds = max(1, round(seconds))
    if seconds < 60:
        return T["seconds"].format(n=seconds)
    minutes, rest = divmod(seconds, 60)
    return T["min_sec"].format(m=minutes, s=rest) if rest else T["minutes"].format(n=minutes)


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
            old_job = st.session_state.pop("job", None)
            if old_job is not None and old_job.running:
                old_job.cancel()
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
def current_job():
    """The session's slide-analysis job for the current file, if any."""
    job = st.session_state.get("job")
    return job if job is not None and doc is not None and job.sig == doc["sig"] else None


def start_analysis(pages=None):
    """Start analyzing all slides (or just `pages`) on a background thread."""
    pages = list(pages) if pages else list(range(1, doc["pages"] + 1))
    try:
        limiter.start_ai_job(visitor(), slides=len(pages))
    except LimitExceeded as exc:
        show_limit(exc, pages=len(pages))
        return
    try:
        st.session_state.job = jobs.start_job(doc["pdf"], doc["sig"], pages,
                                              retry=len(pages) < doc["pages"])
    except jobs.ServerBusy:
        limiter.refund_slides(len(pages))
        show_error("server_busy")
        return
    st.session_state.pop("job_summary", None)
    st.session_state.pop("job_error", None)
    st.rerun()


def absorb_finished_job(job):
    """Merge a finished job into the session's notes, once (script thread)."""
    if job.running or job.consumed:
        return
    job.consumed = True
    if job.status == "failed":
        limiter.refund_slides(job.total)
        st.session_state.job_error = (job.error_kind, job.error_ref)
        return
    notes = job.notes
    not_sent = sum(1 for note in notes if note.get("error") == "cancelled")
    limiter.refund_slides(not_sent)
    store = cache("notes")
    if job.retry and doc["sig"] in store:
        by_page = {note["source_page"]: note for note in store[doc["sig"]]}
        by_page.update({note["source_page"]: note for note in notes})
        notes = [by_page[number] for number in sorted(by_page)]
    store[doc["sig"]] = notes
    pdfs = cache("pdfs")
    for key in [k for k in pdfs if k[0] == doc["sig"]]:
        del pdfs[key]
    # Counted from this job's own results, not from the merged notes.
    errors = [note.get("error") for note in job.notes]
    st.session_state.job_summary = {
        "sig": job.sig, "total": job.total, "ok": errors.count(None),
        "failed": sum(1 for e in errors if e and e != "cancelled"),
        "time": job.elapsed(), "cancelled": job.status == "cancelled",
    }


@st.fragment(run_every=1.0)
def job_progress():
    """Live progress; reruns itself every second without blocking the page."""
    job = current_job()
    if job is None or not job.running:
        st.rerun()  # whole page, to show the finished result
    state = job.snapshot()
    done, total = state["done"], state["total"]
    st.progress(done / total if total else 0.0,
                text=T["job_progress"].format(done=done, total=total))
    if state["in_flight"]:
        st.caption(T["job_current"].format(pages="، ".join(map(str, state["in_flight"]))
                                           if rtl else ", ".join(map(str, state["in_flight"]))))
    elif done == 0:
        st.caption(T["job_starting"])
    eta = job.eta()
    elapsed = human_duration(job.elapsed())
    st.caption(T["job_time"].format(elapsed=elapsed, eta=human_duration(eta))
               if eta is not None else T["job_time_no_eta"].format(elapsed=elapsed))
    if state["failed"]:
        st.caption(T["job_failed_so_far"].format(n=state["failed"]))
    if job.cancel_event.is_set():
        st.info(T["job_cancelling"], icon="⏳")
    else:
        st.caption(T["job_free_to_move"])
        if st.button(T["job_cancel"], key="cancel_job", icon="⏹️"):
            job.cancel()  # takes effect at once; the next tick shows "stopping"


def show_job_summary(notes):
    summary = st.session_state.get("job_summary")
    failed = [n["source_page"] for n in notes if n.get("error") and n["error"] != "cancelled"]
    not_sent = [n["source_page"] for n in notes if n.get("error") == "cancelled"]
    if summary and summary["sig"] == doc["sig"]:
        text = T["job_summary"].format(ok=summary["ok"], total=summary["total"],
                                       time=human_duration(summary["time"]))
        if summary["failed"]:
            text += " " + T["job_summary_failed"].format(n=summary["failed"])
        (st.warning if summary["failed"] else st.success)(text, icon="📊")
    if not_sent:
        st.info(T["job_cancelled"].format(n=len(not_sent)), icon="⏹️")
        if st.button(T["continue_analysis"], key="continue_analysis", type="primary"):
            start_analysis(pages=not_sent)
    if failed:
        st.warning(T["failed_slides"].format(n=len(failed), pages=", ".join(map(str, failed))),
                   icon="⚠️")
        if st.button(T["retry_failed"], key="retry_failed"):
            start_analysis(pages=failed)


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
            T["per_sheet"], options=[1, 2], default=1, key="per_sheet",
            format_func=lambda n: T["per_sheet_1"] if n == 1 else T["per_sheet_2"],
        ) or 1

    st.html(f'<div class="step">{T["step_create"]}</div>')
    if doc is None:
        st.info(T["upload_first"], icon="📄")
        return
    if not ai_allowed("notes"):
        return

    job = current_job()
    if job is not None:
        absorb_finished_job(job)
        if job.running:
            job_progress()
            return
    # Kept until the next analysis starts, so later reruns don't hide it.
    error = st.session_state.get("job_error")
    if error:
        kind, ref = error
        show_error(kind, ref=ref or "-")

    notes = cache("notes").get(doc["sig"])
    if notes is None:
        st.caption(T["create_hint"])
        if st.button(f"✨ {T['create_button']}", type="primary", width="stretch",
                     key="create_notes"):
            start_analysis()
        return

    show_job_summary(notes)

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
