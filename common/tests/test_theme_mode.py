"""Light, dark and system, chosen from the user menu.

The switching is the purchased theme's: `KTThemeMode` binds the menu, resolves
"system" against `prefers-color-scheme`, writes `data-bs-theme` on `<html>`,
and remembers the choice. Bootstrap 5.3 and the theme's own variables do the
rest, which is why no palette is defined in this project.

What this project owns is the part `KTThemeMode` cannot do: it runs on
DOMContentLoaded, and by then a dark-mode reader has already been shown a white
page. The inline script in the head is the fix, and most of what is pinned here
is that script and the markup the theme's JS looks for.
"""

import pathlib
import re

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User


PASSWORD = "Strong-pass-937!"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE_TEMPLATE = REPOSITORY_ROOT / "common" / "templates" / "common" / "base.html"
PRINT_TEMPLATE = REPOSITORY_ROOT / "common" / "templates" / "common" / "print_base.html"


class ThemeModeMarkupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="theme.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.markup = self.client.get("/customers/").content.decode("utf-8")

    def test_the_menu_is_the_container_the_themes_js_looks_for(self):
        """`KTThemeMode.init()` queries this exact attribute; without it the
        three rows render and nothing happens when they are clicked."""
        self.assertIn('data-kt-element="theme-mode-menu"', self.markup)

    def test_all_three_modes_are_offered(self):
        for value in ("light", "dark", "system"):
            self.assertIn(f'data-kt-element="mode" data-kt-value="{value}"', self.markup)

    def test_each_mode_carries_an_icon(self):
        """Asked for as «لوگو های مینیمال و جذاب» — the theme's own set."""
        for icon in ("ki-night-day", "ki-moon", "ki-screen"):
            self.assertIn(icon, self.markup)

    def test_the_switcher_sits_inside_the_user_menu(self):
        """Where it was asked for, and — just as importantly — not in a nested
        dropdown, which KTMenu would position with Popper. Popper is in the
        plugins bundle this deployment does not load."""
        menu_start = self.markup.index('id="user-menu"')
        menu_end = self.markup.index('id="logout-form"')
        self.assertIn(
            'data-kt-element="theme-mode-menu"', self.markup[menu_start:menu_end]
        )

    def test_the_modes_are_buttons_rather_than_links(self):
        """They change a setting; they do not go anywhere.

        Written first as `<a href="#">`, which `KTThemeMode` binds happily —
        and which put three dead links in the shell. `test_ui_connectivity`
        refuses those outright, and in a real browser each click also pushed a
        `#` onto the URL, which is what broke the navigation tests.
        """
        for value in ("light", "dark", "system"):
            self.assertIn(
                f'<button type="button" class="menu-link px-5 w-100 text-start '
                f'border-0 bg-transparent" data-kt-element="mode" data-kt-value="{value}">',
                self.markup,
            )

    def test_the_button_reports_the_current_theme(self):
        """Two icons, one shown, decided by the theme's own CSS from the
        attribute on `<html>` — so it is right on the first frame."""
        self.assertIn("theme-light-show", self.markup)
        self.assertIn("theme-dark-show", self.markup)


class ThemeBootstrapScriptTests(SimpleTestCase):
    """The inline script that beats the first paint."""

    def setUp(self):
        self.template = BASE_TEMPLATE.read_text(encoding="utf-8")
        head = self.template.index("<head>")
        self.head = self.template[head : self.template.index("</head>")]

    def test_the_theme_is_applied_in_the_head_before_the_stylesheets_paint(self):
        self.assertIn("data-bs-theme", self.head)
        self.assertIn("setAttribute", self.head)

    def test_it_runs_ahead_of_the_panel_script_that_would_otherwise_do_it(self):
        """`KTThemeMode` sets the same attribute on DOMContentLoaded, which is
        after the first paint. If this ever moved below the body it would stop
        being a fix and start being a second flash."""
        self.assertLess(
            self.template.index("data-bs-theme"),
            self.template.index("js/scripts.bundle.js"),
        )

    def test_system_is_resolved_on_every_load_rather_than_stored(self):
        """A reader who chose "system" and then changed their OS setting must
        not be given yesterday's answer."""
        self.assertIn("prefers-color-scheme: dark", self.head)
        self.assertIn('localStorage.getItem("data-bs-theme-mode")', self.head)

    def test_a_refused_localstorage_still_renders_a_panel(self):
        """Private mode can throw on access. A panel in the wrong theme is a
        blemish; a panel that does not render is an outage."""
        self.assertIn("catch", self.head)

    def test_the_default_is_the_readers_own_system_setting(self):
        self.assertIn('var defaultThemeMode = "system"', self.head)

    def test_the_stored_keys_are_the_ones_the_themes_js_uses(self):
        """`KTThemeMode` reads `data-bs-theme-mode` for the choice and writes
        `data-bs-theme` for what it resolved to. Diverging on either name means
        the head script and the menu disagree about what was chosen."""
        self.assertIn("data-bs-theme-mode", self.head)
        self.assertIn('setAttribute("data-bs-theme"', self.head)


class PrintedDocumentThemeTests(SimpleTestCase):
    """A document is printed on paper, and paper has no dark mode."""

    def test_the_print_shell_is_its_own_document(self):
        """It does not extend the panel shell, so nothing themes it — which is
        the reason an invoice stays black on white while the panel is dark. It
        is worth pinning: making the print page extend `base.html` would look
        like a tidy-up and would quietly start printing dark invoices."""
        template = PRINT_TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("{% extends", template)
        self.assertNotIn("data-bs-theme", template)
