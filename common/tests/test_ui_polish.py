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
