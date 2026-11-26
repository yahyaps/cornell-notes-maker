"""Generate the synthetic lecture used by the test suite.

Run once with `python tests/make_fixtures.py`. The output is committed so
golden-image tests stay stable even if PyMuPDF's drawing changes.
"""

from pathlib import Path

import pymupdf

FIXTURES = Path(__file__).parent / "fixtures"
ARABIC_FONT = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"

SLIDES = [
    ("Bioethics: Core Principles", [
        "Autonomy - respect the patient's right to decide",
        "Beneficence - act in the patient's best interest",
        "Non-maleficence - first, do no harm",
        "Justice - fair distribution of care",
    ]),
    ("Informed Consent", [
        "Disclosure of risks and benefits",
        "Patient capacity (competence)",
        "Voluntariness - no coercion",
        "Documentation in the medical record",
    ]),
    ("Pharmacokinetics (ADME)", [
        "Absorption -> Distribution -> Metabolism -> Excretion",
        "Half-life t1/2 = 0.693 x Vd / CL",
        "First-pass effect reduces oral bioavailability",
    ]),
]


def add_slide(doc, title, bullets, number):
    page = doc.new_page(width=720, height=405)  # 16:9 slide
    page.draw_rect(page.rect, fill=(0.97, 0.98, 1.0), color=None)
    page.draw_rect(pymupdf.Rect(0, 0, 720, 64), fill=(0.16, 0.29, 0.52), color=None)
    page.insert_text((32, 42), title, fontsize=26, fontname="hebo", color=(1, 1, 1))
    y = 110
    for bullet in bullets:
        page.insert_text((48, y), "- " + bullet, fontsize=17, fontname="helv")
        y += 40
    page.draw_circle((660, 340), 26, fill=(0.85, 0.45, 0.2), color=None)
    page.insert_text((650, 378), str(number), fontsize=12, fontname="helv")


def add_arabic_page(doc):
    # Portrait page with a large empty margin, like a Word export.
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="noto", fontfile=ARABIC_FONT)
    page.insert_htmlbox(
        pymupdf.Rect(60, 120, 535, 420),
        "<div dir='rtl' style='font-size:15px'>"
        "<h2>الموافقة المستنيرة (Informed Consent)</h2>"
        "<p>يجب على الصيدلي شرح المخاطر والفوائد للمريض قبل بدء العلاج، "
        "مع احترام مبدأ الاستقلالية (Autonomy).</p></div>",
        css=f"* {{font-family: noto;}} @font-face {{font-family: noto; src: url({ARABIC_FONT});}}",
    )


def main():
    FIXTURES.mkdir(exist_ok=True)
    doc = pymupdf.open()
    for number, (title, bullets) in enumerate(SLIDES, start=1):
        add_slide(doc, title, bullets, number)
    add_arabic_page(doc)
    doc.set_metadata({"title": "Synthetic test lecture", "creationDate": "", "modDate": ""})
    out = FIXTURES / "sample_lecture.pdf"
    doc.save(out, garbage=4, deflate=True, no_new_id=True)
    print(f"wrote {out} ({doc.page_count} pages)")


if __name__ == "__main__":
    main()
