"""The popup calendar every `data-jalali` field opens on focus/click.

Product-owner request: every date/time input should open a small calendar
for picking a value, themed like the rest of the panel in both light and
dark mode, rather than being a plain typed field with no visual affordance.

Built in-house rather than adapted from a vendor picker: the theme bundles
flatpickr (`assets/plugins/global/plugins.bundle.js`), but it draws its grid
straight from JS `Date` with no hook for a different calendar system, and
this codebase already carries a complete, tested Jalali <-> Gregorian
conversion layer (`common/jalali.py` on the server, its JS mirror in
`dolphin-app.js` — pinned to each other by `test_jalali.py`'s own
`FrontendParityTests`). `openJalaliPicker()` reuses that layer rather than
inventing a second one, and reuses the theme's own dropdown shell
(`.menu-sub-dropdown`, the same classes `#user-menu` and
`setupListFilterPopovers()`'s panel already use) rather than a bespoke
design, so only the day grid itself is custom CSS — the one piece Metronic
has no component for.

What is worth proving here, none of which a full browser run through this
repository's Django-only test suite can exercise directly:

* every `data-jalali` field gets the picker, generically, the same way
  `setupListFilterPopovers()` reaches every `.list-filters` form;
* the grid math is the shared conversion layer, not a re-implementation;
* the popup is themed via the same `--bs-*` tokens and `.btn-*` state
  classes the rest of the panel already uses — no hardcoded colour that
  would only look right in one mode;
* a field inside a native `<dialog>` gets a picker parented inside that
  dialog, not one that would paint behind its top-layer backdrop;
* typing the date directly still works exactly as it did before this
  feature existed — the picker is additive, not a replacement.
"""

import pathlib

from django.test import SimpleTestCase

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "common" / "templates" / "common"

#: Every template known to carry a Jalali field, so the picker's reach can
#: be checked directly rather than sampled.
JALALI_FIELD_TEMPLATES = sorted(
    path.relative_to(TEMPLATES).as_posix()
    for path in TEMPLATES.rglob("*.html")
    if "data-jalali=" in path.read_text(encoding="utf-8")
)


def _function_body(name, end_marker):
    start = SCRIPT.index(f"function {name}(")
    end = SCRIPT.index(end_marker, start)
    return SCRIPT[start:end]


OPEN_PICKER_BODY = _function_body("openJalaliPicker", "\n    function setupJalaliInputs(")
SETUP_BODY = _function_body(
    "setupJalaliInputs", "\n    async function loadAllPages("
)
JALALI_WEEKDAY_BODY = _function_body("jalaliWeekday", "\n    let closeOpenJalaliPicker")


class ReachTests(SimpleTestCase):
    def test_the_known_set_of_templates_still_carries_a_jalali_field(self):
        """Guards the fixture above, not the feature: if a page's date field
        stopped carrying `data-jalali`, the generic wiring below would
        silently skip it and this would be the only thing to notice."""
        self.assertGreaterEqual(len(JALALI_FIELD_TEMPLATES), 15, JALALI_FIELD_TEMPLATES)

    def test_every_jalali_field_is_wired_generically_not_a_hand_picked_list(self):
        self.assertIn('root.querySelectorAll("input[data-jalali]")', SETUP_BODY)
        self.assertIn("openJalaliPicker(field)", SETUP_BODY)
        # No page name appears in the wiring — it cannot be, since the same
        # loop has to reach every one of the templates listed above.
        for name in ("lead", "invoice", "payment", "installment"):
            with self.subTest(name=name):
                self.assertNotIn(f'"{name}', SETUP_BODY)

    def test_typing_the_date_by_hand_still_works_unchanged(self):
        """The picker is additive. `parseJalaliInput` on blur is the same
        validation this field had before `openJalaliPicker` existed."""
        self.assertIn('field.addEventListener("blur"', SETUP_BODY)
        self.assertIn("parseJalaliInput(field.value", SETUP_BODY)


class GridMathReuseTests(SimpleTestCase):
    """The calendar grid is the shared conversion layer, not a second one."""

    def test_it_reuses_the_shared_jalali_conversion_functions(self):
        for helper in (
            "jalaliWeekday(", "gregorianToJalali(", "jalaliMonthLength(", "JALALI_MONTH_NAMES[",
        ):
            with self.subTest(helper=helper):
                self.assertIn(helper, OPEN_PICKER_BODY)
        # `jalaliWeekday` (used above to lay out the grid's leading blanks)
        # is itself built on the same shared conversion, not a fresh one.
        self.assertIn("jalaliToGregorian(", JALALI_WEEKDAY_BODY)

    def test_it_does_not_reimplement_jalali_leap_year_or_epoch_math(self):
        """A second implementation of leap-year math is exactly the kind of
        drift `test_jalali.py`'s `FrontendParityTests` exists to catch for
        the *shared* functions — a picker-local copy would drift silently
        instead, unpinned by that test."""
        for token in ("isJalaliLeap", "JALALI_EPOCH", "JALALI_MONTH_OFFSETS"):
            with self.subTest(token=token):
                self.assertNotIn(token, OPEN_PICKER_BODY)


class ShellReuseTests(SimpleTestCase):
    def test_the_panel_is_the_themes_own_dropdown_shell(self):
        """Background, box-shadow, border-radius and the fade/move-in on
        open all come from `.menu-sub-dropdown` (style.bundle.rtl.css) —
        the same classes `#user-menu` and the filter popover's own panel
        already use, not a bespoke surface."""
        self.assertIn("menu menu-sub menu-sub-dropdown menu-column jalali-picker", OPEN_PICKER_BODY)

    def test_it_opens_and_closes_like_the_other_header_dropdowns(self):
        self.assertIn('panel.classList.add("show")', OPEN_PICKER_BODY)
        self.assertNotIn("data-kt-menu-trigger", OPEN_PICKER_BODY)

    def test_escape_closes_only_the_picker_not_a_parent_dialog(self):
        """`stopPropagation` here is load-bearing: a field inside a
        `<dialog>` must not also close that dialog on the same keypress."""
        self.assertIn('event.key === "Escape"', OPEN_PICKER_BODY)
        self.assertIn("event.stopPropagation();", OPEN_PICKER_BODY)
        self.assertIn("field.focus();", OPEN_PICKER_BODY)

    def test_a_field_inside_a_dialog_gets_a_picker_parented_inside_it(self):
        """A native `<dialog>` renders in the browser's own top layer; a
        picker appended to `<body>` would paint *behind* an open dialog's
        backdrop and be unreachable."""
        self.assertIn('field.closest("dialog") || document.body', OPEN_PICKER_BODY)


class InteractionTests(SimpleTestCase):
    def test_a_date_only_field_closes_on_the_first_day_click(self):
        self.assertIn("if (wantsTime) {", OPEN_PICKER_BODY)
        self.assertIn("renderDays();\n                    } else {\n                        close();", OPEN_PICKER_BODY)

    def test_a_datetime_field_offers_hour_and_minute_and_a_confirm_step(self):
        self.assertIn('hourSelect.setAttribute("aria-label", "ساعت")', OPEN_PICKER_BODY)
        self.assertIn('minuteSelect.setAttribute("aria-label", "دقیقه")', OPEN_PICKER_BODY)
        self.assertIn('confirmBtn.textContent = "تأیید"', OPEN_PICKER_BODY)

    def test_the_exact_stored_minute_is_offered_even_off_the_five_minute_grid(self):
        """Five-minute steps cover picking a new value; they must never
        silently round away a minute the field already had."""
        self.assertIn("new Set([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, minute])", OPEN_PICKER_BODY)

    def test_committing_dispatches_the_events_existing_listeners_expect(self):
        """`input`/`change` for anything already watching the field, `blur`
        so the pre-existing validity/error-clearing handler runs the same
        way it does after typing."""
        for event_name in ('"input"', '"change"', '"blur"'):
            with self.subTest(event=event_name):
                self.assertIn(f"new Event({event_name}", OPEN_PICKER_BODY)

    def test_the_grid_is_a_constant_six_weeks_so_navigating_months_does_not_resize_it(self):
        self.assertIn("const totalCells = 42;", OPEN_PICKER_BODY)


class StylingTests(SimpleTestCase):
    def test_the_panel_is_fixed_positioned_and_computed_in_viewport_coordinates(self):
        """Not `position: absolute`: the field can sit inside a nested
        popover (a `list-filters` panel) or a scrollable `<dialog>`, and
        `position: fixed` is the one positioning mode that does not need to
        know what — if anything — establishes its containing block."""
        self.assertIn(".jalali-picker {", CSS)
        rule = CSS.split(".jalali-picker {")[1].split("}")[0]
        self.assertIn("position: fixed", rule)

    def test_grid_and_state_colours_are_theme_tokens_not_hardcoded(self):
        """Light/dark mode need no separate rule here because every colour
        already comes from a `--bs-*` custom property or a theme `.btn-*`
        state class — both already redefined per mode elsewhere."""
        for token in ("var(--bs-gray-800)", "var(--bs-text-muted)", "var(--bs-border-color)"):
            with self.subTest(token=token):
                self.assertIn(token, CSS)
        for day_class in ("btn-primary", "btn-active-light-primary", "btn-color-gray-700"):
            with self.subTest(day_class=day_class):
                self.assertIn(day_class, OPEN_PICKER_BODY)
        self.assertNotIn("#", CSS.split(".jalali-picker {")[1].split(".jalali-picker-time select {")[0])

    def test_day_cells_override_only_size_keeping_the_themes_own_button_states(self):
        """`.btn.btn-icon` alone sizes to `calc(1.5em + 1.55rem + 2px)` —
        right for a lone icon button, far too wide for seven across one
        row — but everything else that class pair gives a day cell
        (centering, radius, hover/active transitions, focus ring) is worth
        keeping, so only the size is overridden."""
        self.assertIn(".jalali-picker-day {", CSS)
        rule = CSS.split(".jalali-picker-day {")[1].split("}")[0]
        self.assertIn("height:", rule)
        self.assertIn("width:", rule)
        self.assertIn('"btn btn-icon jalali-picker-day ', OPEN_PICKER_BODY)
