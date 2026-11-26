"""Run app.py headlessly with Streamlit's AppTest and check every screen loads."""

import unittest

from streamlit.testing.v1 import AppTest

from tests.helpers import ROOT


class AppSmokeTest(unittest.TestCase):
    def start(self):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.run()
        self.assertFalse(app.exception, app.exception)
        return app

    def test_both_languages_and_layouts_render(self):
        app = self.start()
        for language in ("en", "ar"):
            app.selectbox(key="language_selector").set_value(language).run()
            for pages_per_sheet in (1, 2):
                with self.subTest(language=language, pages_per_sheet=pages_per_sheet):
                    app.radio(key="pages_per_sheet_choice").set_value(pages_per_sheet).run()
                    self.assertFalse(app.exception, app.exception)

    def test_ai_buttons_warn_without_upload(self):
        app = self.start()
        app.button(key="create_ai_lecture_notes_button").click().run()
        self.assertTrue(app.warning, "AI notes should ask for a file first")
        app.button(key="analyze_lecture_button").click().run()
        self.assertTrue(app.warning, "AI Assistant should ask for a file first")
        self.assertFalse(app.exception, app.exception)


if __name__ == "__main__":
    unittest.main()
