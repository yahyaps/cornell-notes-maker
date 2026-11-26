"""Shared test utilities."""

import threading
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*fitz.*deprecated", category=FutureWarning)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
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
    """Stands in for genai.Client and records every call (thread-safe).

    `responses` is either a list (served in order; the last one repeats) or a
    function contents -> text. A response that is an Exception is raised.
    """

    def __init__(self, responses):
        self._responses = responses if callable(responses) else list(responses)
        self._lock = threading.Lock()
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config=None):
        with self._lock:
            self.calls.append({"model": model, "contents": contents, "config": config})
            if callable(self._responses):
                result = self._responses(contents)
            elif len(self._responses) > 1:
                result = self._responses.pop(0)
            else:
                result = self._responses[0]
        if isinstance(result, Exception):
            raise result
        return type("Response", (), {"text": result})()
