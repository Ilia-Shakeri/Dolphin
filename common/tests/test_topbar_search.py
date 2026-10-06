"""The topbar search becomes a field in place (2.40.1).

The magnifier grows into the field with a board column's own search motion
(`#order-board .board-search`): only the box's width animates, so the header
keeps its height and its neighbours are pushed, never covered. Results open
under the field. Behaviour that was already right stays: debounce, a stale
answer never painting last (now also aborted), Ctrl/⌘+K, Escape back to the
magnifier, Enter opens a result. New: ↑/↓ with `aria-activedescendant`, a
polite result count, Arabic letters and digits normalised.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

from common import search
from common.tests.test_global_search import SearchFixtures

ROOT = Path(__file__).resolve().parents[2]
JS_ROOT = ROOT / "common" / "static" / "common" / "js"
SCRIPT = (JS_ROOT / "shell" / "search.js").read_text(encoding="utf-8")
POPOVER = (JS_ROOT / "ui" / "popover.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
BASE = (ROOT / "common" / "templates" / "common" / "base.html").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _rule(selector):
    return CSS.split(selector)[1].split("}")[0]


def _markup():
    start = BASE.index('id="global-search-wrap"')
    return BASE[start:BASE.index('{% if "reminders" in features %}', start)]


class FieldInPlaceTests(SimpleTestCase):
    def test_icon_field_and_close_glyph_are_one_box(self):
        markup = _markup()
        box = markup.index('id="global-search-box"')
        self.assertLess(box, markup.index('id="global-search-toggle"'))
        self.assertLess(markup.index('id="global-search-toggle"'), markup.index('id="global-search-input"'))
        self.assertLess(markup.index('id="global-search-input"'), markup.index('id="global-search-close"'))
        # The field is no longer inside the results panel.
        self.assertLess(markup.index('id="global-search-close"'), markup.index('id="global-search-menu"'))

    def test_the_box_has_the_header_controls_height(self):
        """The same `h-40px` utility as the toggle, bell and avatar."""
        self.assertIn('class="topbar-search h-40px"', _markup())

    def test_only_the_width_animates_with_the_board_search_motion(self):
        rule = _rule(".topbar-search {")
        self.assertIn("transition: min-width var(--dolphin-dur) var(--dolphin-ease), width var(--dolphin-dur) var(--dolphin-ease)", rule)
        self.assertIn("overflow: hidden", rule)
        self.assertNotIn("height", rule.replace("min-width", "").replace("width", ""))
        board = _rule("#order-board .board-search {")
        self.assertIn("var(--dolphin-dur) var(--dolphin-ease)", board)

    def test_results_are_as_wide_as_the_field(self):
        rule = _rule("#global-search-menu {\n    position: absolute;")
        self.assertIn("width: 100%", rule)
        self.assertIn("22.5rem", _rule(".topbar-search {"))  # 360px floor

    def test_an_idle_panel_is_not_drawn(self):
        self.assertIn("#global-search-menu[data-idle] {\n    display: none;", CSS)
        self.assertIn("data-idle>", _markup())

    def test_on_a_phone_the_open_field_covers_the_header(self):
        block = CSS.split("@media (max-width: 575.98px) {")[1].split("\n}\n")[0]
        self.assertIn(".topbar-search-open {", block)
        self.assertIn("width: calc(100vw - 1.5rem)", block)

    def test_reduced_motion_turns_the_animation_off(self):
        self.assertRegex(CSS, r"prefers-reduced-motion: reduce\) \{\s*\.topbar-search,\s*\.topbar-search-close \{\s*transition: none;")


class ComboboxTests(SimpleTestCase):
    def test_the_field_is_a_combobox_over_a_listbox(self):
        markup = _markup()
        self.assertIn('role="combobox"', markup)
        self.assertIn('aria-controls="global-search-body"', markup)
        self.assertIn('id="global-search-body" class="global-search-body px-3" role="listbox"', markup)
        self.assertIn('aria-live="polite"', markup)

    def test_arrow_keys_move_the_active_descendant(self):
        self.assertIn('event.key === "ArrowDown" || event.key === "ArrowUp"', SCRIPT)
        self.assertIn('input.setAttribute("aria-activedescendant", all[active].id)', SCRIPT)
        self.assertIn('link.setAttribute("role", "option")', SCRIPT)

    def test_enter_opens_the_highlighted_result_or_the_first(self):
        self.assertIn('const chosen = options()[active] || body.querySelector(".topbar-list-item");', SCRIPT)

    def test_the_count_is_announced(self):
        self.assertIn("announce(data.count ?", SCRIPT)


class OpenCloseTests(SimpleTestCase):
    def test_the_field_counts_as_inside_for_outside_clicks(self):
        self.assertIn("inside: box,", SCRIPT)
        self.assertIn("if (entry.inside && entry.inside.contains(event.target)) return;", POPOVER)

    def test_escape_returns_focus_to_the_magnifier(self):
        """Escape is the shared popover rule, which focuses the toggle."""
        self.assertIn("open.forEach((entry) => { entry.close(); entry.toggle.focus(); });", POPOVER)

    def test_the_close_glyph_closes_and_returns_focus(self):
        body = SCRIPT.split('closer.addEventListener("click"')[1].split("});")[0]
        self.assertIn("popover.close();", body)
        self.assertIn("toggle.focus();", body)

    def test_an_empty_field_folds_away_on_blur(self):
        body = SCRIPT.split('addEventListener("focusout"')[1].split("});")[0]
        self.assertIn("if (!input.value.trim() && popover.isOpen()) popover.close();", body)

    def test_closed_field_is_out_of_the_tab_order(self):
        self.assertRegex(_markup(), r'id="global-search-input"[^>]*tabindex="-1"')
        self.assertIn("input.tabIndex = 0;", SCRIPT)


class RequestTests(SimpleTestCase):
    def test_a_newer_query_aborts_the_one_in_flight(self):
        self.assertIn("new AbortController()", SCRIPT)
        self.assertIn("if (inFlight) inFlight.abort();", SCRIPT)
        self.assertIn("{signal: controller.signal}", SCRIPT)

    def test_the_stale_answer_guard_stays(self):
        self.assertEqual(SCRIPT.count("if (mine !== sequence) return;"), 2)

    def test_the_debounce_stays(self):
        self.assertIn("const SEARCH_DEBOUNCE_MS = 250;", SCRIPT)
        self.assertIn("const MIN_QUERY_LENGTH = 2;", SCRIPT)


@skipUnless(NODE, "node is not installed")
class NormaliseTests(SimpleTestCase):
    def test_arabic_letters_and_digits_become_persian(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "digits.mjs"
            shutil.copyfile(JS_ROOT / "core" / "digits.js", target)
            probe = Path(tmp) / "probe.mjs"
            probe.write_text(
                'import {normalizeSearchText} from "./digits.mjs";\n'
                'console.log(JSON.stringify(["علي كريمي", "٠٩١٢", "موسى", "۰۹۱۲ abc"].map(normalizeSearchText)));\n',
                encoding="utf-8",
            )
            out = subprocess.run([NODE, str(probe)], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        self.assertEqual(json.loads(out), ["علی کریمی", "۰۹۱۲", "موسی", "۰۹۱۲ abc"])


class ServerNormaliseTests(SearchFixtures):
    def test_arabic_letters_find_persian_names(self):
        self.a_customer("علی کریمی", actor=self.manager)
        result = search.search(self.manager, "علي كريمي")
        self.assertEqual(result["query"], "علی کریمی")
        self.assertGreaterEqual(result["count"], 1)


class HeaderStackingTests(SimpleTestCase):
    def test_panels_open_above_the_page_on_a_phone(self):
        """The header's blur makes it a stacking context; below `lg` it is in
        the flow, so without a z-index its panels opened behind the first card."""
        block = CSS.split("#dolphin_app_header.app-header {\n    backdrop-filter")[1]
        rule = block.split("@media (max-width: 991.98px) {")[1].split("}")[0]
        self.assertIn("position: relative", rule)
        self.assertIn("z-index: 105", rule)


class CleanOpenFieldTests(SimpleTestCase):
    """2.40.18: the open field shows no blue ring and no blue square."""

    def test_no_focus_ring_on_the_box(self):
        self.assertNotIn(".topbar-search-open:focus-within", CSS)

    def test_the_field_beats_the_panels_keyboard_ring(self):
        rule = CSS.split("#global-search-input:focus,\n#global-search-input:focus-visible {")[1].split("}")[0]
        self.assertIn("outline: none", rule)

    def test_the_magnifier_has_no_tint_while_open(self):
        self.assertIn(".topbar-search-open #global-search-toggle:hover", CSS)
        rule = CSS.split(".topbar-search-open #global-search-toggle:focus {")[1].split("}")[0]
        self.assertIn("background-color: transparent !important", rule)
