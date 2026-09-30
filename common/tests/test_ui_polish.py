from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "common" / "dolphin-app.js"
APP_CSS = ROOT / "static" / "common" / "dolphin.css"


class UiPolishTests(SimpleTestCase):
    def test_no_native_confirm_dialogs(self):
        source = APP_JS.read_text(encoding="utf-8")
        self.assertNotIn("window.confirm(", source)
        self.assertIn("function confirmDialog(", source)
    def test_loading_placeholders_and_busy_buttons(self):
        css = APP_CSS.read_text(encoding="utf-8")
        self.assertIn('[id$="-loading"]:not([hidden])', css)
        self.assertIn('.btn[aria-busy="true"]', css)
        self.assertIn("function setupBusyButtons(", APP_JS.read_text(encoding="utf-8"))


    def test_motion_tokens_and_reduced_motion(self):
        css = APP_CSS.read_text(encoding="utf-8")
        for token in ("--dolphin-dur-fast:", "--dolphin-dur:", "--dolphin-ease:"):
            self.assertIn(token, css)
        source = APP_JS.read_text(encoding="utf-8")
        self.assertNotIn("behavior: \"smooth\"", source)
        self.assertIn("function motionBehavior(", source)


    def test_header_badges_use_the_shared_visible_only_poll(self):
        source = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function keepBadgeFresh(", source)
        self.assertEqual(source.count("keepBadgeFresh({"), 2)
        self.assertNotIn("setInterval(pollCount", source)

