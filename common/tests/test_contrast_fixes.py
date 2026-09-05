"""Two low-contrast text colours, found and fixed in the same UI/UX audit
(2026-09-05) that confirmed the rest of the panel already matches Metronic.

Both are the same shape of bug the codebase already fixed once for
`.text-muted` (see the comment above `.text-muted` in `dolphin.css`): a
theme-supplied gray reads fine on the Metronic demo's own background, but
falls short of WCAG AA's 4.5:1 for normal text once measured against where
this panel actually puts it.

* `.text-gray-500` is the same `--bs-gray-500` token under a different
  Bootstrap utility name, so it never got `.text-muted`'s fix even though it
  carries real sentences here too — the login page's instruction line, a
  user profile's KPI labels. Measured on a dark card: 3.14:1.
* The login page's brand aside is a *fixed* `#1e1e2d` — it does not follow
  the reader's own light/dark choice, the same reasoning the print sheet
  already uses elsewhere in this file. Its tagline used `.text-gray-400`,
  whose colour *does* follow the reader's theme: 10:1 for a light-mode
  reader (whose page is otherwise light, coincidentally readable here too),
  but only 1.8:1 for a dark-mode reader, on this exact same always-dark
  panel — nowhere near AA. `.login-aside-subtitle` fixes the colour instead
  of leaving it themed, at the one value already proven to read well against
  this exact background regardless of which theme resolved it.
"""

import pathlib

from django.test import Client, SimpleTestCase, TestCase

CSS = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
).read_text(encoding="utf-8")


def _rule(css, selector):
    return css.split(selector, 1)[1].split("}")[0]


class TextGray500ContrastTests(SimpleTestCase):
    def test_text_gray_500_gets_the_same_fix_text_muted_already_has(self):
        self.assertIn(".text-muted,\n.text-gray-500 {", CSS)

    def test_the_fixed_rule_still_stays_inside_the_theme_palette(self):
        rule = _rule(CSS, ".text-muted,\n.text-gray-500 {")
        self.assertIn("var(--bs-gray-700)", rule)
        self.assertIn("!important", rule)


class LoginAsideContrastTests(TestCase):
    def setUp(self):
        self.client = Client()

    def page(self):
        return self.client.get("/login/").content.decode("utf-8")

    def test_the_tagline_no_longer_uses_the_themed_gray(self):
        """That class's colour follows the reader's own theme choice, but the
        aside behind it is a fixed colour that never does.

        The same sentence also appears in the page's `<meta name="description">`
        — matched here as one exact substring including the class, not by
        finding the sentence first, so that meta tag can't be mistaken for it.
        """
        page = self.page()
        self.assertIn('login-aside-subtitle fs-base text-center">سامانه مدیریت ارتباط با مشتری', page)
        self.assertNotIn('text-gray-400 fs-base text-center">سامانه مدیریت ارتباط با مشتری', page)

    def test_the_fixed_colour_is_defined_and_not_a_theme_variable(self):
        rule = _rule(CSS, ".login-aside-subtitle {")
        self.assertIn("#C4CADA", rule)
        self.assertNotIn("var(", rule)
