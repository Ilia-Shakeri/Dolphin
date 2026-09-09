"""`common.color`: deriving a full set of Bootstrap/Metronic primary-colour
CSS custom properties from one hex value an admin picked.

What is worth proving:

* validation actually rejects the shapes it claims to (missing `#`, wrong
  length, non-hex characters) and normalises case, since a wrongly-cased
  value stored inconsistently would make two identical colours compare as
  different rows;
* the derived tokens are internally consistent — the RGB triplet actually
  matches the hex value it was derived from, the "active" shade is really
  darker, `light` differs between light and dark mode, and a very light or
  very dark accent still gets a readable inverse text colour;
* `accent_theme_css` degrades to `None` for no colour, so a caller can gate
  on it with a single `if`, and never leaks an `!important` or the vendor's
  own tokens.
"""

from django.test import SimpleTestCase

from common.color import (
    DEFAULT_ACCENT,
    accent_theme_css,
    accent_theme_variables,
    is_valid_hex_color,
    normalize_hex_color,
)


class ValidationTests(SimpleTestCase):
    def test_a_well_formed_hex_color_is_valid(self):
        self.assertTrue(is_valid_hex_color("#1b84ff"))
        self.assertTrue(is_valid_hex_color("#1B84FF"))

    def test_missing_hash_is_invalid(self):
        self.assertFalse(is_valid_hex_color("1b84ff"))

    def test_wrong_length_is_invalid(self):
        self.assertFalse(is_valid_hex_color("#1b84f"))
        self.assertFalse(is_valid_hex_color("#1b84ff0"))

    def test_non_hex_characters_are_invalid(self):
        self.assertFalse(is_valid_hex_color("#zzzzzz"))

    def test_blank_is_invalid(self):
        self.assertFalse(is_valid_hex_color(""))
        self.assertFalse(is_valid_hex_color(None))

    def test_normalize_lower_cases_the_value(self):
        self.assertEqual(normalize_hex_color("#1B84FF"), "#1b84ff")

    def test_normalize_raises_on_an_invalid_value(self):
        with self.assertRaises(ValueError):
            normalize_hex_color("not-a-color")


class DerivationTests(SimpleTestCase):
    def test_the_rgb_triplet_matches_the_source_hex(self):
        variables = accent_theme_variables("#1b84ff")
        self.assertEqual(variables["bs-primary"], "#1b84ff")
        self.assertEqual(variables["bs-primary-rgb"], "27, 132, 255")

    def test_the_active_shade_is_darker_than_the_base(self):
        variables = accent_theme_variables("#1b84ff")
        base_sum = sum(int(variables["bs-primary"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        active_sum = sum(int(variables["bs-primary-active"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        self.assertLess(active_sum, base_sum)

    def test_light_and_dark_mode_get_different_light_tint_tokens(self):
        css = accent_theme_css("#1b84ff")
        light_block = css.split("[data-bs-theme=light]")[1].split("[data-bs-theme=dark]")[0]
        dark_block = css.split("[data-bs-theme=dark]")[1]
        light_tint = light_block.split("--bs-primary-light:")[1].split(";")[0]
        dark_tint = dark_block.split("--bs-primary-light:")[1].split(";")[0]
        self.assertNotEqual(light_tint, dark_tint)
        # Light mode tints toward white — the tint should read as pale.
        self.assertGreater(int(light_tint.lstrip("#")[:2], 16), 200)
        # Dark mode tints toward black — the tint should read as dark.
        self.assertLess(int(dark_tint.lstrip("#")[:2], 16), 80)

    def test_a_light_accent_gets_a_dark_inverse_text_color(self):
        variables = accent_theme_variables("#f5f5f5")
        self.assertEqual(variables["bs-primary-inverse"], "#071437")

    def test_a_dark_accent_gets_a_white_inverse_text_color(self):
        variables = accent_theme_variables("#0a0a2a")
        self.assertEqual(variables["bs-primary-inverse"], "#ffffff")

    def test_links_are_routed_through_the_same_accent(self):
        variables = accent_theme_variables("#1b84ff")
        self.assertEqual(variables["bs-link-color"], "#1b84ff")

    def test_no_color_produces_no_css(self):
        self.assertIsNone(accent_theme_css(""))
        self.assertIsNone(accent_theme_css(None))

    def test_the_css_carries_no_important_and_both_theme_selectors(self):
        css = accent_theme_css(DEFAULT_ACCENT)
        self.assertNotIn("!important", css)
        self.assertIn("[data-bs-theme=light]", css)
        self.assertIn("[data-bs-theme=dark]", css)
