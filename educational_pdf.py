import io

import os

import textwrap



import fitz

from PIL import Image, ImageDraw, ImageFont





PAGE_W = 1191

PAGE_H = 842

MARGIN = 32

GAP = 24



BACKGROUND = "#FFFFFF"

PANEL = "#F5F7F6"

BORDER = "#D7DFDA"

TEXT = "#26332D"

MUTED = "#66756D"

ACCENT = "#4D7D67"







def find_arabic_font():

    path = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"

    if not os.path.exists(path):

        raise FileNotFoundError("Noto Sans Arabic font not found.")

    return path





def find_english_font():

    path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    if not os.path.exists(path):

        raise FileNotFoundError("DejaVu Sans font not found.")

    return path







def load_font(path, size):

    return ImageFont.truetype(

        path,

        size=size,

        layout_engine=ImageFont.Layout.RAQM,

    )





def wrap_text(draw, text, font, max_width, direction="rtl"):

    """Wrap text by measured pixel width, preserving mixed-language text."""

    lines = []



    for paragraph in str(text).splitlines() or [""]:

        if not paragraph.strip():

            lines.append("")

            continue



        words = paragraph.split()

        current = ""



        for word in words:

            candidate = f"{current} {word}".strip()

            bbox = draw.textbbox(

                (0, 0),

                candidate,

                font=font,

                direction=direction,

                language="ar" if direction == "rtl" else "en",

            )

            width = bbox[2] - bbox[0]



            if width <= max_width or not current:

                current = candidate

            else:

                lines.append(current)

                current = word



        if current:

            lines.append(current)



    return lines





def draw_mixed_text(

    draw,

    text,

    x,

    y,

    max_width,

    arabic_font,

    english_font,

    fill=TEXT,

    line_gap=7,

):

    """Draw mixed Arabic/English text using separate fonts for each run."""

    import re



    token_pattern = re.compile(

        r"[A-Za-z][A-Za-z0-9+./()\-]*"

        r"|[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+"

        r"|[0-9]+(?:.[0-9]+)?"

        r"|[^\s]",

    )

    tokens = token_pattern.findall(str(text))

    lines = []

    current = []

    current_width = 0



    for token in tokens:

        font = (

            english_font

            if re.fullmatch(r"[A-Za-z0-9+./()\-]+", token)

            else arabic_font

        )

        box = draw.textbbox((0, 0), token, font=font)

        token_width = box[2] - box[0]

        space_width = draw.textlength(" ", font=font)



        if current and current_width + space_width + token_width > max_width:

            lines.append(current)

            current = []

            current_width = 0



        current.append((token, font))

        current_width += token_width + space_width



    if current:

        lines.append(current)



    for line in lines:

        cursor_x = x + max_width

        line_height = 0



        for token, font in line:

            box = draw.textbbox((0, 0), token, font=font)

            token_width = box[2] - box[0]

            line_height = max(line_height, box[3] - box[1])



            cursor_x -= token_width

            draw.text(

                (cursor_x, y),

                token,

                font=font,

                fill=fill,

            )

            cursor_x -= draw.textlength(" ", font=font)



        y += line_height + line_gap



    return y





def draw_wrapped_text(

    draw,

    text,

    x,

    y,

    max_width,

    font,

    fill=TEXT,

    direction="rtl",

    line_gap=7,

):

    arabic_font = font

    english_font = load_font(find_english_font(), font.size)



    return draw_mixed_text(

        draw=draw,

        text=text,

        x=x,

        y=y,

        max_width=max_width,

        arabic_font=arabic_font,

        english_font=english_font,

        fill=fill,

        line_gap=line_gap,

    )





def make_educational_pdf(source_pdf_bytes, page_notes):

    """

    Create a landscape PDF with each original source page beside its notes.



    page_notes example:

    [

        {

            "source_page": 1,

            "title": "Cell Membrane",

            "explanation_ar": "شرح مبسط للمفهوم...",

            "key_points": ["Point one", "Point two"],

        }

    ]



    source_page uses 1-based page numbering.

    """

    if not page_notes:

        raise ValueError("No page explanations were supplied.")



    arabic_font_path = find_arabic_font()

    english_font_path = find_english_font()



    title_font = load_font(english_font_path, 25)

    heading_font = load_font(english_font_path, 19)

    body_font = load_font(arabic_font_path, 16)

    small_font = load_font(english_font_path, 12)



    output = fitz.open()



    try:

        with fitz.open(

            stream=source_pdf_bytes,

            filetype="pdf",

        ) as source:

            for item in page_notes:

                source_number = int(item["source_page"])



                if not 1 <= source_number <= source.page_count:

                    raise ValueError(

                        f"Invalid source page: {source_number}"

                    )



                canvas = Image.new(

                    "RGB",

                    (PAGE_W, PAGE_H),

                    BACKGROUND,

                )

                draw = ImageDraw.Draw(canvas)



                draw.text(

                    (PAGE_W - MARGIN, 25),

                    "LECTURE STUDY GUIDE",

                    font=small_font,

                    fill=ACCENT,

                    anchor="ra",

                    direction="ltr",

                )



                title = str(item.get("title") or f"Source Page {source_number}")

                draw_wrapped_text(

                    draw,

                    title,

                    MARGIN,

                    54,

                    PAGE_W - 2 * MARGIN,

                    title_font,

                    fill=TEXT,

                    direction="ltr",

                )



                top = 115

                bottom = PAGE_H - MARGIN

                panel_h = bottom - top

                usable_w = PAGE_W - 2 * MARGIN

                panel_w = (usable_w - GAP) // 2



                left_x = MARGIN

                right_x = MARGIN + panel_w + GAP



                left_rect = (

                    left_x,

                    top,

                    left_x + panel_w,

                    top + panel_h,

                )

                right_rect = (

                    right_x,

                    top,

                    right_x + panel_w,

                    top + panel_h,

                )



                draw.rounded_rectangle(

                    left_rect,

                    radius=14,

                    fill=PANEL,

                    outline=BORDER,

                    width=2,

                )

                draw.rounded_rectangle(

                    right_rect,

                    radius=14,

                    fill=PANEL,

                    outline=BORDER,

                    width=2,

                )



                draw.text(

                    (left_x + panel_w - 18, top + 18),

                    f"ORIGINAL SLIDE · {source_number}",

                    font=small_font,

                    fill=MUTED,

                    anchor="ra",

                    direction="ltr",

                )



                source_page = source[source_number - 1]

                pix = source_page.get_pixmap(

                    matrix=fitz.Matrix(1.5, 1.5),

                    alpha=False,

                )

                source_image = Image.open(

                    io.BytesIO(pix.tobytes("png"))

                ).convert("RGB")



                image_box = (

                    left_x + 14,

                    top + 50,

                    left_x + panel_w - 14,

                    top + panel_h - 14,

                )

                box_w = image_box[2] - image_box[0]

                box_h = image_box[3] - image_box[1]



                source_image.thumbnail((box_w, box_h))

                image_x = image_box[0] + (box_w - source_image.width) // 2

                image_y = image_box[1] + (box_h - source_image.height) // 2



                canvas.paste(source_image, (image_x, image_y))



                text_x = right_x + 18

                text_w = panel_w - 36

                y = top + 18



                draw.text(

                    (right_x + panel_w - 18, y),

                    "AI EXPLANATION",

                    font=heading_font,

                    fill=ACCENT,

                    anchor="ra",

                    direction="ltr",

                )

                y += 38



                y = draw_wrapped_text(

                    draw,

                    item.get("explanation_ar", ""),

                    text_x,

                    y,

                    text_w,

                    body_font,

                    direction="rtl",

                )



                points = item.get("key_points") or []

                if points:

                    y += 18

                    draw.text(

                        (right_x + panel_w - 18, y),

                        "HIGH-YIELD POINTS",

                        font=heading_font,

                        fill=ACCENT,

                        anchor="ra",

                        direction="ltr",

                    )

                    y += 34



                    for point in points:

                        y = draw_wrapped_text(

                            draw,

                            f"• {point}",

                            text_x,

                            y,

                            text_w,

                            body_font,

                            direction="rtl",

                        )

                        y += 5



                draw.text(

                    (PAGE_W // 2, PAGE_H - 12),

                    f"Study Guide · Source page {source_number}",

                    font=small_font,

                    fill=MUTED,

                    anchor="ms",

                    direction="ltr",

                )



                buffer = io.BytesIO()

                canvas.save(buffer, format="PNG")



                pdf_page = output.new_page(

                    width=841.89,

                    height=595.28,

                )

                pdf_page.insert_image(

                    pdf_page.rect,

                    stream=buffer.getvalue(),

                )



        return output.tobytes(

            garbage=4,

            deflate=True,

        )

    finally:

        output.close()


def make_ai_lecture_notes_pdf(
    source_pdf_bytes,
    page_notes,
    pages_per_sheet=1,
):
    """
    Create an A4 portrait PDF with AI explanation on the left
    and the matching original slide on the right.

    `page_notes` is the structured output returned by
    ai_assistant.analyze_pages().
    """
    if not page_notes:
        raise ValueError("No AI explanations were supplied.")

    if pages_per_sheet not in (1, 2):
        raise ValueError("Choose 1 or 2 source slides per sheet.")

    arabic_font_path = find_arabic_font()
    english_font_path = find_english_font()

    # Pixel canvas sized proportionally to A4 portrait.
    canvas_w, canvas_h = 842, 1191
    margin = 28
    gap = 16
    header_h = 82
    footer_h = 24
    row_gap = 16

    title_font = load_font(english_font_path, 24)
    heading_font = load_font(english_font_path, 16)
    body_font = load_font(arabic_font_path, 17)
    small_font = load_font(english_font_path, 12)

    output = fitz.open()

    try:
        with fitz.open(stream=source_pdf_bytes, filetype="pdf") as source:
            for start in range(0, len(page_notes), pages_per_sheet):
                batch = page_notes[start:start + pages_per_sheet]
                canvas = Image.new("RGB", (canvas_w, canvas_h), BACKGROUND)
                draw = ImageDraw.Draw(canvas)

                draw.text(
                    (canvas_w - margin, 24),
                    "AI LECTURE NOTES",
                    font=title_font,
                    fill=ACCENT,
                    anchor="ra",
                    direction="ltr",
                )
                draw.line(
                    (margin, 62, canvas_w - margin, 62),
                    fill=BORDER,
                    width=3,
                )

                content_top = margin + header_h
                content_bottom = canvas_h - margin - footer_h
                usable_h = content_bottom - content_top
                row_h = (usable_h - row_gap * (len(batch) - 1)) // len(batch)

                usable_w = canvas_w - 2 * margin
                panel_w = (usable_w - gap) // 2

                # Template 2 layout: explanation LEFT, original slide RIGHT.
                left_x = margin
                right_x = margin + panel_w + gap

                for row_index, item in enumerate(batch):
                    source_number = int(item["source_page"])
                    if not 1 <= source_number <= source.page_count:
                        raise ValueError(f"Invalid source page: {source_number}")

                    y0 = content_top + row_index * (row_h + row_gap)
                    y1 = y0 + row_h

                    left_rect = (left_x, y0, left_x + panel_w, y1)
                    right_rect = (right_x, y0, right_x + panel_w, y1)

                    for rect in (left_rect, right_rect):
                        draw.rounded_rectangle(
                            rect,
                            radius=14,
                            fill=PANEL,
                            outline=BORDER,
                            width=2,
                        )

                    draw.text(
                        (left_x + panel_w - 14, y0 + 16),
                        "AI EXPLANATION",
                        font=heading_font,
                        fill=ACCENT,
                        anchor="ra",
                        direction="ltr",
                    )
                    draw.text(
                        (right_x + panel_w - 14, y0 + 16),
                        f"ORIGINAL SLIDE · {source_number}",
                        font=small_font,
                        fill=MUTED,
                        anchor="ra",
                        direction="ltr",
                    )

                    # Render the original source page into the right panel.
                    pix = source[source_number - 1].get_pixmap(
                        matrix=fitz.Matrix(1.5, 1.5),
                        alpha=False,
                    )
                    source_image = Image.open(
                        io.BytesIO(pix.tobytes("png"))
                    ).convert("RGB")

                    image_box = (
                        right_x + 12,
                        y0 + 42,
                        right_x + panel_w - 12,
                        y1 - 12,
                    )
                    box_w = image_box[2] - image_box[0]
                    box_h = image_box[3] - image_box[1]
                    source_image.thumbnail((box_w, box_h))
                    image_x = image_box[0] + (box_w - source_image.width) // 2
                    image_y = image_box[1] + (box_h - source_image.height) // 2
                    canvas.paste(source_image, (image_x, image_y))

                    # Explanation and key points on the left.
                    text_x = left_x + 14
                    text_w = panel_w - 28
                    y = y0 + 44
                    text_bottom = y1 - 12

                    explanation = str(item.get("explanation_ar") or "").strip()
                    y = draw_wrapped_text(
                        draw,
                        explanation,
                        text_x,
                        y,
                        text_w,
                        body_font,
                        fill=TEXT,
                        direction="rtl",
                        line_gap=5,
                    )

                    points = item.get("key_points") or []
                    if points and y < text_bottom - 24:
                        y += 10
                        draw.text(
                            (left_x + panel_w - 14, y),
                            "HIGH-YIELD POINTS",
                            font=small_font,
                            fill=ACCENT,
                            anchor="ra",
                            direction="ltr",
                        )
                        y += 24

                        for point in points:
                            if y >= text_bottom:
                                break
                            y = draw_wrapped_text(
                                draw,
                                f"• {point}",
                                text_x,
                                y,
                                text_w,
                                body_font,
                                fill=TEXT,
                                direction="rtl",
                                line_gap=4,
                            )
                            y += 3

                page_number = start // pages_per_sheet + 1
                draw.text(
                    (canvas_w // 2, canvas_h - 12),
                    f"AI Lecture Notes · Page {page_number}",
                    font=small_font,
                    fill=MUTED,
                    anchor="ms",
                    direction="ltr",
                )

                buffer = io.BytesIO()
                canvas.save(buffer, format="PNG")
                pdf_page = output.new_page(width=595.28, height=841.89)
                pdf_page.insert_image(pdf_page.rect, stream=buffer.getvalue())

        return output.tobytes(garbage=4, deflate=True)
    finally:
        output.close()
