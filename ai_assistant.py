import os

import fitz
from google import genai


MODEL_NAME = "gemini-3.8-flash"
MAX_INPUT_CHARS = 60000


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
  ]
}}

Rules:
- Provide 2 to 5 key points when the slide supports them.
- Keep the explanation concise enough to fit a side panel.
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
                "_image_bytes": image_bytes,
            })

    return results


def generate_study_extras(pdf_bytes, question_count=10):
    """Generate structured diagrams and MCQs from the full lecture."""
    import json

    if not isinstance(question_count, int) or question_count < 1:
        raise ValueError("question_count must be a positive integer.")

    lecture_text = extract_pdf_text(pdf_bytes)

    client = get_gemini_client()

    prompt = f"""
You are an academic learning-design assistant.

Analyze the lecture and decide which visual aids, if any, would
meaningfully improve student understanding and recall.

Use ONLY information supported by the source lecture.
Never invent facts, relationships, values, or medical knowledge.

Return valid JSON only with exactly these keys:

{{
  "visual_decisions": [
    {{
      "visual_id": "unique-id-1",
      "topic": "English topic or slide range",
      "visual_needed": true,
      "visual_type": "concept_map | flowchart | comparison_table | mechanism_diagram | timeline | none",
      "reason": "Brief explanation in English",
      "source_evidence": ["Relevant concepts explicitly supported by the lecture"]
    }}
  ],
  "diagrams": [
    {{
      "visual_id": "unique-id-1",
      "title": "English title",
      "nodes": ["English concept 1", "English concept 2"],
      "arrows": [
        {{"from": "English concept 1", "to": "English concept 2",
          "label": "short, clear relationship"}}
      ]
    }}
  ],
  "mcqs": [
    {{
      "question": "Question in English",
      "options": {{
        "A": "Option A",
        "B": "Option B",
        "C": "Option C",
        "D": "Option D"
      }},
      "correct_answer": "A",
      "explanation_ar": "تفسير الإجابة باللغة العربية مستند إلى المصدر"
    }}
  ],
  "source_limitations": ["Missing or unclear source information"]
}}

Visual selection rules:
- Evaluate the lecture content before choosing any visual.
- A visual is optional. Zero visuals is a valid result.
- Use a visual only when it clarifies relationships, sequences,
  comparisons, mechanisms, or complex classifications.
- Do not create a visual merely to decorate a title slide,
  a simple definition, a reference slide, or already-clear content.
- Choose the most suitable visual type for the source content.
- Use comparison_table when comparing items across shared criteria.
- Use flowchart for ordered steps or processes.
- Use mechanism_diagram for supported causal or mechanistic links.
- Use concept_map for meaningful relationships among concepts.
- Do not create tables or diagrams when the source lacks enough
  information to populate them accurately.
- Create at most 3 visuals for the entire lecture.
- Give every visual decision a unique, stable visual_id, such as
  "visual-1" or "visual-2".
- Copy the exact same visual_id into the corresponding diagram object.
- Never reuse a visual_id for different visuals.
- A diagram must match its approved decision using visual_id,
  not by matching the topic and title text.
- Do not include a diagram unless its matching decision has
  visual_needed=true and a supported diagram visual_type.
- Only include a diagram in "diagrams" when its corresponding
  decision has visual_needed=true and visual_type is a diagram type.
- Do not represent a comparison table as a node-and-arrow diagram.
  If a table is needed, record that decision; do not fabricate it
  using the diagram schema.
- Keep relationship labels concise to reduce visual clutter.
- Diagram titles, nodes, and relationship labels must be in English.
- Every relationship must be explicitly supported by the source.
- If the source does not support a relationship, omit it.

MCQ rules:
- Create exactly {question_count} MCQs only if the source supports them.
- Each question must have exactly four options: A, B, C, and D.
- Each question must have one best answer supported by the source.
- Explain every correct answer in Arabic using the source content.
- If the source cannot support {question_count} valid questions,
  return fewer questions and explain this limitation in source_limitations.

Source limitation rules:
- Mention missing, unclear, or incomplete source content.
- Do not infer details from references or tables not included in the source.
- Do not use Markdown fences or text outside the JSON object.

SOURCE LECTURE:
{lecture_text}
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    raw = (response.text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    if not raw:
        raise RuntimeError("Gemini returned an empty response.")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Gemini returned invalid JSON: {raw[:300]}"
        ) from exc

    diagrams = data.get("diagrams", [])
    mcqs = data.get("mcqs", [])
    visual_decisions = data.get("visual_decisions", [])
    source_limitations = data.get("source_limitations", [])

    if (
        not isinstance(diagrams, list)
        or not isinstance(mcqs, list)
        or not isinstance(visual_decisions, list)
        or not isinstance(source_limitations, list)
    ):
        raise ValueError("Gemini returned an invalid data structure.")

    valid_visual_types = {
        "concept_map",
        "flowchart",
        "comparison_table",
        "mechanism_diagram",
        "timeline",
        "none",
    }

    seen_visual_ids = set()

    for index, decision in enumerate(visual_decisions, start=1):
        if not isinstance(decision, dict):
            raise ValueError(
                f"Invalid visual decision at item {index}."
            )

        visual_id = decision.get("visual_id")
        if not isinstance(visual_id, str) or not visual_id.strip():
            raise ValueError(
                f"Missing or invalid visual_id at item {index}."
            )

        visual_id = visual_id.strip()
        if visual_id in seen_visual_ids:
            raise ValueError(
                f"Duplicate visual_id '{visual_id}' at item {index}."
            )
        seen_visual_ids.add(visual_id)

        visual_type = decision.get("visual_type")
        if visual_type not in valid_visual_types:
            raise ValueError(
                f"Invalid visual type at item {index}."
            )

        visual_needed = decision.get("visual_needed")
        if not isinstance(visual_needed, bool):
            raise ValueError(
                f"visual_needed must be boolean at item {index}."
            )

        if visual_needed and visual_type == "none":
            raise ValueError(
                f"Decision {visual_id}: visual_needed cannot be true "
                "when visual_type is 'none'."
            )

        if not visual_needed and visual_type != "none":
            raise ValueError(
                f"Decision {visual_id}: use visual_type='none' "
                "when visual_needed is false."
            )

    diagram_types = {"concept_map", "flowchart"}
    approved_diagrams = {
        decision["visual_id"]: decision
        for decision in visual_decisions
        if decision["visual_needed"]
        and decision["visual_type"] in diagram_types
    }

    seen_diagram_ids = set()

    for index, diagram in enumerate(diagrams, start=1):
        if not isinstance(diagram, dict):
            raise ValueError(
                f"Invalid diagram structure at item {index}."
            )

        visual_id = diagram.get("visual_id")
        if not isinstance(visual_id, str) or not visual_id.strip():
            raise ValueError(
                f"Missing or invalid diagram visual_id at item {index}."
            )

        visual_id = visual_id.strip()

        if visual_id in seen_diagram_ids:
            raise ValueError(
                f"Duplicate diagram visual_id '{visual_id}'."
            )
        seen_diagram_ids.add(visual_id)

        decision = approved_diagrams.get(visual_id)
        if decision is None:
            raise ValueError(
                f"Diagram '{visual_id}' has no matching approved "
                "concept_map or flowchart decision."
            )

    for visual_id in approved_diagrams:
        if visual_id not in seen_diagram_ids:
            raise ValueError(
                f"Approved diagram decision '{visual_id}' has no "
                "corresponding diagram."
            )

    for index, question in enumerate(mcqs, start=1):
        if not isinstance(question, dict):
            raise ValueError(f"Invalid MCQ structure at question {index}.")

        options = question.get("options", {})
        if (
            not isinstance(options, dict)
            or set(options.keys()) != {"A", "B", "C", "D"}
            or question.get("correct_answer") not in {"A", "B", "C", "D"}
        ):
            raise ValueError(f"Invalid MCQ structure at question {index}.")

    return {
        "visual_decisions": visual_decisions,
        "diagrams": diagrams[:3],
        "mcqs": mcqs,
        "source_limitations": source_limitations,
    }