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

    def test_the_override_sheet_leaves_the_collapsed_sidebar_to_the_theme(self):
        """Three releases of rules used to live here. None of them do now.

        The theme collapses the sidebar by itself — the two logos, the faded
        titles, the 75px width and hover-to-peek are all its own, and the
        vendor's demo does it with no custom CSS at all. Everything written here
        was working around one bug in this project's markup, not in the theme:
        the brand link carried Bootstrap's `d-flex`, which is `!important` and
        beat the theme's `display: none`, so the wide block stayed in the flow
        and — a flex item being `min-width: auto` — held the sidebar open at its
        own content width.

        The fix is in the markup: `d-flex` sits on a span inside the link. This
        test guards against the overrides creeping back, because each of them
        looked reasonable in isolation and together they defeated the peek.
        """
        forbidden = (
            # The logo swap, which the theme does from its own two rules.
            "app-sidebar-logo-minimize { display",
            "app-sidebar-logo-default { display",
            # A guard for a re-peek that does not happen: the toggle travels
            # with the sidebar's edge, so collapsing leaves the pointer outside
            # the rail already.
            "peek-suspended",
        )
        for rule in forbidden:
            with self.subTest(rule=rule):
                self.assertNotIn(rule, self.css, rule)
        # The toggle is placed by the theme's own utilities now. That retired a
        # hand-rolled `inset-inline-start`, which had caused two RTL bugs — the
        # theme's RTL build resolves `start-100` correctly on its own.
        markup = (
            REPOSITORY_ROOT / "common" / "templates" / "common" / "base.html"
        ).read_text(encoding="utf-8")
        toggle = re.search(r'<button id="kt_app_sidebar_toggle".*?>', markup, re.S).group(0)
        for utility in ("position-absolute", "top-50", "start-100", "translate-middle", "rotate"):
            with self.subTest(utility=utility):
                self.assertIn(utility, toggle)

    def test_the_brand_flex_is_not_on_the_element_the_theme_hides(self):
        """The whole reason the overrides above are unnecessary.

        `d-flex` is `!important`; the theme's collapse rule is not. With the
        utility on the link the theme could never hide it.
        """
        markup = (
            REPOSITORY_ROOT / "common" / "templates" / "common" / "base.html"
        ).read_text(encoding="utf-8")
        link = re.search(r'<a class="brand app-sidebar-logo-default[^"]*"', markup)
        self.assertIsNotNone(link)
        self.assertNotIn("d-flex", link.group(0))

    def test_each_state_declares_its_own_width_so_the_sidebar_can_reopen(self):
        """A defect in the theme, not a workaround for our own markup.

        The theme drives the width from one declaration,
        `.app-sidebar { width: var(--bs-app-sidebar-width) }`, and collapses by
        changing that variable. Collapsing works. Expanding does not: the
        variable returns to 265px and the used width stays at 75px, so a
        collapsed sidebar can never be reopened.

        Reproduced in the vendor's own demo served locally, with none of this
        project's code loaded — after its own toggle, the variable read 265px
        while the computed width read 75px. Giving each state its own `width`
        declaration makes the matched rule change rather than the value inside
        one, and that animates in both directions.
        """
        self.assertRegex(
            self.css,
            r"@media \(min-width: 992px\) \{\s*\.app-sidebar \{"
            r"\s*width: var\(--bs-app-sidebar-width-actual\)",
        )
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \{\s*width: 75px',
        )

    def test_the_rail_width_matches_the_theme(self):
        """The one theme number copied into the override sheet, guarded so it
        cannot drift silently."""
        theme = (
            REPOSITORY_ROOT / "assets" / "css" / "style.bundle.rtl.css"
        ).read_text(encoding="utf-8", errors="ignore")
        declared = re.search(
            r"\[data-kt-app-sidebar-minimize=on\]\s*\{[^}]*?"
            r"--bs-app-sidebar-width:\s*([0-9]+px)",
            theme,
        )
        self.assertIsNotNone(declared, "the theme no longer declares a rail width")
        self.assertRegex(
            self.css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \{\s*width: '
            + re.escape(declared.group(1)),
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

    def test_the_minimized_mark_is_a_plain_link_not_a_control(self):
        """1.3.11 made this a button that expanded the sidebar and swapped the
        mark for a chevron on hover. Withdrawn in 1.3.13 as confusing: a logo
        that becomes a different control under the pointer does not tell you
        which of the two you are about to get. It is a link home now, exactly
        like the wide brand above it."""
        self.assertNotIn('id="app-sidebar-expand"', self.markup)
        self.assertNotIn("app-sidebar-expand-hint", self.markup)
        mark = re.search(
            r'<a[^>]*class="[^"]*app-sidebar-logo-minimize[^"]*"[^>]*>', self.markup
        )
        self.assertIsNotNone(mark, "the collapsed mark should be a link")
        self.assertIn('href="/"', mark.group(0))

    def test_reopening_belongs_to_the_control_that_closed_it(self):
        """The floating toggle was hidden while collapsed in 1.3.11, because the
        mark had taken over that job. With the mark inert again it has to be
        reachable, or a collapsed sidebar has no way back."""
        css = PANEL_CSS.read_text(encoding="utf-8")
        self.assertNotRegex(
            css,
            r'\[data-kt-app-sidebar-minimize="on"\] \.app-sidebar \.app-sidebar-toggle \{'
            r"\s*display: none",
        )

    def test_the_shell_asks_the_theme_for_hover_to_peek(self):
        """The whole feature is this attribute: the theme implements the peek in
        CSS with no JavaScript behind it."""
        self.assertIn('data-kt-app-sidebar-hoverable="true"', self.markup)


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
