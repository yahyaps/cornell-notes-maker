"""Note templates: each turns a source PDF plus per-slide AI notes into a study PDF.

To add a template:
1. Create a module here with
   build_pdf(source_pdf_bytes, page_notes, pages_per_sheet=1, lecture_title="").
2. Register it in TEMPLATES below; the app lists every registered template.
3. Run scripts/make_template_previews.py to create its thumbnail.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from note_templates import ai_cornell


@dataclass(frozen=True)
class NoteTemplate:
    key: str
    name_en: str
    name_ar: str
    description_en: str
    description_ar: str
    build_pdf: Callable

    @property
    def preview_image(self):
        """Thumbnail made by scripts/make_template_previews.py, if present."""
        path = Path(__file__).resolve().parent.parent / "static" / "previews" / f"{self.key}.png"
        return path if path.exists() else None


TEMPLATES = {
    template.key: template
    for template in (
        NoteTemplate(
            key="ai_cornell",
            name_en="AI Cornell Notes",
            name_ar="ملاحظات كورنيل بالذكاء الاصطناعي",
            description_en=(
                "Arabic explanation and key points beside each original slide, "
                "with a review question and a summary."
            ),
            description_ar=(
                "شرح عربي وأهم النقاط بجانب كل شريحة أصلية، "
                "مع سؤال للمراجعة وخلاصة."
            ),
            build_pdf=ai_cornell.build_pdf,
        ),
    )
}

DEFAULT_TEMPLATE = "ai_cornell"
