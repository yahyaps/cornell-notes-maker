"""Shared test utilities."""

import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*fitz.*deprecated", category=FutureWarning)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"
OUTPUT = ROOT / "tests" / "output"
SAMPLE_PDF = FIXTURES / "sample_lecture.pdf"


class FakeUpload:
    """Mimics Streamlit's UploadedFile for code that only needs name/getvalue."""

    def __init__(self, name, data):
        self.name = name
        self._data = data
        self.size = len(data)

    def getvalue(self):
        return self._data


class FakeGemini:
    """Stands in for genai.Client; returns queued responses and records calls."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.models = self

    def generate_content(self, model, contents):
        self.calls.append({"model": model, "contents": contents})
        text = self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        return type("Response", (), {"text": text})()
