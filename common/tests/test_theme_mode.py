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
        import re

        for value in ("light", "dark", "system"):
            # The element type and its two data attributes are the contract;
            # the utility classes on it are presentation and may change.
            pattern = (
                r'<button[^>]*data-kt-element="mode"[^>]*data-kt-value="' + value + r'"'
            )
            self.assertRegex(self.markup, pattern)
            self.assertNotRegex(
                self.markup,
                r'<a[^>]*data-kt-element="mode"[^>]*data-kt-value="' + value + r'"',
            )

    def test_the_three_modes_sit_behind_one_row(self):
        """One entry that says «حالت», with the choice in a popup beside it."""
        self.assertIn("data-theme-mode-item", self.markup)
        self.assertIn('id="theme-mode-trigger"', self.markup)
        self.assertIn('id="theme-mode-popup"', self.markup)
        self.assertIn(">حالت<", self.markup)

    def test_the_row_says_which_theme_is_on_without_script(self):
        """The trigger carries both icons; the theme's CSS picks one from
        `data-bs-theme`, so it is right on the very first frame."""
        trigger = self.markup[
            self.markup.index('id="theme-mode-trigger"') : self.markup.index('id="theme-mode-popup"')
        ]
        self.assertIn("theme-light-show", trigger)
        self.assertIn("theme-dark-show", trigger)

    def test_the_popup_states_its_own_display(self):
        """It carries the theme's `.menu-sub`, which is `display: none` until
        KTMenu adds `.show`. Nothing adds `.show` here — this project's script
        opens it — so without an explicit display it stayed 0x0 forever."""
        css = (REPOSITORY_ROOT / "common" / "static" / "common" / "forooshbin.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".theme-mode-popup { display: block; }", css)
        self.assertIn(".theme-mode-popup[hidden] { display: none; }", css)

    def test_the_popup_can_flip_to_whichever_side_has_room(self):
        """The user menu sits against one edge, so the preferred side is not
        always the one with space."""
        css = (REPOSITORY_ROOT / "common" / "static" / "common" / "forooshbin.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".theme-mode-popup.is-flipped", css)

    def test_the_button_reports_the_current_theme(self):
        """Two icons, one shown, decided by the theme's own CSS from the
        attribute on `<html>` — so it is right on the first frame."""
        self.assertIn("theme-light-show", self.markup)
        self.assertIn("theme-dark-show", self.markup)


class AccountMenuTests(TestCase):
    """The account menu carries the account's own things."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="acct.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.markup = self.client.get("/customers/").content.decode("utf-8")

    def test_the_button_wears_a_person(self):
        """1.3.8 put the theme's sun/moon here, which made the account control
        look like a theme switch. The theme reports itself on the «حالت» row
        inside the menu, which is where a reader looks for it."""
        button = self.markup[
            self.markup.index('id="user-menu-toggle"') : self.markup.index('id="user-menu"')
        ]
        self.assertIn("ki-user", button)
        self.assertNotIn("theme-light-show", button)

    def test_the_profile_opens_a_dialog_rather_than_a_dashboard_anchor(self):
        """It was a card on the home page, so editing it from anywhere else
        meant navigating away and losing what you were doing."""
        self.assertIn('id="profile-dialog"', self.markup)
        entry = re.search(r'<[^>]*id="open-profile"[^>]*>', self.markup).group(0)
        self.assertTrue(entry.startswith("<button"), entry)
        self.assertNotIn("href", entry)

    def test_the_profile_form_moved_rather_than_being_copied(self):
        """Two copies of one form would drift, and `setupProfile()` binds by id
        — so a second `#profile-form` would make which one it fills a matter of
        document order."""
        self.assertEqual(self.markup.count('id="profile-form"'), 1)
        dialog = self.markup[self.markup.index('id="profile-dialog"') :]
        self.assertIn('id="profile-form"', dialog[: dialog.index("</dialog>")])

    def test_the_dashboard_no_longer_carries_the_profile(self):
        home = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('id="profile-card"', home)
        self.assertEqual(home.count('id="profile-form"'), 1, "only the dialog's")


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
