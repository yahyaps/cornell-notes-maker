"""AI Cornell notes - the unified template.

A4 portrait. Each slide becomes one study unit:

    +--------------------------------------------------+
    | [3] Slide title                                  |
    +------------------------+-------------------------+
    | Explanation (Arabic)   |  Original slide         |
    |                        |  (vector, not an image) |
    | Key points (tinted)    +-------------------------+
    |                        |  Review question (cue)  |
    |                        +-------------------------+
    |                        |  Summary                |
    +------------------------+-------------------------+

With two slides per sheet, units are paired on a page when both fit in half a
page; a unit that needs more room gets a full page, and text that still does
not fit continues on the next page. Text is never clipped or dropped.

Text is laid out by MuPDF's HTML engine, which applies the Unicode bidi
algorithm, so Arabic sentences with English terms keep the correct order.
"""

import html
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import pymupdf

# --------------------------------------------------
# Page geometry (points) and brand
# --------------------------------------------------
PAGE_W, PAGE_H = 595.28, 841.89  # A4 (210 x 297 mm)
MARGIN_X = 34
MARGIN_TOP = 28
MARGIN_BOTTOM = 30
HEADER_H = 30
UNIT_GAP = 18          # between two units on one page
TITLE_H = 26
COLUMN_GAP = 14
BLOCK_GAP = 9
EXPLANATION_SHARE = 0.52   # explanation column width; slide column gets the rest
# Slide height limits (share of the unit height) tried in order; only tall,
# portrait pages are affected, wide slides are limited by the column width.
SLIDE_SHARES = (0.62, 0.52, 0.42)
BOX_PAD = 7
SCALES = (1.0, 0.95, 0.9, 0.85)   # text sizes tried before moving to more space
MIN_SCALE = SCALES[-1]
# With one slide per page there is room to spare, so text may also grow.
SINGLE_PAGE_SCALES = (1.15, 1.1, 1.05) + SCALES

SAGE = "#4D7D67"
CHARCOAL = "#404042"
WHITE = "#FFFFFF"
SAGE_TINT = "#EEF4F1"
SAGE_BORDER = "#CFDDD5"
MUTED = "#77787B"
SUMMARY_TINT = "#F6F6F4"

# Almarai covers Arabic, Latin and shared punctuation in one font, so mixed
# sentences never fall back to a font that lacks a glyph (e.g. "؟"), and
# its glyphs map back to the right characters when text is copied or searched.
# Symbols it lacks (Greek letters, arrows) are drawn by MuPDF's fallback fonts.
FONT_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
REQUIRED_FONTS = (
    "Almarai-Regular.ttf",
    "Almarai-Bold.ttf",
    "Almarai-ExtraBold.ttf",
)

LABELS = {
    "explanation": "الشرح",
    "key_points": "النقاط المهمة",
    "review": "سؤال للمراجعة",
    "summary": "الخلاصة",
    "continued": "تابع",
    "slide": "Slide",
    "failed": "تعذّر تحليل هذه الشريحة بالذكاء الاصطناعي. الشريحة الأصلية معروضة كما هي.",
}

_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN = re.compile(r"[A-Za-z]")
# Short English term in parentheses, e.g. "(Informed Consent)".
# Up to 48 characters: the longest run that still fits the narrowest text
# column at the largest text scale, so keeping it unbroken never overflows.
_PAREN_TERM = re.compile(r"\(([A-Za-z0-9][^()\u0600-\u06FF]{0,47})\)")
# A number with its unit, e.g. "5 mcg", "37 degC", ">= 140 mmHg", "500 mg/day".
_UNIT = r"(?:[\u00B5\u03BC]?(?:mg|g|kg|mcg|ng|pg|mL|ml|L|dL|dl|mmol|mol|mEq|IU|U|units?|mmHg|cmH2O|kPa|h|hr|hrs|hours?|min|mins|minutes?|s|sec|seconds?|days?|weeks?|months?|years?|yrs?|mm|cm|m|km|nm|kDa|Da|bpm|Hz|kcal|cal|ppm|x))"
_MEASUREMENT = re.compile(
    r"(?:[\u2265\u2264<>=\u00B1~\u2248]\s?)?\d+(?:[.,]\d+)?(?:\s?[-\u2013]\s?\d+(?:[.,]\d+)?)?"
    r"\s?(?:\u00B0\s?[CF]|%|" + _UNIT + r"(?:/" + _UNIT + r")*)(?![A-Za-z])"
)
_SENTENCE_END = re.compile(r"(?<=[.!?\u061F])\s+")
NBSP = "\u00A0"
NB_HYPHEN = "\u2011"   # drawn by MuPDF's fallback font
LRM = "\u200E"   # left-to-right mark


@lru_cache(maxsize=None)
def css(scale=1.0):
    """Stylesheet with every text size multiplied by `scale`."""
    def pt(size):
        return f"{size * scale:.2f}pt"
    return f"""
@font-face {{font-family: almarai; src: url(Almarai-Regular.ttf);}}
@font-face {{font-family: almarai; src: url(Almarai-Bold.ttf); font-weight: bold;}}
@font-face {{font-family: almaraix; src: url(Almarai-ExtraBold.ttf);}}
* {{font-family: almarai; color: {CHARCOAL}; font-size: {pt(9.6)}; line-height: 1.75;
    margin: 0; padding: 0;}}
.label {{font-weight: bold; color: {SAGE}; font-size: {pt(8.4)}; margin-bottom: {pt(2)};}}
.pt {{margin-bottom: {pt(2.5)};}}
.title {{font-family: almaraix; font-size: {pt(11)}; line-height: 1.3;}}
.badge {{font-family: almaraix; color: {WHITE}; font-size: {pt(9.5)}; text-align: center;
         line-height: 1.3;}}
.header {{font-size: {pt(8.4)}; color: {MUTED}; line-height: 1.3;}}
.header b {{color: {SAGE}; font-size: {pt(10)};}}
"""


def _archive():
    missing = [name for name in REQUIRED_FONTS if not (FONT_DIR / name).exists()]
    if missing:
        raise FileNotFoundError(
            "Missing fonts for the AI notes PDF: " + ", ".join(missing)
            + f" (expected in {FONT_DIR})."
        )
    return pymupdf.Archive(str(FONT_DIR))


# --------------------------------------------------
# Text helpers
# --------------------------------------------------
def text_direction(text):
    """Reading direction of a paragraph.

    Like HTML's dir="auto", the first strong letter decides, so an Arabic
    sentence full of English terms stays right-to-left. A paragraph that opens
    with an English term is still Arabic when Arabic letters dominate.
    """
    first_arabic = _ARABIC.search(text)
    first_latin = _LATIN.search(text)
    if not first_arabic:
        return "ltr"
    if not first_latin or first_arabic.start() < first_latin.start():
        return "rtl"
    return "rtl" if len(_ARABIC.findall(text)) >= len(_LATIN.findall(text)) else "ltr"


def _clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _escape(text, rtl=False):
    """Escape for HTML and protect English runs inside Arabic sentences.

    Short parenthesised terms are kept on one line. In right-to-left text a
    number with its unit is fenced with left-to-right marks, so the bidi
    algorithm shows "37 °C" rather than "C° 37".
    """
    escaped = html.escape(_clean(text))
    escaped = _PAREN_TERM.sub(
        lambda m: "(" + m.group(1).replace(" ", NBSP).replace("-", NB_HYPHEN) + ")", escaped)
    if rtl:
        escaped = _MEASUREMENT.sub(lambda m: LRM + m.group(0).replace(" ", NBSP) + LRM, escaped)
    return escaped


def _para(text, cls=""):
    cls_attr = f' class="{cls}"' if cls else ""
    direction = text_direction(text)
    return f'<div{cls_attr} dir="{direction}">{_escape(text, direction == "rtl")}</div>'


def _label(key, continued=False):
    text = LABELS[key] + (f" ({LABELS['continued']})" if continued else "")
    return f'<div class="label" dir="rtl">{html.escape(text)}</div>'


def split_sentences(text):
    return [part for part in _SENTENCE_END.split(_clean(text)) if part]


# --------------------------------------------------
# Unit content
# --------------------------------------------------
@dataclass
class Unit:
    source_page: int
    title: str
    sentences: list
    points: list
    review: str
    summary: str
    continued: bool = False

    @classmethod
    def from_note(cls, note):
        if note.get("error"):
            # Analysis failed: keep the slide and say so instead of leaving a gap.
            return cls(int(note["source_page"]), f"{LABELS['slide']} {note['source_page']}",
                       [LABELS["failed"]], [], review="", summary="")
        return cls(
            source_page=int(note["source_page"]),
            title=_clean(note.get("title")) or f"{LABELS['slide']} {note['source_page']}",
            sentences=split_sentences(note.get("explanation_ar")),
            points=[_clean(p) for p in note.get("key_points") or [] if _clean(p)],
            review=_clean(note.get("review_question_ar")),
            summary=_clean(note.get("summary_ar")),
        )

    def explanation_html(self, sentences):
        if not sentences:
            return ""
        return _label("explanation", self.continued) + _para(" ".join(sentences))

    @staticmethod
    def points_html(points):
        if not points:
            return ""
        return _label("key_points") + "".join(_para("• " + p, "pt") for p in points)

    def review_html(self):
        return "" if self.continued or not self.review else _label("review") + _para(self.review)

    def summary_html(self):
        return "" if not self.summary else _label("summary") + _para(self.summary)


# --------------------------------------------------
# Measuring and drawing HTML
# --------------------------------------------------
class Typesetter:
    """Draws HTML at an exact text scale and measures its visible height."""

    def __init__(self):
        self.archive = _archive()
        self._cache = {}

    def close(self):
        self._cache.clear()

    def _layout_height(self, body, width, scale):
        story = pymupdf.Story(body, user_css=css(scale), archive=self.archive)
        _, filled = story.place(pymupdf.Rect(0, 0, width, PAGE_H * 6))
        return pymupdf.Rect(filled).y1 + 1

    def measure(self, body, width, scale=1.0):
        """Return (layout_height, visible_height); (0, 0) for empty content.

        layout_height is what MuPDF reserves (includes trailing line spacing);
        visible_height is where the last glyph actually ends.
        """
        if not body:
            return 0.0, 0.0
        key = (body, round(width, 2), scale)
        if key not in self._cache:
            layout_h = self._layout_height(body, width, scale)
            # A throwaway document per measurement: each HTML layout embeds the
            # fonts again, and only closing the document releases that memory.
            with pymupdf.open() as scratch:
                page = scratch.new_page(width=width + 10, height=layout_h + 10)
                page.insert_htmlbox(pymupdf.Rect(0, 0, width, layout_h), body,
                                    css=css(scale), archive=self.archive, scale_low=1)
                bottoms = [b[3] for b in page.get_text("blocks")]
            self._cache[key] = (layout_h, max(bottoms) if bottoms else 0.0)
        return self._cache[key]

    def height(self, body, width, scale=1.0):
        return self.measure(body, width, scale)[1]

    def draw(self, page, x0, y0, width, body, scale=1.0):
        if not body:
            return
        layout_h, _ = self.measure(body, width, scale)
        rect = pymupdf.Rect(x0, y0, x0 + width, y0 + layout_h)
        spare, _ = page.insert_htmlbox(rect, body, css=css(scale), archive=self.archive,
                                       scale_low=1)
        if spare < 0:  # Measurement and drawing use the same engine; never expected.
            raise RuntimeError(f"Text did not fit its box on page {page.number + 1}.")


# --------------------------------------------------
# Layout planning
# --------------------------------------------------
@dataclass
class UnitLayout:
    unit: Unit
    scale: float
    sentences: list
    points: list
    slide_share: float = SLIDE_SHARES[0]


@dataclass
class PagePlan:
    units: list = field(default_factory=list)


def content_rect():
    top = MARGIN_TOP + HEADER_H
    return pymupdf.Rect(MARGIN_X, top, PAGE_W - MARGIN_X, PAGE_H - MARGIN_BOTTOM)


def half_rects():
    full = content_rect()
    half_h = (full.height - UNIT_GAP) / 2
    return (pymupdf.Rect(full.x0, full.y0, full.x1, full.y0 + half_h),
            pymupdf.Rect(full.x0, full.y1 - half_h, full.x1, full.y1))


def column_widths(total_width, unit):
    """(explanation, slide) widths; a continuation has no slide, so text spans all."""
    if unit.continued:
        return total_width, 0.0
    left = (total_width - COLUMN_GAP) * EXPLANATION_SHARE
    return left, total_width - COLUMN_GAP - left


class Layout:
    """Computes sizes shared by planning and drawing, so they always agree."""

    def __init__(self, typesetter, source):
        self.ts = typesetter
        self.source = source

    def slide_size(self, unit, width, unit_height, share):
        src = self.source[unit.source_page - 1].rect
        ratio = src.height / src.width if src.width else 0.75
        w, h = width, width * ratio
        max_h = unit_height * share
        if h > max_h:
            w, h = max_h / ratio, max_h
        return w, h

    def box_height(self, body, width, scale=1.0):
        if not body:
            return 0.0
        return self.ts.height(body, width - 2 * BOX_PAD, scale) + 2 * BOX_PAD

    def left_height(self, unit, width, sentences, points, scale):
        explanation = self.ts.height(unit.explanation_html(sentences), width, scale)
        points_box = self.box_height(unit.points_html(points), width, scale)
        gap = BLOCK_GAP if explanation and points_box else 0
        return explanation + gap + points_box

    def right_height(self, unit, width, unit_height, share, with_summary=True):
        """Slide, then the review question, then the summary."""
        if unit.continued:
            return 0.0
        _, height = self.slide_size(unit, width, unit_height, share)
        boxes = [unit.review_html()] + ([unit.summary_html()] if with_summary else [])
        for body in boxes:
            if body:
                height += BLOCK_GAP + self.box_height(body, width)
        return height

    def needed_height(self, unit, rect, sentences, points, scale,
                      share=SLIDE_SHARES[0], with_summary=True):
        left_w, right_w = column_widths(rect.width, unit)
        left = self.left_height(unit, left_w, sentences, points, scale)
        if unit.continued:
            # No slide column: the summary closes the full-width text.
            summary = self.box_height(unit.summary_html(), left_w) if with_summary else 0
            body = left + (BLOCK_GAP + summary if summary else 0)
        else:
            body = max(left, self.right_height(unit, right_w, rect.height, share,
                                               with_summary))
        return TITLE_H + BLOCK_GAP + body


class Planner:
    def __init__(self, layout):
        self.layout = layout

    def fit(self, unit, rect, scales=SCALES):
        """Largest text scale at which the whole unit fits in rect, else None."""
        for share in SLIDE_SHARES:
            for scale in scales:
                if self.layout.needed_height(unit, rect, unit.sentences, unit.points,
                                             scale, share) <= rect.height:
                    return UnitLayout(unit, scale, unit.sentences, unit.points, share)
        return None

    def split(self, unit, rect):
        """Fill rect with as much text as fits at MIN_SCALE; return (layout, rest)."""
        items = [("s", s) for s in unit.sentences] + [("p", p) for p in unit.points]

        def parts(chunk):
            return ([t for kind, t in chunk if kind == "s"],
                    [t for kind, t in chunk if kind == "p"])

        keep = 1  # Always make progress, even if one sentence is very long.
        for count in range(2, len(items) + 1):
            sentences, points = parts(items[:count])
            if self.layout.needed_height(unit, rect, sentences, points, MIN_SCALE,
                                         SLIDE_SHARES[-1], with_summary=False) > rect.height:
                break
            keep = count
        sentences, points = parts(items[:keep])
        rest_sentences, rest_points = parts(items[keep:])
        rest = Unit(unit.source_page, unit.title, rest_sentences, rest_points,
                    review="", summary=unit.summary, continued=True)
        # The summary closes the unit, so it moves to the continuation.
        head = Unit(unit.source_page, unit.title, unit.sentences, unit.points,
                    unit.review, summary="", continued=unit.continued)
        return UnitLayout(head, MIN_SCALE, sentences, points, SLIDE_SHARES[-1]), rest

    def plan(self, units, pages_per_sheet):
        full = content_rect()
        top_half, _ = half_rects()
        pages, queue = [], list(units)
        while queue:
            unit = queue.pop(0)
            if pages_per_sheet == 2:
                first = self.fit(unit, top_half)
                if first:
                    second = self.fit(queue[0], top_half) if queue else None
                    if second:
                        queue.pop(0)
                    pages.append(PagePlan([first] + ([second] if second else [])))
                    continue
            layout = self.fit(unit, full,
                              SINGLE_PAGE_SCALES if pages_per_sheet == 1 else SCALES)
            if layout is None:
                layout, rest = self.split(unit, full)
                queue.insert(0, rest)
            pages.append(PagePlan([layout]))
        return pages


# --------------------------------------------------
# Drawing
# --------------------------------------------------
def _rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _box(page, rect, fill, border=None):
    page.draw_rect(rect, color=_rgb(border) if border else None, fill=_rgb(fill),
                   width=0.6, radius=0.04)


class Renderer:
    def __init__(self, typesetter, layout, source, lecture_title):
        self.ts = typesetter
        self.layout = layout
        self.source = source
        self.lecture_title = _clean(lecture_title)

    def header(self, page, number, total):
        title = self.lecture_title or "AI Lecture Notes"
        number_w = 60
        width = PAGE_W - 2 * MARGIN_X - number_w
        # The page number sits on the side opposite the title's reading start.
        if text_direction(title) == "rtl":
            title_x, number_x, align = MARGIN_X + number_w, MARGIN_X, "left"
        else:
            title_x, number_x, align = MARGIN_X, PAGE_W - MARGIN_X - number_w, "right"
        title_html = (f'<div class="header" dir="{text_direction(title)}">'
                      f"<b>{_escape(title)}</b></div>")
        # Long titles are shown smaller rather than wrapping into the content.
        scale = next((s for s in (1.0, 0.9, 0.8, 0.7)
                      if self.ts.height(title_html, width, s) <= HEADER_H - 12), 0.7)
        self.ts.draw(page, title_x, MARGIN_TOP, width, title_html, scale)
        self.ts.draw(page, number_x, MARGIN_TOP, number_w,
                     f'<div class="header" style="text-align:{align}">{number} / {total}</div>')
        y = MARGIN_TOP + HEADER_H - 8
        page.draw_line((MARGIN_X, y), (PAGE_W - MARGIN_X, y), color=_rgb(SAGE), width=1.2)

    def title_bar(self, page, rect, unit):
        bar_bottom = rect.y0 + TITLE_H
        badge = pymupdf.Rect(rect.x0, rect.y0 + 3, rect.x0 + 26, bar_bottom - 4)
        _box(page, badge, SAGE)
        badge_html = f'<div class="badge">{unit.source_page}</div>'
        badge_h = self.ts.height(badge_html, badge.width)
        self.ts.draw(page, badge.x0, badge.y0 + (badge.height - badge_h) / 2 - 1,
                     badge.width, badge_html)
        title = unit.title + (f" ({LABELS['continued']})" if unit.continued else "")
        title_html = f'<div class="title" dir="ltr">{_escape(title)}</div>'
        width = rect.x1 - badge.x1 - 8
        scale = next((s for s in (1.0, 0.9, 0.8, 0.7)
                      if self.ts.height(title_html, width, s) <= TITLE_H - 4), 0.7)
        title_h = self.ts.height(title_html, width, scale)
        self.ts.draw(page, badge.x1 + 8, badge.y0 + (badge.height - title_h) / 2 - 1,
                     width, title_html, scale)
        page.draw_line((rect.x0, bar_bottom), (rect.x1, bar_bottom),
                       color=_rgb(SAGE_BORDER), width=0.6)

    def text_box(self, page, x0, y0, width, body, fill, border=None, scale=1.0, accent=False):
        h = self.layout.box_height(body, width, scale)
        box = pymupdf.Rect(x0, y0, x0 + width, y0 + h)
        _box(page, box, fill, border)
        if accent:  # Sage bar on the reading-start (right) edge.
            page.draw_line((box.x1, box.y0 + 1), (box.x1, box.y1 - 1), color=_rgb(SAGE), width=2.4)
        self.ts.draw(page, x0 + BOX_PAD, y0 + BOX_PAD, width - 2 * BOX_PAD, body, scale)
        return box.y1

    def unit(self, page, rect, plan):
        unit, scale = plan.unit, plan.scale
        self.title_bar(page, rect, unit)
        left_w, right_w = column_widths(rect.width, unit)
        top = rect.y0 + TITLE_H + BLOCK_GAP
        left_x, right_x = rect.x0, rect.x0 + left_w + COLUMN_GAP

        # Left column: explanation, then the tinted key-points box.
        y = top
        explanation = unit.explanation_html(plan.sentences)
        if explanation:
            self.ts.draw(page, left_x, y, left_w, explanation, scale)
            y += self.ts.height(explanation, left_w, scale) + BLOCK_GAP
        points = unit.points_html(plan.points)
        if points:
            y = self.text_box(page, left_x, y, left_w, points, SAGE_TINT, scale=scale,
                              accent=True)

        # Right column: the original slide as vector content, the review
        # question, then the summary (balances the usually longer left column).
        summary = unit.summary_html()
        if unit.continued:
            if summary:
                self.text_box(page, left_x, y + BLOCK_GAP, left_w, summary,
                              SUMMARY_TINT, SAGE_BORDER)
        else:
            slide_w, slide_h = self.layout.slide_size(unit, right_w, rect.height,
                                                      plan.slide_share)
            slide = pymupdf.Rect(right_x, top, right_x + slide_w, top + slide_h)
            page.show_pdf_page(slide, self.source, unit.source_page - 1, keep_proportion=True)
            page.draw_rect(slide, color=_rgb(SAGE_BORDER), width=0.8)
            y = slide.y1
            review = unit.review_html()
            if review:
                y = self.text_box(page, right_x, y + BLOCK_GAP, right_w,
                                  review, WHITE, SAGE_BORDER)
            if summary:
                self.text_box(page, right_x, y + BLOCK_GAP, right_w, summary,
                              SUMMARY_TINT, SAGE_BORDER)

    def page(self, out, plan, number, total):
        page = out.new_page(width=PAGE_W, height=PAGE_H)
        self.header(page, number, total)
        if len(plan.units) == 1:
            rects = [content_rect()]
        else:
            rects = half_rects()
            mid = (rects[0].y1 + rects[1].y0) / 2
            page.draw_line((rects[0].x0, mid), (rects[0].x1, mid), color=_rgb(SAGE_BORDER),
                           width=0.6, dashes="[3 3] 0")
        for rect, unit_plan in zip(rects, plan.units):
            self.unit(page, rect, unit_plan)


# --------------------------------------------------
# Public entry point
# --------------------------------------------------
def build_pdf(source_pdf_bytes, page_notes, pages_per_sheet=1, lecture_title=""):
    """Create the AI Cornell notes PDF.

    `page_notes` is the list returned by ai_assistant.analyze_pages(): one dict
    per slide with source_page, title, explanation_ar, key_points and,
    optionally, review_question_ar and summary_ar.
    """
    if not page_notes:
        raise ValueError("No AI explanations were supplied.")
    if pages_per_sheet not in (1, 2):
        raise ValueError("Choose 1 or 2 source slides per sheet.")

    source = pymupdf.open(stream=source_pdf_bytes, filetype="pdf")
    out = pymupdf.open()
    typesetter = Typesetter()
    try:
        units = []
        for note in page_notes:
            unit = Unit.from_note(note)
            if not 1 <= unit.source_page <= source.page_count:
                raise ValueError(f"Invalid source page: {unit.source_page}")
            units.append(unit)

        layout = Layout(typesetter, source)
        plans = Planner(layout).plan(units, pages_per_sheet)
        renderer = Renderer(typesetter, layout, source, lecture_title)
        for number, plan in enumerate(plans, start=1):
            # Each page is drawn in its own document with fonts subset to the
            # glyphs used, then merged; drawing straight into `out` would keep
            # a full font copy per text box in memory (~300 MB for 38 slides).
            with pymupdf.open() as single:
                renderer.page(single, plan, number, len(plans))
                single.subset_fonts()
                out.insert_pdf(single)
        out.set_metadata({"title": lecture_title or "AI Lecture Notes",
                          "creator": "Cornell Notes Maker"})
        return out.tobytes(garbage=4, deflate=True)
    finally:
        typesetter.close()
        out.close()
        source.close()
