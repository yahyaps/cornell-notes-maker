"""End-to-end interface tests: app.py driven by Streamlit's AppTest.

Gemini calls are replaced with mocks, so no network or API key is used.
st.file_uploader cannot be driven by AppTest, so a converted document is placed
in session state (see the `_test_document` note in app.py).
"""

import json
import os
import tomllib
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

import ai_assistant
import usage_limits
from ai_assistant import AIError
from tests.helpers import ROOT, SAMPLE_PDF
from tests.test_ai_cornell_template import note


def sample_doc():
    return {"sig": "test-sig", "name": "Lecture 1.pdf", "pdf": SAMPLE_PDF.read_bytes(),
            "pages": 4, "size": 12345}


def sample_notes(failed=()):
    return [ai_assistant.failed_note(n, "quota") if n in failed else note(n) for n in range(1, 5)]


class AppFlowTest(unittest.TestCase):
    def setUp(self):
        fresh = mock.patch.object(usage_limits, "limiter", usage_limits.UsageLimiter())
        fresh.start()
        self.addCleanup(fresh.stop)

    def start(self, lang="ar", with_doc=True):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        app.query_params["lang"] = lang
        if with_doc:
            app.session_state["doc"] = sample_doc()
            app.session_state["_test_document"] = True
        app.run()
        self.assertFalse(app.exception, app.exception)
        return app

    def texts(self, elements):
        return " ".join(str(e.value) for e in elements)

    # ---- Basic rendering ----
    def test_both_languages_render_without_document(self):
        for lang in ("ar", "en"):
            with self.subTest(lang=lang):
                app = self.start(lang, with_doc=False)
                self.assertTrue(app.info)
                self.assertFalse([b for b in app.button if b.key == "create_notes"])
                self.assertEqual(len(app.tabs), 2)

    def test_language_switch(self):
        app = self.start("ar", with_doc=False)
        app.get("button_group")[0].set_value("en").run()
        self.assertFalse(app.exception)
        self.assertIn("Upload a lecture file", self.texts(app.info))

    # ---- PDF notes ----
    def test_create_notes_then_change_layout_without_new_ai_call(self):
        with mock.patch.object(ai_assistant, "analyze_pages",
                               return_value=sample_notes()) as analyze:
            app = self.start()
            app.button(key="create_notes").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(analyze.call_count, 1)
            self.assertIn("4", self.texts(app.success))
            self.assertTrue(app.get("download_button"))
            app.get("button_group")[1].set_value(1).run()   # one slide per sheet
            self.assertFalse(app.exception, app.exception)
            app.get("button_group")[0].set_value("en").run()  # language switch
            self.assertEqual(analyze.call_count, 1, "layout/language must not re-run AI")

    def test_failed_slides_can_be_retried_alone(self):
        with mock.patch.object(ai_assistant, "analyze_pages",
                               return_value=sample_notes(failed={2})) as analyze:
            app = self.start()
            app.button(key="create_notes").click().run()
            self.assertIn("2", self.texts(app.warning))
            analyze.return_value = [note(2)]
            app.button(key="retry_failed").click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(analyze.call_args.kwargs["pages"], [2])
            self.assertFalse(app.warning)

    def test_ai_error_is_explained_without_traceback(self):
        with mock.patch.object(ai_assistant, "analyze_pages",
                               side_effect=AIError("quota", "x")):
            app = self.start()
            app.button(key="create_notes").click().run()
        self.assertFalse(app.exception)
        self.assertIn("مزدحمة", self.texts(app.error))

    def test_unexpected_error_shows_reference_only(self):
        with mock.patch.object(ai_assistant, "analyze_pages",
                               side_effect=RuntimeError("internal detail")):
            app = self.start("en")
            app.button(key="create_notes").click().run()
        message = self.texts(app.error)
        self.assertIn("Reference", message)
        self.assertNotIn("internal detail", message)

    def test_rate_limit_message(self):
        with mock.patch.object(usage_limits, "AI_RUNS_PER_HOUR", 0), \
                mock.patch.object(ai_assistant, "analyze_pages") as analyze:
            app = self.start("en")
            app.button(key="create_notes").click().run()
        analyze.assert_not_called()
        self.assertIn("request limit", self.texts(app.error))

    # ---- Assistant ----
    def test_study_report(self):
        with mock.patch.object(ai_assistant, "analyze_lecture",
                               return_value="# 1. Lecture Overview\nOK") as report:
            app = self.start()
            app.button(key="analyze_lecture_button").click().run()
        self.assertFalse(app.exception, app.exception)
        self.assertEqual(report.call_args.kwargs["question_count"], 10)
        self.assertIn("Lecture Overview", self.texts(app.markdown))

    def test_chat_question_and_answer(self):
        with mock.patch.object(ai_assistant, "ask_about_lecture",
                               return_value="الإجابة (p. 2)") as ask:
            app = self.start()
            app.chat_input(key="chat_input").set_value("ما الموافقة المستنيرة؟").run()
            self.assertFalse(app.exception, app.exception)
            self.assertEqual(ask.call_count, 1)
            self.assertEqual(len(app.chat_message), 2)
            app.get("button_group")[1].set_value(1).run()   # unrelated rerun
            self.assertEqual(ask.call_count, 1, "a rerun must not resend the question")

    def test_suggestion_is_sent_once(self):
        with mock.patch.object(ai_assistant, "ask_about_lecture",
                               return_value="answer") as ask:
            app = self.start("en")
            pills = [g for g in app.get("button_group") if g.key == "chat_suggestion"][0]
            pills.set_value(pills.options[0]).run()
            self.assertEqual(ask.call_count, 1)
            app.run()
            self.assertEqual(ask.call_count, 1)

    # ---- Access code ----
    def test_access_code_gate(self):
        with mock.patch.dict(os.environ, {"APP_ACCESS_CODE": "open-sesame"}):
            app = self.start("en")
            self.assertFalse([b for b in app.button if b.key == "create_notes"])
            app.text_input[0].input("wrong")
            app.button[0].click().run()
            self.assertIn("Incorrect", self.texts(app.error))
            app.text_input[0].input("open-sesame")
            app.button[0].click().run()
            self.assertFalse(app.exception, app.exception)
            self.assertTrue(app.session_state["access_ok"])


class ConfigTest(unittest.TestCase):
    def test_production_safe_streamlit_config(self):
        config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
        self.assertEqual(config["client"]["showErrorDetails"], "none")
        self.assertFalse(config["browser"]["gatherUsageStats"])
        self.assertTrue(config["server"]["enableXsrfProtection"])
        self.assertLessEqual(config["server"]["maxUploadSize"], 50)


if __name__ == "__main__":
    unittest.main()
