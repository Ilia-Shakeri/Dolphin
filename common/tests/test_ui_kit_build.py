"""The served UI kit is what `ui_kit/` builds for the code that uses it (2.40.43).

`scripts/build_ui_kit.py` writes the theme and icon stylesheets, the icon fonts
and the vendor bundles from the kit's full sources, keeping only what a
template, a script or a Python module uses. These tests fail when the served
files lag the code — a theme class or an icon used for the first time, a
vendor file swapped in `ui_kit/vendor/` — so the remedy is always the same
command, never a class that silently renders unstyled:

    python scripts/build_ui_kit.py
"""

import importlib.util
import unittest
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("build_ui_kit", ROOT / "scripts" / "build_ui_kit.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
REBUILD = "run `python scripts/build_ui_kit.py` and commit what it writes"

try:
    import fontTools  # noqa: F401

    HAS_FONTTOOLS = True
except ImportError:
    HAS_FONTTOOLS = False


class UiKitBuildTests(SimpleTestCase):
    def test_the_served_stylesheets_and_bundles_cover_what_the_code_uses(self):
        self.assertEqual(BUILD.check(fonts=False), [], REBUILD)

    @unittest.skipUnless(HAS_FONTTOOLS, "fontTools (a development tool) is not installed")
    def test_the_icon_fonts_hold_every_glyph_their_stylesheet_draws(self):
        self.assertEqual(BUILD.check(), [], REBUILD)

    def test_an_icon_is_never_built_from_a_bare_name(self):
        """`di-${name}` would keep every icon; the class goes in the data whole."""
        _tokens, prefixes = BUILD.usage()
        self.assertNotIn("di-", prefixes)

    def test_the_kit_sources_never_ship(self):
        ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("ui_kit", ignore)
        for name in BUILD.BUNDLES.values():
            for file in name[1]:
                self.assertTrue((ROOT / "ui_kit" / "vendor" / file).is_file(), file)

    def test_a_vendor_bundle_names_what_built_it(self):
        for name in BUILD.BUNDLES:
            served = (BUILD.SERVED / name).read_text(encoding="utf-8")
            self.assertTrue(served.startswith("/*!\n * Dolphin UI kit — "), name)
            self.assertIn("scripts/build_ui_kit.py", served.split("*/", 1)[0])

    def test_only_woff_icon_fonts_are_served(self):
        fonts = BUILD.SERVED / "fonts" / "dolphin-icons"
        self.assertEqual(sorted(path.suffix for path in fonts.iterdir()), [".woff", ".woff", ".woff"])
        self.assertNotIn(".ttf", (BUILD.SERVED / "css" / "dolphin-plugins.rtl.css").read_text(encoding="utf-8"))
