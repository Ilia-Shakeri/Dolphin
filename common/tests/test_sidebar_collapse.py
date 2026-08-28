"""The sidebar collapses to its icons, and remembers that it did.

The collapsing itself is the purchased theme's: its CSS reacts to
`data-kt-app-sidebar-minimize` on `<body>`, and its `KTToggle` flips that
attribute and writes a cookie. What this project owns is the three things the
theme cannot supply — the attribute rendered server-side so a collapsed sidebar
never paints open first, a second logo for a 75px rail, and a toggle in a place
a reader can find.

Those three are what these tests hold. They are deliberately about markup and
state, not about pixels: the widths are the vendor's and are not ours to pin.
"""

import pathlib
import re

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User
from common.context_processors import SIDEBAR_MINIMIZE_COOKIE


PASSWORD = "Strong-pass-937!"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL_CSS = REPOSITORY_ROOT / "common" / "static" / "common" / "forooshbin.css"


class SidebarCollapseRenderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sidebar.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)

    def page(self):
        return self.client.get("/customers/").content.decode("utf-8")

    # --- the state has to survive a page load ------------------------------

    def test_a_fresh_visitor_gets_an_open_sidebar(self):
        self.assertNotIn('data-kt-app-sidebar-minimize="on"', self.page())

    def test_the_cookie_collapses_the_sidebar_on_the_server(self):
        """Rendered collapsed, not collapsed by script after paint.

        This panel does full page loads between screens. Restoring the state in
        JavaScript would open the sidebar and snap it shut on every single
        navigation.
        """
        self.client.cookies[SIDEBAR_MINIMIZE_COOKIE] = "on"
        self.assertIn('data-kt-app-sidebar-minimize="on"', self.page())

    def test_the_toggle_renders_pressed_when_collapsed(self):
        """Otherwise the chevron points the wrong way on a collapsed reload."""
        self.client.cookies[SIDEBAR_MINIMIZE_COOKIE] = "on"
        markup = self.page()
        toggle = re.search(r'<button id="kt_app_sidebar_toggle"[^>]*>', markup).group(0)
        self.assertIn("active", toggle)

    def test_any_other_cookie_value_leaves_the_sidebar_open(self):
        self.client.cookies[SIDEBAR_MINIMIZE_COOKIE] = "off"
        self.assertNotIn('data-kt-app-sidebar-minimize="on"', self.page())

    # --- the markup the theme's own JS and CSS look for --------------------

    def test_the_toggle_carries_the_attributes_kttoggle_binds_to(self):
        """`KTToggle.createInstances()` finds these at DOM ready; nothing else
        wires the button, so a missing attribute is a dead control."""
        markup = self.page()
        toggle = re.search(r'<button id="kt_app_sidebar_toggle"[^>]*>', markup).group(0)
        self.assertIn('data-kt-toggle="true"', toggle)
        self.assertIn('data-kt-toggle-target="body"', toggle)
        self.assertIn('data-kt-toggle-name="app-sidebar-minimize"', toggle)
        self.assertIn('data-kt-toggle-state="active"', toggle)

    def test_the_toggle_is_reachable_without_sight(self):
        markup = self.page()
        toggle = re.search(r'<button id="kt_app_sidebar_toggle"[^>]*>', markup).group(0)
        self.assertIn("aria-label", toggle)

    def test_both_logos_are_rendered_so_neither_has_to_load_on_toggle(self):
        """Swapping a `src` would reload a file and blank the rail mid-toggle."""
        markup = self.page()
        self.assertIn("app-sidebar-logo-default", markup)
        self.assertIn("app-sidebar-logo-minimize", markup)

    def test_the_cookie_name_is_the_one_the_theme_writes(self):
        """`KTToggle` builds it as `data-kt-` + the toggle's name. If these ever
        disagree the sidebar collapses and forgets on the next page."""
        markup = self.page()
        toggle = re.search(r'<button id="kt_app_sidebar_toggle"[^>]*>', markup).group(0)
        name = re.search(r'data-kt-toggle-name="([^"]+)"', toggle).group(1)
        self.assertEqual(SIDEBAR_MINIMIZE_COOKIE, f"data-kt-{name}")


class SidebarCollapseStyleTests(SimpleTestCase):
    """The few rules that must outrank the theme's own utilities."""

    def setUp(self):
        self.css = PANEL_CSS.read_text(encoding="utf-8")

    def test_the_collapsed_rail_may_shrink_below_its_content(self):
        """A flex item defaults to `min-width: auto` — never smaller than what
        is inside it. Without this the width variable says 75px, the rule reads
        it, and the sidebar still measures its widest child."""
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \{[^}]*min-width: 0',
        )

    def test_the_expanded_brand_is_hidden_with_enough_weight_to_win(self):
        """It carries Bootstrap's `d-flex`, which is `!important`."""
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar-logo-default \{'
            r'[^}]*display: none !important',
        )

    def test_the_width_transition_is_off_so_the_toggle_actually_resizes(self):
        """The collapse did nothing until the next page load, and this is why.

        The sidebar's width is `var(--bs-app-sidebar-width)`, and the toggle
        changes that custom property rather than the `width` declaration.
        Chromium will not re-apply a width that resolves through `var()` while a
        transition on `width` is armed: measured live, the variable moved 265px
        to 75px on every click while the box stayed at 265px. The theme declares
        that transition inside its own collapsed rule, so the selector is
        repeated here to outrank it.
        """
        self.assertRegex(
            self.css,
            r'\.app-sidebar,\s*\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \{'
            r"[^}]*transition: none",
        )

    def test_the_brand_mark_has_an_explicit_auto_height(self):
        """Without it the collapsed logo renders as a 1230px-tall sliver.

        The markup carries `width="1278" height="1230"` so the browser can
        reserve the box before the file arrives. Setting only a CSS width leaves
        that height attribute in force — which is what «لوگوی ریز نشان داده
        نمی‌شود» actually was: it was being drawn, one column wide and taller
        than the screen.
        """
        self.assertRegex(self.css, r"\.brand-mark \{[^}]*height: auto")

    def test_the_collapsed_menu_narrows_to_the_rail(self):
        """Without this the icons are drawn outside the visible strip.

        The theme keeps the wrapper at the full width while collapsed and lets
        the 75px sidebar clip it — that is how its own hover-to-peek mode works,
        which this panel does not use. So the links stayed 234px and
        `justify-content: center` put each icon in the middle of 234px:
        measured at x=1447 while the visible rail was 1510-1585. The icons were
        rendering perfectly, just off the edge of their own sidebar.
        """
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \.app-sidebar-menu,'
            r"[^{]*\{[^}]*width: var\(--bs-app-sidebar-width\)",
        )

    def test_the_collapsed_titles_become_labels_rather_than_vanishing(self):
        """A rail of eleven unlabelled glyphs asks the reader to memorise them."""
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \.menu-title \{'
            r"[^}]*position: absolute",
        )
        # Left of the rail, which under RTL means insetting the *start*.
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \.menu-title \{'
            r"[^}]*inset-inline-start: calc\(100% \+",
        )

    def test_the_rail_stops_clipping_so_a_label_can_leave_it(self):
        """`overflow: hidden` on the rail would cut the label off with it."""
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \.app-sidebar-menu,'
            r"[^{]*\{[^}]*overflow: visible",
        )

    def test_the_mobile_rule_outranks_the_themes_button_classes(self):
        """`.btn.btn-icon` is two classes; a single-class rule loses to it and
        the toggle stays on screen in drawer mode."""
        self.assertIn(".app-sidebar .app-sidebar-toggle { display: none; }", self.css)


class CollapsedSidebarMarkupTests(TestCase):
    """The mark is the way out of a collapsed rail."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="rail.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.markup = self.client.get("/customers/").content.decode("utf-8")

    def test_the_minimized_mark_is_a_button_not_a_link(self):
        """Collapsed, it is the only control at the top of the rail, so the
        obvious click has to be the useful one. Going to the dashboard is
        already the first item in the menu underneath it."""
        self.assertIn('id="app-sidebar-expand"', self.markup)
        expander = re.search(r'<button[^>]*id="app-sidebar-expand"[^>]*>', self.markup)
        self.assertIsNotNone(expander, "the mark should be a button")
        self.assertIn("aria-label", expander.group(0))

    def test_the_expander_says_what_it_does_before_it_is_pressed(self):
        self.assertIn("app-sidebar-expand-hint", self.markup)


class SelectStyleTests(SimpleTestCase):
    """Dropdowns stay native `<select>` elements and are styled as such."""

    def setUp(self):
        self.css = PANEL_CSS.read_text(encoding="utf-8")

    def test_the_native_popup_is_told_which_palette_to_use(self):
        """`color-scheme` is the only handle a page has on the list the browser
        draws itself; without it the popup opens white against a dark panel."""
        self.assertRegex(self.css, r"\.form-select \{[^}]*color-scheme: light dark")

    def test_the_options_are_themed_rather_than_left_to_the_platform(self):
        self.assertIn(".form-select option,", self.css)

    def test_the_placeholder_row_reads_as_an_instruction(self):
        """`fillSelect` writes it with an empty value; it is not a choice."""
        self.assertIn('.form-select option[value=""]', self.css)
