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


class ChecklistPolishTests(SimpleTestCase):
    """2.40.9: what the checklist says and does around its options."""

    script = (SCRIPTS / "ui" / "checklist-select.js").read_text(encoding="utf-8")
    wizard = (SCRIPTS / "ui" / "wizard.js").read_text(encoding="utf-8")
    css = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")

    def test_a_search_with_no_match_says_so(self):
        self.assertIn('noMatch.textContent = "گزینه‌ای با این جست‌وجو نیست.";', self.script)
        self.assertIn("noMatch.hidden = !term || shown > 0;", self.script)

    def test_persian_arabic_and_latin_forms_match(self):
        self.assertIn("const searchable = (text) => toPersianDigits(normalizeSearchText(text)).toLowerCase();", self.script)
        self.assertIn("!searchable(option.text).includes(term)", self.script)

    def test_typing_a_search_never_marks_a_wizard_changed(self):
        self.assertIn('search.dataset.dirtyIgnore = "";', self.script)
        self.assertIn('if (event.target?.closest?.("[data-dirty-ignore]")) return;', self.wizard)

    def test_nothing_ticked_means_all_only_where_it_does(self):
        self.assertIn('(emptyMeansAll ? "هیچ‌کدام (یعنی همه)" : "هیچ‌کدام")', self.script)
        analytics = (SCRIPTS / "features" / "campaigns" / "campaign-analytics.js").read_text(encoding="utf-8")
        self.assertIn("enhanceChecklistSelect(select, {emptyMeansAll: true});", analytics)
        for name in ("campaigns.js", "campaign-detail.js"):
            self.assertNotIn("emptyMeansAll", (SCRIPTS / "features" / "campaigns" / name).read_text(encoding="utf-8"))

    def test_no_fixed_width_search_and_a_phone_layout(self):
        self.assertNotIn("w-200px", self.script)
        self.assertIn("flex: 1 1 12rem;", self.css.split(".dolphin-checklist-search {")[1].split("}")[0])
        self.assertIn(".dolphin-checklist-counter {\n        flex-basis: 100%;", self.css)
