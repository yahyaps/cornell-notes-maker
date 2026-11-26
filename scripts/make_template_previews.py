"""Render the template thumbnails shown in the app (static/previews/<key>.png).

    python scripts/make_template_previews.py

Uses the synthetic test lecture with hand-written sample notes, so no AI call
and no private material is involved.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from note_templates import TEMPLATES  # noqa: E402

SAMPLE_NOTES = [
    {
        "source_page": 1,
        "title": "Bioethics: Core Principles",
        "explanation_ar": (
            "تعرض الشريحة المبادئ الأربعة الأساسية للأخلاقيات الحيوية (Bioethics). "
            "الاستقلالية (Autonomy) تعني احترام حق المريض في اتخاذ قراره، "
            "والإحسان (Beneficence) هو العمل لمصلحة المريض، وعدم الإضرار "
            "(Non-maleficence) يعني تجنب الأذى أولًا، أما العدالة (Justice) "
            "فهي التوزيع العادل للرعاية."
        ),
        "key_points": [
            "الاستقلالية (Autonomy): القرار للمريض بعد فهمه للخيارات.",
            "الإحسان (Beneficence): التصرف بما يحقق المصلحة الفضلى للمريض.",
            "عدم الإضرار (Non-maleficence): أولًا، لا تُلحق ضررًا.",
            "العدالة (Justice): توزيع عادل للموارد والرعاية.",
        ],
        "review_question_ar": "أي مبدأ يقوم على قاعدة «أولًا، لا تُلحق ضررًا»؟",
        "summary_ar": "أربعة مبادئ توجّه القرار الطبي: الاستقلالية، والإحسان، وعدم الإضرار، والعدالة.",
    },
    {
        "source_page": 2,
        "title": "Informed Consent",
        "explanation_ar": (
            "الموافقة المستنيرة (Informed Consent) شرط قبل أي علاج. تتطلب الإفصاح "
            "عن المخاطر والفوائد (Disclosure)، والتأكد من أهلية المريض (Capacity)، "
            "وأن تكون الموافقة طوعية دون إكراه (Voluntariness)، ثم توثيقها في السجل الطبي."
        ),
        "key_points": [
            "الإفصاح الكامل عن المخاطر والفوائد والبدائل.",
            "أهلية المريض (Capacity) لفهم المعلومات واتخاذ القرار.",
            "الطوعية (Voluntariness): لا ضغط ولا إكراه.",
        ],
        "review_question_ar": "ما العناصر الأربعة للموافقة المستنيرة (Informed Consent)؟",
        "summary_ar": "موافقة صحيحة = إفصاح + أهلية + طوعية + توثيق.",
    },
]


def main():
    source = (ROOT / "tests" / "fixtures" / "sample_lecture.pdf").read_bytes()
    out_dir = ROOT / "static" / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, template in TEMPLATES.items():
        pdf = template.build_pdf(source, SAMPLE_NOTES, pages_per_sheet=2,
                                 lecture_title="Bioethics-I")
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:
            path = out_dir / f"{key}.png"
            doc[0].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), alpha=False).save(path)
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
