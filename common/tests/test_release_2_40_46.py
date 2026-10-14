"""The 2.40.46 UI/UX audit: what every page measured, fixed at its cause.

Each page was opened in light, dark and on a phone, every dialog on it opened
in turn, and the page tabbed through with the real Tab key. What this pins:

* keyboard focus is visible on buttons and menu entries — the kit's own
  `outline: none !important` had beaten the panel's ring on all of them;
* a closed drawer is out of the Tab order;
* primary-coloured *text* reads at 4.5:1 in both themes, for the panel's
  colour and any company's own, while fills keep the accent;
* the muted-text repair holds at the token, and the light-only badge and tab
  repairs reach dark mode;
* no utility class the code uses is missing from every stylesheet (`min-w-0`
  and `text-break` were, in twenty places);
* the lead page shows a campaign's hidden container as not found, the way its
  API does;
* a page whose module fails to load says so.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from accounts.models import User
from common.color import (
    KIT_DARK_PRIMARY,
    KIT_DARK_PRIMARY_LIGHT,
    PANEL_LIGHT_ACCENT,
    TEXT_CONTRAST,
    TEXT_SURFACES,
    _hex_to_rgb,
    _tint,
    accent_theme_css,
    accent_theme_variables,
    contrast_ratio,
    panel_default_accent_css,
    text_shade,
)
from common.stylesheets import stylesheet_text
from sales.campaigns import add_campaign_member, create_campaign
from sales.models import Lead

ROOT = Path(__file__).resolve().parents[2]
THEME = ROOT / "common" / "static" / "common" / "ui" / "css" / "dolphin-theme.rtl.css"
PLUGINS = ROOT / "common" / "static" / "common" / "ui" / "css" / "dolphin-plugins.rtl.css"
JS = ROOT / "common" / "static" / "common" / "js"


def css_value(block, name):
    return block.split(f"--{name}:")[1].split(";")[0]


class PrimaryTextTests(SimpleTestCase):
    ACCENTS = ("#1b84ff", "#0071e3", "#087f73", "#ffcc00", "#f5f5f5", "#0a0a2a", "#e42855", "#7239ea")

    def assert_reads(self, shade, mode, accent, extra=()):
        surfaces = [*TEXT_SURFACES[mode], *extra]
        for surface in surfaces:
            ratio = contrast_ratio(_hex_to_rgb(shade), _hex_to_rgb(surface))
            self.assertGreaterEqual(ratio, TEXT_CONTRAST, f"{accent} as text in {mode} on {surface}: {ratio:.2f}")
        tint = _tint(_hex_to_rgb(accent), mode)
        self.assertGreaterEqual(contrast_ratio(_hex_to_rgb(shade), tint), TEXT_CONTRAST)

    def test_any_accent_gets_a_text_shade_that_reads_in_both_themes(self):
        for accent in self.ACCENTS:
            for mode in ("light", "dark"):
                with self.subTest(accent=accent, mode=mode):
                    self.assert_reads(text_shade(accent, mode), mode, accent)

    def test_an_accent_that_already_reads_is_left_alone(self):
        self.assertEqual(text_shade("#0a0a2a", "light"), "#0a0a2a")
        self.assertEqual(text_shade("#ffcc00", "dark"), "#ffcc00")

    def test_fills_keep_the_accent_and_words_take_the_shade(self):
        for mode in ("light", "dark"):
            variables = accent_theme_variables("#1b84ff", mode)
            self.assertEqual(variables["bs-primary"], "#1b84ff")
            self.assertEqual(variables["bs-text-primary"], text_shade("#1b84ff", mode))
            self.assertEqual(variables["bs-link-color"], variables["bs-text-primary"])
        css = accent_theme_css("#1b84ff")
        dark = css.split("[data-bs-theme=dark]")[1]
        self.assertEqual(css_value(dark, "bs-text-primary"), text_shade("#1b84ff", "dark"))

    def test_the_panel_default_reads_in_dark_mode_too(self):
        """Dark mode with no company colour keeps the kit's fill (#006AE6, white
        text at 5.1:1) and gets only a text shade of it: the kit's own blue as
        words on the dark card measured 3.6:1."""
        self.assertLess(contrast_ratio(_hex_to_rgb(KIT_DARK_PRIMARY), _hex_to_rgb("#15171c")), TEXT_CONTRAST)
        css = panel_default_accent_css()
        light, dark = css.split("[data-bs-theme=dark]")
        self.assertNotIn("--bs-primary:", dark)
        self.assertEqual(css_value(light, "bs-primary"), PANEL_LIGHT_ACCENT)
        shade = css_value(dark, "bs-text-primary")
        self.assert_reads(shade, "dark", KIT_DARK_PRIMARY, (KIT_DARK_PRIMARY_LIGHT,))
        self.assert_reads(css_value(light, "bs-text-primary"), "light", PANEL_LIGHT_ACCENT)

    def test_kit_components_put_the_text_shade_on_words(self):
        css = stylesheet_text()
        for selector in (
            ".btn.btn-light-primary,\n.btn-check:checked + .btn.btn-active-light-primary,",
            ".btn.btn-active-light-primary.show {\n    color: var(--bs-text-primary);",
            ".stepper.stepper-links .stepper-nav .stepper-item.current .stepper-title {\n    color: var(--bs-text-primary);",
            "--bs-accordion-active-color: var(--bs-text-primary);",
            ".dolphin-page-tabs.nav-pills-custom .nav-link.active {\n    color: var(--bs-text-primary);",
        ):
            with self.subTest(selector=selector[:50]):
                self.assertIn(selector, css)


class ContrastRepairTests(SimpleTestCase):
    def test_the_muted_repair_holds_at_the_token(self):
        """`.text-muted` was repaired in 2.40.31; the panel's own rules that read
        `var(--bs-text-muted)` directly still drew 2.6:1 (light) and 3.1:1 (dark)."""
        css = stylesheet_text()
        self.assertRegex(css, r"\[data-bs-theme=dark\] \{\s*--bs-text-muted: var\(--bs-gray-700\);")
        self.assertIn("color: var(--bs-text-muted);", css)

    def test_badges_and_tabs_are_repaired_in_dark_mode_too(self):
        css = stylesheet_text()
        for tone in ("success", "primary", "info", "warning", "danger"):
            with self.subTest(tone=tone):
                self.assertRegex(css, rf"\[data-bs-theme=dark\] \.badge-light-{tone} \{{ color: color-mix\(in srgb, var\(--bs-{tone}\) \d+%, #fff\); \}}")
        self.assertIn("\n.nav-line-tabs .nav-item .nav-link:not(.active) { color: var(--bs-gray-700); }", css)


class KeyboardTests(SimpleTestCase):
    def test_buttons_and_menu_entries_show_the_focus_ring(self):
        theme = THEME.read_text(encoding="utf-8")
        # The kit turns the outline off on both, with !important…
        self.assertRegex(theme, r"\.btn \{[^}]*outline: none !important")
        self.assertRegex(theme, r"\.menu-item \.menu-link \{[^}]*outline: none !important")
        # …so the panel's ring has to be !important on exactly those two.
        css = stylesheet_text()
        self.assertRegex(css, r"\.btn:focus-visible,\n\.menu-item \.menu-link:focus-visible \{\n    outline: 2px solid var\(--bs-primary\) !important;")

    def test_a_closed_drawer_leaves_the_tab_order(self):
        css = stylesheet_text()
        self.assertRegex(css, r"\.drawer:not\(\.drawer-on\) \{\n    visibility: hidden;")
        # Hidden only after the slide-out, so closing still animates.
        self.assertIn("visibility 0s linear 0.3s !important", css)


#: Utility families whose classes are defined on their own (`.min-w-100px`),
#: unlike a component's modifiers (`.btn.btn-icon`, `.symbol-40px …`).
UTILITY = re.compile(
    r"^(m[setbxy]?|p[setbxy]?|g[xy]?|gap|w|h|mw|mh|min-w|min-h|fs|fw|lh|ls|text|bg|border|rounded|d|flex|align"
    r"|justify|order|position|top|bottom|start|end|z|opacity|overflow|shadow|col|offset|cursor|user-select)"
    r"(-[a-z0-9]+)+$"
)


def standalone_classes(*paths):
    defined = set()
    for path in paths:
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for selector_list in re.findall(r"([^{}]+)\{", text):
            for selector in selector_list.split(","):
                match = re.fullmatch(
                    r"\s*(?:\[data-bs-theme=\w+\]\s+|:root\s+)?\.(-?[_a-zA-Z][\w-]*)((?::[\w-]+(?:\([^)]*\))?)*)\s*",
                    selector,
                )
                if match:
                    defined.add(match.group(1))
    return defined


class UtilityClassTests(SimpleTestCase):
    def test_every_utility_the_code_uses_is_defined_somewhere(self):
        """`min-w-0` reads as a kit utility, so nobody checked it: the kit has no
        such class, and in eleven places a flex row with a long name pushed out
        of its card instead of truncating. `text-break`, Bootstrap's own, was
        dropped from the kit and nine places relied on it."""
        panel_css = sorted((ROOT / "common" / "static" / "common" / "css").glob("*.css"))
        defined = standalone_classes(THEME, PLUGINS, *panel_css)
        sources = [
            *(ROOT / "common" / "templates").rglob("*.html"),
            *(ROOT / "common" / "templates").rglob("*.inc"),
            *(ROOT / "profiles" / "templates").rglob("*.html"),
            *(ROOT / "profiles" / "templates").rglob("*.inc"),
            *JS.rglob("*.js"),
        ]
        missing = {}
        for path in sources:
            text = path.read_text(encoding="utf-8")
            chunks = re.findall(r'class="([^"]*)"', text)
            chunks += re.findall(r'className\s*=\s*[`"]([^`"]*)[`"]', text)
            chunks += re.findall(r"classList\.(?:add|remove|toggle)\(([^)]*)\)", text)
            for chunk in chunks:
                chunk = re.sub(r"\{[%{].*?[%}]\}|\$\{[^}]*\}", " ", chunk)
                for token in re.findall(r"[a-z][a-z0-9-]*", chunk):
                    if UTILITY.match(token) and token not in defined:
                        missing.setdefault(token, path.relative_to(ROOT).as_posix())
        self.assertEqual(missing, {})


class SmallFixTests(SimpleTestCase):
    def test_a_page_that_fails_to_load_says_so(self):
        main = (JS / "main.js").read_text(encoding="utf-8")
        self.assertNotIn(".catch(() => {})", main)
        self.assertIn(".then(loadPage).catch(pageFailed)", main)
        self.assertIn("console.error(error);", main)

    def test_small_touch_targets_grow_on_a_phone(self):
        css = stylesheet_text()
        self.assertIn(".dashboard-card-all,\n    .chat-page-link {\n        min-width: 2rem;", css)
        self.assertIn("#lead-board .board-search-toggle,\n    #order-board .board-search-toggle {\n        min-width: 2.4rem;", css)
        for name in ("dashboard/dashboard.js", "dashboard/widget-cards.js"):
            self.assertIn('"dashboard-card-all ', (JS / "features" / name).read_text(encoding="utf-8"))

    def test_the_supply_batch_search_has_a_name(self):
        page = (ROOT / "common" / "templates" / "common" / "orders" / "list.html").read_text(encoding="utf-8")
        self.assertRegex(page, r'id="supply-batch-search"[^>]*aria-label="[^"]+"')


class LeadPageTests(TestCase):
    def test_a_campaign_container_is_not_found_on_the_lead_page_as_in_the_api(self):
        manager = User.objects.create_user(username="audit.manager", password="Strong-pass-746!", role=User.Role.SALES_MANAGER)
        campaign = create_campaign(actor=manager, name="پاییز")
        add_campaign_member(actor=manager, campaign=campaign, full_name="مریم", raw_phone="09125550146")
        container = Lead.objects.get(campaign=campaign, source="campaign")
        self.client.force_login(manager)
        self.assertEqual(self.client.get(f"/api/v1/leads/{container.pk}/").status_code, 404)
        page = self.client.get(f"/leads/{container.pk}/")
        self.assertContains(page, "سرنخ پیدا نشد", status_code=404)
        self.assertNotContains(page, "data-attachments-panel", status_code=404)
