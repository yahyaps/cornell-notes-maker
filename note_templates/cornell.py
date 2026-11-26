"""Template 1 - Cornell layout (Course details, Key Points, Lecture Content, Notes).

Moved verbatim from app.py. Output is locked by tests/test_cornell_template.py;
do not change the drawing code without updating the golden images on purpose.
"""

import fitz  # PyMuPDF

PAGE_W = 8.5 * 72
PAGE_H = 11 * 72


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


def make_page(
    out, src, first, second, number, total, template,
    crop_whitespace=False, hide_notes=False
):
    page = out.new_page(width=PAGE_W, height=PAGE_H)

    margin = 28
    header_h = 66
    summary_h = 126
    main_w = 150

    # Header remains visible regardless of the Notes toggle.
    page.draw_rect(
        fitz.Rect(margin, margin, PAGE_W - margin, margin + header_h),
        color=(0.55, 0.58, 0.55),
        width=0.6,
    )
    add_label(page, margin + 8, margin + 18, "Course:", 9, "hebo")
    add_label(page, margin + 8, margin + 47, "Topic:", 9, "hebo")
    add_label(page, PAGE_W - 165, margin + 18, "Date:", 9, "hebo")
    add_label(page, PAGE_W - 165, margin + 47, "Continued from:", 7, "hebo")

    body_top = margin + header_h + 12
    # When personal notes are hidden, let lecture content use the freed space.
    body_bottom = PAGE_H - margin - (0 if hide_notes else summary_h)
    left_x0 = margin
    left_x1 = margin + main_w
    right_x0 = left_x1
    right_x1 = PAGE_W - margin

    # The Key Points column always remains visible.
    page.draw_rect(
        fitz.Rect(left_x0, body_top, left_x1, body_bottom),
        color=(0.55, 0.58, 0.55),
        width=0.6,
    )
    page.draw_rect(
        fitz.Rect(left_x0, body_top, left_x1, body_top + 24),
        color=(0.65, 0.68, 0.65),
        fill=(0.91, 0.93, 0.90),
        width=0.6,
    )
    add_label(page, left_x0 + 10, body_top + 16, "Key Points", 9, "hebo")

    # The toggle hides only the Notes heading/border, never the Key Points column.
    if not hide_notes:
        page.draw_rect(
            fitz.Rect(right_x0, body_top, right_x1, body_bottom),
            color=(0.55, 0.58, 0.55),
            width=0.6,
        )
        page.draw_rect(
            fitz.Rect(right_x0, body_top, right_x1, body_top + 24),
            color=(0.65, 0.68, 0.65),
            fill=(0.91, 0.93, 0.90),
            width=0.6,
        )
        add_label(page, right_x0 + 10, body_top + 16, "Lecture Content & Notes", 9, "hebo")

    # Keep the source slide in the right-hand content area in either mode.
    target = fitz.Rect(
        right_x0 + 5,
        body_top + 29,
        right_x1 - 5,
        body_bottom - 5,
    )

    # Personal notes area (beige) is hidden when the toggle is enabled.
    if not hide_notes:
        sy = PAGE_H - margin - summary_h
        page.draw_rect(
            fitz.Rect(margin, sy, PAGE_W - margin, PAGE_H - margin),
            color=(0.55, 0.58, 0.55),
            fill=(0.98, 0.96, 0.88),
            width=0.6,
        )
        add_label(page, margin + 10, sy + 16, "Personal Notes Area", 9, "hebo")

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
        if not hide_notes:
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

def build_pdf(input_bytes, template, pages_per_sheet=1, crop_whitespace=False, hide_notes=False):
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
                crop_whitespace=crop_whitespace, hide_notes=hide_notes,
            )
        return out.tobytes(garbage=4, deflate=True)
    finally:
        out.close()
        src.close()
