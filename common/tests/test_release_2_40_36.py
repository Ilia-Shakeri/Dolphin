"""A smooth, fast, readable panel (2.40.36).

Product owner, 2026-10-07, after a page-by-page design review: «همهٔ این موارد
را انجام بده» — no page jumps while it loads, a lighter vendor bundle, instant
navigation, Persian names everywhere, readable contrast, real font weights,
cards for lists on a phone, and the smaller polish items of that review.
"""

import json
import re
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User
from auditlog.labels import object_type_label
from common.color import PANEL_LIGHT_ACCENT, _hex_to_rgb, _relative_luminance
from common.models import DEFAULT_PANEL_FONT_FAMILY, PANEL_FONT_FAMILY_STACKS

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "common" / "static" / "common"
JS = STATIC / "js"
CSS = (STATIC / "dolphin.css").read_text(encoding="utf-8")
BASE = (ROOT / "common" / "templates" / "common" / "base.html").read_text(encoding="utf-8")
PASSWORD = "Strong-pass-736!"


def contrast(foreground, background=(255, 255, 255)):
    lighter, darker = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class NoJumpTests(SimpleTestCase):
    def test_the_scrollbar_keeps_its_room(self):
        # A page growing past the window used to move everything sideways.
        self.assertIn("html { scrollbar-gutter: stable; }", CSS)

    def test_the_page_appears_once_its_first_load_is_done(self):
        self.assertIn('<div id="page-stage" class="page-stage" {% block page_booting %}data-booting{% endblock %}>', BASE)
        main = (JS / "main.js").read_text(encoding="utf-8")
        self.assertIn("Promise.race([loaded, new Promise((resolve) => { setTimeout(resolve, REVEAL_DEADLINE_MS); })]).then(revealPage);", main)
        # Shown by the stylesheet itself should the script never get there.
        self.assertIn("animation: dashboard-stage-failsafe 0s linear 4s forwards;", CSS)

    def test_the_menu_entry_is_lit_before_the_first_paint(self):
        script = BASE.split('<div class="app-main flex-column flex-row-fluid" id="dolphin_app_main">')[0]
        self.assertIn('if (group) group.classList.add("here", "show");', script)


class LighterVendorTests(SimpleTestCase):
    def test_the_vendor_bundle_carries_only_what_the_panel_uses(self):
        bundle = (STATIC / "ui" / "js" / "dolphin-plugins.js").read_text(encoding="utf-8")
        self.assertLess(len(bundle), 1_100_000)
        for kept in ("jQuery JavaScript Library v3.7.1", "@popperjs/core v2.11.8", "Bootstrap v5.3.3", "ApexCharts v3.48.0"):
            self.assertIn(kept, bundle)
        for dropped in ("Quill Editor", "Select2 4.1.0", "Tempus Dominus", "Chart.js v4.4.2", "FormValidation", "jQuery.fn.dropzone"):
            self.assertNotIn(dropped, bundle)

    def test_the_vendor_styles_drop_the_unused_icon_fonts(self):
        sheet = (STATIC / "ui" / "css" / "dolphin-plugins.rtl.css").read_text(encoding="utf-8")
        self.assertLess(len(sheet), 400_000)
        # Only the panel's own three icon fonts are declared; no Font Awesome,
        # Line Awesome or Bootstrap Icons rule is left to draw anything.
        self.assertEqual(sheet.count("@font-face"), 3)
        self.assertNotIn(".fa-solid", sheet)
        self.assertNotIn(".ql-container", sheet)

    def test_links_are_prefetched_never_the_api(self):
        rules = json.loads(re.search(r'<script type="speculationrules">(.*?)</script>', BASE, re.S).group(1))
        prefetch = rules["prefetch"][0]
        self.assertEqual(prefetch["eagerness"], "moderate")
        self.assertIn("/api/*", json.dumps(prefetch))


class PersianNamesTests(TestCase):
    def test_the_activity_log_names_the_record_kind(self):
        self.assertEqual(object_type_label("chat.chatmessage"), "پیام گفت‌وگو")
        self.assertEqual(object_type_label("sales.salesdocument"), "سند فروش")
        self.assertEqual(object_type_label("unknown.model"), "unknown.model")

    def test_file_fields_are_drawn_in_persian(self):
        module = (JS / "ui" / "file-inputs.js").read_text(encoding="utf-8")
        self.assertIn('button.textContent = "انتخاب فایل";', module)
        self.assertIn("setupFileInputs();", (JS / "main.js").read_text(encoding="utf-8"))

    def test_a_number_cell_keeps_its_order_and_its_column(self):
        self.assertIn('.table td[dir="ltr"]:not(.text-center):not(.text-start):not(.text-end) { text-align: right; }', CSS)
        customers = (JS / "features" / "customers" / "customers.js").read_text(encoding="utf-8")
        self.assertIn('customer.primary_phone?.raw_phone || "—").dir = "ltr";', customers)


class ReadableTests(SimpleTestCase):
    def test_the_default_light_primary_carries_small_white_text(self):
        self.assertGreaterEqual(contrast((255, 255, 255), _hex_to_rgb(PANEL_LIGHT_ACCENT)), 4.5)
        self.assertGreaterEqual(contrast(_hex_to_rgb(PANEL_LIGHT_ACCENT)), 4.5)

    def test_status_colours_have_a_text_shade_in_light_mode(self):
        self.assertIn("[data-bs-theme=light] .text-success:not(i):not(svg),", CSS)
        self.assertIn(".form-check-label { color: var(--bs-gray-700); }", CSS)

    def test_the_default_face_has_real_weights_and_persian_digits(self):
        self.assertEqual(DEFAULT_PANEL_FONT_FAMILY, "vazirmatn")
        self.assertTrue(PANEL_FONT_FAMILY_STACKS["vazirmatn"].startswith('"Vazirmatn FD"'))
        sheet = (STATIC / "fonts" / "panel-fonts.css").read_text(encoding="utf-8")
        for weight, name in ((400, "Regular"), (500, "Medium"), (600, "SemiBold"), (700, "Bold"), (800, "ExtraBold")):
            self.assertIn(f'src: url("vazirmatn/Vazirmatn-FD-{name}.woff2") format("woff2");\n    font-weight: {weight};', sheet)
            self.assertEqual((STATIC / "fonts" / "vazirmatn" / f"Vazirmatn-FD-{name}.woff2").read_bytes()[:4], b"wOF2")


class PhoneAndPolishTests(SimpleTestCase):
    def test_lists_become_cards_on_a_phone(self):
        module = (JS / "ui" / "stack-tables.js").read_text(encoding="utf-8")
        self.assertIn("cell.dataset.label = label;", module)
        self.assertIn(".table.dolphin-stack > tbody > tr > td::before {\n        content: attr(data-label);", CSS)

    def test_a_dialog_opens_on_its_first_field(self):
        dialogs = (JS / "ui" / "dialogs.js").read_text(encoding="utf-8")
        self.assertIn("export function setupDialogFocus()", dialogs)
        self.assertIn('if (window.matchMedia("(pointer: coarse)").matches) return;', dialogs)

    def test_the_trend_axis_reads_compact_amounts(self):
        charts = (JS / "ui" / "charts.js").read_text(encoding="utf-8")
        self.assertIn('[[1e9, "میلیارد"], [1e6, "میلیون"], [1e3, "هزار"]]', charts)
        self.assertIn("formatter: compactAmount,", (JS / "features" / "dashboard" / "dashboard.js").read_text(encoding="utf-8"))

    def test_a_locked_field_on_a_detail_page_reads_as_a_value(self):
        self.assertIn('body[data-page$="-detail"] #page-stage select.form-select.form-select-solid:disabled:not(dialog *)', CSS)


class FaviconAndLeadTests(TestCase):
    def test_the_browsers_own_favicon_request_is_answered(self):
        response = Client().get("/favicon.ico")
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response["Location"].endswith("common/brand/favicon.ico"))

    def test_a_lead_names_its_real_campaign(self):
        from rest_framework.test import APIClient

        from sales.campaigns import create_campaign
        from sales.services import create_lead

        manager = User.objects.create_user(username="lc.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        parent = create_campaign(actor=manager, name="مادر")
        child = create_campaign(actor=manager, name="فرزند", parent=parent)
        lead = create_lead(actor=manager, campaign=child)
        client = APIClient()
        client.force_login(manager)
        self.assertEqual(client.get(f"/api/v1/leads/{lead.pk}/").json()["campaign_display"], "مادر (فرزند)")
