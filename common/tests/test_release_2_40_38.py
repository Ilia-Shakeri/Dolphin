"""The platform layer (2.40.38).

Product owner, after the design review: «همه رو انجام بده» — one type scale,
one control size and radius, layered surfaces, a light sidebar in light mode,
a grey dialog close, dialogs that close with a motion and are sheets on a
phone, a tab bar on a phone, a large title that moves into the header, a
sliding tab indicator, rows that open their record, and a legible
notification badge.
"""

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "common" / "static" / "common"
JS = STATIC / "js"
CSS = (STATIC / "dolphin.css").read_text(encoding="utf-8")
BASE = (ROOT / "common" / "templates" / "common" / "base.html").read_text(encoding="utf-8")
MAIN = (JS / "main.js").read_text(encoding="utf-8")


class TokenTests(SimpleTestCase):
    def test_one_motion_curve_and_one_radius_per_kind(self):
        self.assertIn("--dolphin-ease: cubic-bezier(0.32, 0.72, 0, 1);", CSS)
        self.assertIn("--dolphin-radius-control: 10px;", CSS)
        self.assertIn("--dolphin-radius-card: 16px;", CSS)

    def test_surfaces_are_layered_not_bordered(self):
        self.assertIn("--bs-app-bg-color: #f2f2f7;", CSS)
        self.assertIn("--bs-root-card-border-color: transparent;", CSS)

    def test_the_badge_figure_is_legible(self):
        block = CSS.split("#dolphin_drawer_chat_toggle .reminder-bell-badge {")[1].split("}")[0]
        self.assertIn("font-size: 11px;", block)


class SidebarAndBrandTests(SimpleTestCase):
    def test_the_sidebar_follows_the_colour_theme(self):
        self.assertIn('=== "dark" ? "dark-sidebar" : "light-sidebar"', BASE)
        self.assertIn("[data-dolphin-app-layout=light-sidebar] .app-sidebar {", CSS)

    def test_each_ground_gets_its_own_brand_mark(self):
        self.assertEqual(BASE.count('<picture class="brand-on-light">'), 3)
        self.assertIn("[data-bs-theme=light] .brand-on-dark,", CSS)
        self.assertNotIn('<span class="text-white fw-bold fs-4">{{ brand_name }}</span>', BASE)


class DialogTests(SimpleTestCase):
    def test_the_close_control_is_a_quiet_circle(self):
        block = CSS.split("dialog .btn.btn-icon[data-close-dialog]:not(.btn-active) {")[1].split("}")[0]
        self.assertIn("border-radius: 999px;", block)
        self.assertNotIn("--bs-danger", block)

    def test_a_dialog_closes_with_a_motion(self):
        self.assertIn("display 260ms allow-discrete, overlay 260ms allow-discrete", CSS)
        self.assertIn("@starting-style", CSS)

    def test_a_phone_dialog_is_a_sheet_that_can_be_pulled_down(self):
        dialogs = (JS / "ui" / "dialogs.js").read_text(encoding="utf-8")
        self.assertIn("export function setupSheetDrag()", dialogs)
        self.assertIn("border-radius: 18px 18px 0 0;", CSS)
        self.assertIn("setupSheetDrag();", MAIN)


class NavigationTests(SimpleTestCase):
    def test_the_phone_gets_a_tab_bar_built_from_the_sidebar(self):
        module = (JS / "shell" / "tab-bar.js").read_text(encoding="utf-8")
        self.assertIn('sidebar.querySelector(`a.menu-link[href="${path}"]`)', module)
        self.assertIn("setupTabBar();", MAIN)

    def test_the_title_moves_into_the_header(self):
        module = (JS / "shell" / "header-title.js").read_text(encoding="utf-8")
        self.assertIn('document.body.classList.toggle("is-title-collapsed"', module)
        self.assertIn("#dolphin_app_toolbar .breadcrumb { display: none; }", CSS)

    def test_tabs_have_a_sliding_indicator(self):
        module = (JS / "ui" / "tab-indicator.js").read_text(encoding="utf-8")
        self.assertIn('bar.className = "nav-line-indicator";', module)
        self.assertIn("setupTabIndicators();", MAIN)

    def test_a_row_opens_its_record(self):
        table = (JS / "ui" / "table.js").read_text(encoding="utf-8")
        self.assertIn('row.classList.add("is-row-link");', table)
        self.assertIn('link.setAttribute("aria-label", "جزئیات");', table)
        self.assertIn("setupRowLinks();", MAIN)
