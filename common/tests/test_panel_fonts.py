"""The typefaces a reader may choose, and whether the choice reaches the whole
panel (2.18.7).

Product owner, 2026-09-27: «کاربر باید بتواند قلم‌های بیشتری انتخاب کند و
تغییر قلم روی کل پنل اثر بگذارد».
"""

import re

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from common import preferences
from common.models import (
    DEFAULT_PANEL_FONT_FAMILY,
    PANEL_FONT_FAMILIES,
    PANEL_FONT_FAMILIES_BUNDLED,
    PANEL_FONT_FAMILY_STACKS,
    THEME_PANEL_FONT_FAMILY,
)
from common.tests.ui_overhaul_helpers import CODE, ROOT, SCRIPT, TEMPLATES, function_body

FONTS = ROOT / "common" / "static" / "common" / "fonts"
SHEET = (FONTS / "panel-fonts.css").read_text(encoding="utf-8")
User = get_user_model()
PASSWORD = "Aa!23456pass"


def registered_families():
    return set(re.findall(r'font-family:\s*"([^"]+)";', SHEET))


class BundledFontTests(SimpleTestCase):
    def test_every_bundled_face_is_registered_and_first_in_its_stack(self):
        registered = registered_families()
        # The theme's own IRANSans is registered by the theme's stylesheet.
        for family in PANEL_FONT_FAMILIES_BUNDLED - {THEME_PANEL_FONT_FAMILY}:
            with self.subTest(family=family):
                first = PANEL_FONT_FAMILY_STACKS[family].split(",")[0].strip().strip('"')
                self.assertIn(first, registered)

    def test_every_registered_file_exists_and_is_a_woff2(self):
        for relative in re.findall(r'url\("([^"]+)"\)', SHEET):
            with self.subTest(file=relative):
                path = FONTS / relative
                self.assertTrue(path.exists(), relative)
                self.assertEqual(path.read_bytes()[:4], b"wOF2")

    def test_every_font_folder_carries_its_open_font_license(self):
        """The SIL OFL requires the license to travel with the font."""
        folders = {relative.split("/")[0] for relative in re.findall(r'url\("([^"]+)"\)', SHEET)}
        self.assertEqual(len(folders), 6)
        for folder in folders:
            with self.subTest(folder=folder):
                text = (FONTS / folder / "OFL.txt").read_text(encoding="utf-8", errors="replace").upper()
                self.assertIn("OPEN FONT LICENSE", text)

    def test_the_sheet_registers_faces_and_chooses_none(self):
        stripped = re.sub(r"@font-face\s*\{[^}]*\}", "", re.sub(r"/\*.*?\*/", "", SHEET, flags=re.S))
        self.assertEqual(stripped.strip(), "")

    def test_each_bundled_face_is_offered_with_its_stack(self):
        offered = {entry["value"]: entry for entry in preferences.catalog()["font_families"]}
        self.assertEqual(set(offered), {value for value, _label, _stack in PANEL_FONT_FAMILIES})
        for family in PANEL_FONT_FAMILIES_BUNDLED:
            self.assertTrue(offered[family]["bundled"])
        self.assertFalse(offered["tahoma"]["bundled"])
        self.assertEqual(offered["vazirmatn"]["stack"], PANEL_FONT_FAMILY_STACKS["vazirmatn"])


class WholePanelTests(SimpleTestCase):
    def test_charts_draw_in_the_panels_current_face_not_a_literal(self):
        self.assertNotIn('fontFamily: "IRANSansWeb, Helvetica, sans-serif"', SCRIPT)
        self.assertIn("fontFamily: chartFontFamily()", SCRIPT)
        self.assertIn("getComputedStyle(document.body).fontFamily", function_body("chartFontFamily"))

    def test_the_chart_label_guard_follows_the_body_font_token(self):
        marker = ".apexcharts-legend-text {"
        declarations = CODE[CODE.index(marker):CODE.index("}", CODE.index(marker))]
        self.assertIn("font-family: var(--bs-body-font-family) !important", declarations)

    def test_the_sheet_loads_only_where_it_is_needed(self):
        base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        self.assertIn("{% if panel_font_sheet %}<link rel=\"stylesheet\" href=\"{% static 'common/fonts/panel-fonts.css' %}", base)
        self.assertTrue(preferences.needs_font_sheet({"font_family": "vazirmatn"}))
        # The default is Vazirmatn since 2.40.36, so the sheet loads for it;
        # only the theme's own face needs none.
        self.assertTrue(preferences.needs_font_sheet({"font_family": DEFAULT_PANEL_FONT_FAMILY}))
        self.assertFalse(preferences.needs_font_sheet({"font_family": THEME_PANEL_FONT_FAMILY}))
        self.assertFalse(preferences.needs_font_sheet({"font_family": "tahoma"}))

    def test_the_live_preview_reads_the_stack_from_the_page(self):
        body = function_body("setupSettingsPage")
        self.assertIn("chosen.dataset.fontStack", body)
        self.assertNotIn("const FONT_STACKS", body)


class SettingsPageFontTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fonts.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.client.force_login(self.user)

    def test_every_choice_is_drawn_in_its_own_face(self):
        page = self.client.get("/settings/").content.decode("utf-8")
        self.assertEqual(page.count('class="font-family-sample"'), len(PANEL_FONT_FAMILIES))
        self.assertIn("panel-fonts.css", page)
        self.assertEqual(page.count("اگر روی دستگاه نصب باشد"),
                         len(PANEL_FONT_FAMILIES) - len(PANEL_FONT_FAMILIES_BUNDLED))

    def test_a_chosen_bundled_face_reaches_every_other_page(self):
        preferences.update_preferences(actor=self.user, font_family="estedad")
        page = self.client.get("/customers/").content.decode("utf-8")
        self.assertIn("panel-fonts.css", page)
        self.assertIn("html,body{font-family:Estedad, IRANSansWeb", page)
