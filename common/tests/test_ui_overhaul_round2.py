"""Round 2 of the product owner's UI/UX follow-up (2026-09-21) — twelve fixes
and additions on top of the five batches already shipped as `2.14.0`.

One class per item, added as each item lands, in the same source-scanning
style as `test_ui_overhaul_*` (`ui_overhaul_helpers`): what a browser check
already confirmed once is pinned here against silent regressions, not
re-verified.
"""

from django.test import SimpleTestCase

from common.tests.ui_overhaul_helpers import CODE, SCRIPT, TEMPLATES, function_body, markup, rule

PAYMENTS_LIST = (TEMPLATES / "payments" / "list.html").read_text(encoding="utf-8")


def exact_rule(selector, source=CODE):
    """`rule()`'s declarations, but for the one block whose selector is
    exactly this — not merely contains it as a substring. `rule("
    .postal-mini-step")` also matches `.postal-mini-stepper` and
    `.postal-mini-step-current`; this pins the block by its own opening
    line (`<selector> {`, this file's one-selector-per-line convention)."""
    marker = f"\n{selector} {{"
    start = source.index(marker) + len(marker)
    end = source.index("}", start)
    return source[start:end]


class JalaliPickerTitleSpacingTests(SimpleTestCase):
    """Item 1 — the month/year title in the date picker read as one jumbled
    word: 2026-09-20 split it into two buttons (`monthBtn`/`yearBtn` in
    `openJalaliPicker`, dolphin-app.js) so each half opens its own grid, but
    both buttons carry the base `.btn` class the nav-arrow rule also
    selects — `.jalali-picker .jalali-picker-header .btn` forced them to a
    27px square meant for a lone icon, leaving ~0 content width once padding
    was accounted for. The text was clipped to an unreadable sliver.
    """

    def test_nav_arrow_rule_excludes_the_title_buttons(self):
        # The fixed-width icon-button rule must no longer also catch the
        # two title buttons — that was the whole bug.
        self.assertIn(
            ".jalali-picker .jalali-picker-header .btn:not(.jalali-picker-scope)",
            CODE,
        )

    def test_title_is_a_flex_row_with_a_real_gap(self):
        # `display:flex` + `gap` is what actually separates the two buttons;
        # without it they sat back to back with zero space between them
        # regardless of their own padding.
        body = rule(".jalali-picker-title")
        self.assertIn("display: flex", body)
        self.assertRegex(body, r"gap:\s*0\.3rem")

    def test_scope_padding_wins_over_the_vendor_button(self):
        # Metronic's own `.btn:not(...).btn-sm` (eight `:not()` clauses) has
        # higher specificity than any selector built from this component's
        # own classes, so the padding override needs `!important` to
        # actually apply — without it the buttons kept the vendor's roomy
        # text-button padding despite the width fix, which is what had
        # pushed a long month name out of the title's own space.
        body = rule(".jalali-picker .jalali-picker-scope")
        self.assertIn("!important", body)
        self.assertIn("overflow: hidden", body)


class LineChartAxisLabelTests(SimpleTestCase):
    """Item 2 — the bottom axis of every line/mixed chart (`renderAreaChart`,
    `renderMixedChart`) was truncating its own already-thinned date labels
    to unreadable garbage: measured live on the dashboard trend widget, a
    full `۱۴۰۵/۰۴/۱۵` came out `۱…`, and even the shortened `۰۴/۱۵` this fix
    introduces still came out `۰۴…` before `trim` was removed. The
    untruncated value only ever reached a hover `<title>` nobody finds.
    """

    def test_compact_axis_label_drops_the_year(self):
        body = function_body("compactAxisLabel", SCRIPT)
        self.assertIn('split("/")', body)
        self.assertIn("parts.length === 3", body)

    def test_thinning_formatter_shortens_surviving_labels(self):
        body = function_body("thinningFormatter", SCRIPT)
        self.assertIn("compactAxisLabel(value)", body)

    def test_neither_line_chart_lets_apex_trim_the_axis_text(self):
        # `trim: true` is what was chopping the already-short label down
        # further — removed from both chart functions, `hideOverlappingLabels`
        # stays as the real backstop against genuine overlap.
        for fn in ("renderAreaChart", "renderMixedChart"):
            body = function_body(fn, SCRIPT)
            self.assertNotIn("trim: true", body, f"{fn} still lets Apex trim its axis text")
            self.assertIn("hideOverlappingLabels: true", body)


class BoardCardDetailsLinkTests(SimpleTestCase):
    """Item 4 — the three-dot "view details" link on a board card
    (`boardCardHeader`) was a real `<a href>` that never navigated: jKanban's
    own vendor bundle attaches a click listener straight to every
    `.kanban-item` it builds and calls the event's `preventDefault()`
    unconditionally, which also cancels the anchor's own default action
    since a link's navigation resolves only after the click event finishes
    propagating. Confirmed live: dispatching a click on the link navigated
    to `/leads/<id>/` once the fix was in place.
    """

    def test_the_fix_runs_in_the_capture_phase(self):
        # Has to see the click before jKanban's own bubble-phase listener on
        # `.kanban-item` does, or the preventDefault already happened.
        body = function_body("letCardDetailsLinkThrough", SCRIPT)
        self.assertIn('.closest(".kanban-card-more")', body)
        self.assertIn("event.stopPropagation()", body)
        self.assertIn("}, true)", body)

    def test_both_boards_install_it(self):
        for fn in ("setupLeadBoard", "setupOrderBoard"):
            body = function_body(fn, SCRIPT)
            self.assertIn("letCardDetailsLinkThrough(container)", body, f"{fn} does not install the fix")


class PaymentWizardDocumentStepTests(SimpleTestCase):
    """Item 5 — the receipts/payments wizard's «اطلاعات سند» step shared the
    exact bug `.wizard-lines-step` was already written to fix: the theme
    lays every `[data-kt-stepper-element="content"]` out as `display:flex;
    flex-direction:row` by default, and this step has up to five top-level
    children once a fieldset is shown, so they fought each other for one
    shared row instead of stacking. Measured live with «چک» selected before
    the fix: the fields row came out 128px wide, the cheque fieldset 252px,
    the notes row 64px.
    """

    def test_the_step_carries_the_scoping_class(self):
        self.assertIn('class="wizard-document-step" data-kt-stepper-element="content"', markup(PAYMENTS_LIST))

    def test_the_step_is_a_column(self):
        body = rule(".wizard-document-step")
        self.assertIn("flex-direction: column", body)
        self.assertIn("align-items: stretch", body)

    def test_the_sections_get_more_air_than_a_lone_form_row_would(self):
        # The theme's own `.mt-2` utility is itself `!important`
        # (style.bundle.rtl.css), so beating it for just this step needs the
        # same — a single, targeted override, not a chain.
        body = rule(".wizard-document-step > .mt-2")
        self.assertIn("!important", body)


class PostalMiniStepperTests(SimpleTestCase):
    """Item 6 — «رهگیری پستی» (sales_documents/list.html) showed each
    document's postal status as plain text in a table cell; the full
    four-stop stepper only ever existed on one document's own detail page.
    Product owner, 2026-09-21: «وضعیت پستی باید ۴ تا ایکون پست سرهم به هم
    متصل باشد و در هر مرحله‌ای است باید این ایکون روشن باشد. کلا ۴ حالت باید
    وجود داشته باشد». The four states and their order were already decided
    (2026-09-20, `sales/postal.py`) and are read from
    `item.postal_stepper` — the exact field `SalesDocumentSerializer`
    already computed for the detail page — not redeclared here.
    """

    def test_the_row_reads_the_servers_own_stepper_not_a_redeclared_one(self):
        body = function_body("postalStatusCell", SCRIPT)
        self.assertIn("item.postal_stepper", body)
        self.assertIn("step.icon", body)
        self.assertIn("step.stage", body)

    def test_a_pre_vocabulary_free_text_status_falls_back_to_text(self):
        """`stepper_for` (sales/postal.py) returns `[]` for a status outside
        the four states, and four icons with none of them current would
        claim to know where such a parcel is when nobody does."""
        body = function_body("postalStatusCell", SCRIPT)
        self.assertIn("if (!steps || !steps.length)", body)
        self.assertIn("item.postal_status", body)

    def test_the_current_stage_is_named_for_a_screen_reader(self):
        body = function_body("postalStatusCell", SCRIPT)
        self.assertIn('setAttribute("aria-label"', body)
        self.assertIn("mark.title = step.label", body)

    def test_the_list_row_calls_it_instead_of_printing_raw_text(self):
        body = function_body("salesDocumentRow", SCRIPT)
        self.assertIn("postalStatusCell(row, item)", body)
        self.assertNotIn('appendCell(row, item.postal_status)', body)

    def test_four_icons_sit_flush_against_each_other(self):
        """"سرهم به هم متصل" — connected, not merely nearby: the rail is
        one continuous line and the marks carry no gap of their own.

        `rule()` matches by substring of the selector text, so a bare
        `.postal-mini-step` query also matches `.postal-mini-stepper` and
        `.postal-mini-step-current` — this pins the exact single-class rule
        by its own opening line instead."""
        self.assertIn("display: inline-flex", rule(".postal-mini-stepper"))
        mark = exact_rule(".postal-mini-step")
        self.assertNotIn("gap", mark)
        self.assertNotIn("margin", mark)

    def test_the_current_mark_is_visibly_lit(self):
        body = exact_rule(".postal-mini-step-current")
        self.assertIn("var(--bs-primary)", body)
        self.assertIn("box-shadow", body)
