import os

import fitz
from google import genai


MODEL_NAME = "gemini-3.8-flash"
MAX_INPUT_CHARS = 60000

# Structured output: Gemini must answer each slide with this JSON shape.
SLIDE_NOTES_CONFIG = genai.types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema={
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "explanation_ar": {"type": "STRING"},
            "key_points": {"type": "ARRAY", "items": {"type": "STRING"}},
            "review_question_ar": {"type": "STRING"},
            "summary_ar": {"type": "STRING"},
        },
        "required": [
            "title", "explanation_ar", "key_points",
            "review_question_ar", "summary_ar",
        ],
    },
)


def get_gemini_client():
    """Create a Gemini client without hardcoding API credentials."""
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("GEMINI_API_KEY")
        except (FileNotFoundError, KeyError, RuntimeError):
            api_key = None

    if not api_key:
        raise ValueError(
            "Gemini API key is missing. Configure GEMINI_API_KEY "
            "in Streamlit secrets or environment variables."
        )

    return genai.Client(api_key=api_key)


def extract_pdf_text(pdf_bytes):
    """Extract selectable text from a PDF while preserving page numbers."""
    pages = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        for index, page in enumerate(document):
            text = page.get_text("text").strip()

            if text:
                pages.append(
                    f"\n--- SOURCE PAGE {index + 1} ---\n{text}"
                )

    result = "\n".join(pages).strip()

    if not result:
        raise ValueError(
            "No selectable text was found in this PDF. "
            "Scanned or image-only slides need OCR or image analysis."
        )

    return result[:MAX_INPUT_CHARS]


def analyze_lecture(pdf_bytes, question_count=10):
    """Generate Arabic study notes and English MCQs from extracted PDF text."""
    if not 5 <= question_count <= 20:
        raise ValueError("Question count must be between 5 and 20.")

    lecture_text = extract_pdf_text(pdf_bytes)
    client = get_gemini_client()

    prompt = f"""
You are an educational assistant helping a university student study
from an uploaded lecture.

Use ONLY the source content provided below for lecture-specific facts.
Do not invent facts, doses, mechanisms, or recommendations.
If information is missing or unclear, explicitly say so.

Write the explanation in clear Arabic. Keep important scientific,
medical, and pharmacological terms in English in parentheses.

Use this exact structure:

# 1. Lecture Overview
Briefly identify the main subject and learning themes.

# 2. شرح المحاضرة
Explain the source content in Arabic, organized by topic.
Preserve important English terminology.
Refer to source page numbers when possible.

# 3. High-Yield Points
List the most important study points supported by the source.
Do not claim that any point will definitely appear on an exam.

# 4. Visual Learning Plans
Suggest up to three useful diagrams or mind maps.
For each, provide an English title and a concise node-and-arrow
structure in English. Do not claim an image was generated.

# 5. Multiple-Choice Questions
Create exactly {question_count} MCQs in English.
Each question must have four options (A-D), one best answer,
and an explanation in Arabic.
Base every answer on the source. If the source does not support
a question, do not ask it.

# 6. Source Limitations
Mention any missing, unclear, or potentially incomplete source content.

SOURCE LECTURE:
{lecture_text}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    result = (response.text or "").strip()
    if not result:
        raise RuntimeError("Gemini returned an empty response.")

    return result


def analyze_pages(pdf_bytes, max_pages=None):
    """
    Analyze each PDF page separately.
    Returns structured data for the educational PDF generator.
    """
    client = get_gemini_client()
    results = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
        page_count = document.page_count

        if max_pages is not None:
            page_count = min(page_count, max_pages)

        for index in range(page_count):
            page = document[index]
            page_text = page.get_text("text").strip()

            # Provide a rendered page image so image-based slides can
            # still be analyzed when selectable text is unavailable.
            pix = page.get_pixmap(
                matrix=fitz.Matrix(1.5, 1.5),
                alpha=False,
            )
            image_bytes = pix.tobytes("png")

            prompt = f"""
You are helping a university student study a lecture slide.

Analyze ONLY this slide. Do not invent information.
If the slide is unclear or lacks enough information, say so.
Write the explanation in clear Arabic and retain important
medical/scientific terms in English.

Return valid JSON only, using exactly these keys:
{{
  "title": "short slide title in English",
  "explanation_ar": "clear Arabic explanation",
  "key_points": [
    "important point supported by this slide"
  ],
  "review_question_ar": "one Arabic self-test question about this slide",
  "summary_ar": "one Arabic sentence summarizing this slide"
}}

Rules:
- Provide 2 to 5 key points when the slide supports them.
- Write key points in Arabic, keeping technical terms in English.
- Keep the explanation concise enough to fit a side panel
  (about 60 to 150 words).
- Put each English term in parentheses right after its Arabic
  meaning, e.g. "الموافقة المستنيرة (Informed Consent)".
- The review question must be answerable from this slide alone.
- For a title, agenda, or reference slide, keep every field brief.
- Do not predict exact exam questions.
- Do not include Markdown fences or any text outside JSON.

Extracted slide text:
{page_text[:12000] if page_text else "[No selectable text found; analyze the slide image.]"}
"""

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    prompt,
                    genai.types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/png",
                    ),
                ],
                config=SLIDE_NOTES_CONFIG,
            )

            raw = (response.text or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw[:-3].strip()

            import json
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Gemini returned invalid JSON for source page {index + 1}: "
                    f"{raw[:300]}"
                ) from exc

            results.append({
                "source_page": index + 1,
                "title": str(data.get("title") or f"Slide {index + 1}"),
                "explanation_ar": str(data.get("explanation_ar") or ""),
                "key_points": [
                    str(point)
                    for point in data.get("key_points", [])
                ],
                "review_question_ar": str(data.get("review_question_ar") or ""),
                "summary_ar": str(data.get("summary_ar") or ""),
                "_image_bytes": image_bytes,
            })

    return results
