"""Multi-choice controls are checklists, never «hold Ctrl» (2.39.7)."""

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "common" / "templates" / "common"
SCRIPTS = ROOT / "common" / "static" / "common" / "js"


class ChecklistTests(SimpleTestCase):
    def test_no_user_facing_template_tells_people_to_hold_ctrl(self):
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Ctrl را نگه دارید", text, path)
            self.assertNotIn("کلید Ctrl", text, path)

    def test_the_two_multiple_selects_are_enhanced_into_checklists(self):
        multiple = sorted(
            path.name for path in TEMPLATES.rglob("*.html")
            if "<select" in (text := path.read_text(encoding="utf-8")) and " multiple" in text
        )
        self.assertEqual(multiple, ["analytics.html", "detail.html", "list.html"])
        for name in ("campaigns.js", "campaign-analytics.js", "campaign-detail.js"):
            self.assertIn("enhanceChecklistSelect(", (SCRIPTS / "features" / "campaigns" / name).read_text(encoding="utf-8"))
