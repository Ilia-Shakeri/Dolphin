"""The create wizards: how the review step is laid out, and what it says when
the server rejects the form.

Product-owner request, 2026-09-19, items 1 and 9:

* «مرحله بررسی و بازبینی خیلی زشت و درهم هستش و باید زیبا و مرتب زیر هم نوشته
  شده باشه» — the last step of every wizard;
* «توی اروری که در صفحه بازبینی به یوزر میده باید توضیح کوتاه بده کجاش مشکل
  داره» — what happens after a rejected submit.

Two defects were behind those sentences, and both are worth pinning because
both are invisible from the code that renders the step:

1. **The step was laid out sideways.** The theme's own stylesheet sets
   `[data-kt-stepper-element="content"].current { display: flex }` with
   flexbox's default `row` direction. Every other step in every wizard has
   exactly one child (its `.row` of fields) so nobody noticed; the review
   steps have two or three (`h3`, the field list, sometimes a `p`), and those
   were being drawn as columns beside one another. Measured in a browser
   before the fix: the `h3` was 62px wide and 561px tall, sitting to the side
   of the list. The fix is the vendor's own convention — one `.w-100` wrapper
   as the single flex child — so this file checks every wizard has it.
2. **A rejected submit explained itself where nobody could see it.** Field
   errors are written into `[data-error-for]` paragraphs that live on steps 1
   and 2, behind the review step the reader submitted from. All that showed
   was the generic banner.

Everything here reads the real source files, so none of it needs a browser or
a database — and none of it can pass while the shipped file says otherwise.
"""

import pathlib
import re

from django.test import SimpleTestCase


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "common" / "templates" / "common"

#: Every wizard in the product, found rather than listed: a wizard added later
#: is covered by these tests the day it is added, and one deleted stops being
#: asserted about instead of failing a hard-coded name.
WIZARD_PAGES = sorted(
    path for path in TEMPLATES.rglob("*.html")
    if 'data-kt-stepper-element="nav"' in path.read_text(encoding="utf-8")
)


def _function_body(name):
    """One function's text, from its declaration to the next top-level one."""
    start = SCRIPT.index(f"function {name}(")
    following = SCRIPT.find("\n    function ", start + 1)
    return SCRIPT[start:following if following != -1 else len(SCRIPT)]


def _dialogs(text):
    return re.findall(r"<dialog\b.*?</dialog>", text, re.S)


def _review_steps():
    """`(page, dialog)` for every wizard dialog that ends on a review step."""
    for path in WIZARD_PAGES:
        for dialog in _dialogs(path.read_text(encoding="utf-8")):
            if "wizard-review mb-4" in dialog:
                yield path.relative_to(TEMPLATES).as_posix(), dialog


class WizardInventoryTests(SimpleTestCase):
    def test_the_product_still_has_wizards_to_check(self):
        """Guards every other test in this file: a selector that quietly
        matched nothing would make all of them pass while proving nothing."""
        self.assertGreaterEqual(len(list(_review_steps())), 15)


class ReviewStepLayoutTests(SimpleTestCase):
    def test_every_review_step_sits_in_one_full_width_wrapper(self):
        """The fix for the sideways layout, checked per wizard.

        The theme makes the *current* step a flex row; one child means one
        column, which is the only arrangement that reads top to bottom.
        """
        for page, dialog in _review_steps():
            with self.subTest(page=page):
                last = dialog.rfind('data-kt-stepper-element="content"')
                tail = dialog[last:]
                # The wrapper opens before the heading and the field list, and
                # nothing else sits outside it inside that step.
                self.assertRegex(
                    tail,
                    r'data-kt-stepper-element="content">\s*<div class="w-100">\s*<h3',
                )

    def test_no_review_container_is_still_a_two_column_grid(self):
        """The old shape was `row g-3` of `col-md-6` cells — a label stacked
        over its value, four edges to read six fields, and one long Persian
        value knocking its neighbour's baseline out of line."""
        for page, dialog in _review_steps():
            with self.subTest(page=page):
                self.assertNotRegex(dialog, r'class="row g-3 mb-4" id="[a-z-]*review"')
                self.assertRegex(dialog, r'class="wizard-review mb-4" id="[a-z-]*review"')

    def test_the_renderer_builds_one_labelled_line_per_field(self):
        body = _function_body("renderWizardReview")
        self.assertIn('line.className = "wizard-review-row"', body)
        self.assertIn('labelEl.className = "wizard-review-label"', body)
        self.assertIn('valueEl.className = "wizard-review-value"', body)
        # Nothing may go back to the grid it came from.
        self.assertNotIn("col-md-6", body)

    def test_an_empty_value_reads_as_an_em_dash(self):
        """Twelve review rows read a field's `.value` with no fallback of
        their own (an audit of every wizard found them). Handling it in the
        one renderer covers those and anything written later."""
        body = _function_body("renderWizardReview")
        self.assertIn('String(value ?? "").trim() || "—"', body)

    def test_a_review_shows_every_field_its_own_form_collects(self):
        """A review step's whole job is to reflect what is about to be sent.
        The order wizard collected «توضیحات» and never showed it; this walks
        every wizard so the next omission is caught the same way.

        Matching is by element id or by `form.<name>` — the two ways these
        renderers read a field — and skips the hidden plumbing a form carries
        but a person never typed into: the CSRF token, and `type="hidden"`
        inputs such as the payments form's own `direction`, which the page
        sets from the desk it was opened from (the review reflects it by
        wording its rows «گیرنده»/«تاریخ پرداخت» rather than as a row of its
        own).
        """
        skip = {"csrfmiddlewaretoken"}
        for page, dialog in _review_steps():
            dialog = re.sub(r'<input[^>]*type="hidden"[^>]*>', "", dialog)
            review = re.search(r'id="([a-z-]*review)"', dialog).group(1)
            index = SCRIPT.find(f'"{review}"')
            self.assertNotEqual(index, -1, f"{page}: no renderer for {review}")
            # The whole enclosing setup function, so locals such as
            # `customerSelect` and incremental `rows.push(...)` are included.
            start = SCRIPT.rfind("\n    async function ", 0, index)
            start = max(start, SCRIPT.rfind("\n    function ", 0, index))
            following = SCRIPT.find("\n    function ", index)
            body = SCRIPT[start:following if following != -1 else len(SCRIPT)]
            for element_id, name in re.findall(
                r'<(?:input|select|textarea)[^>]*id="([a-z0-9-]+)"[^>]*name="([a-z0-9_]+)"', dialog
            ):
                if name in skip:
                    continue
                with self.subTest(page=page, field=name):
                    self.assertTrue(
                        element_id in body or f".{name}.value" in body or f'"{name}"' in body,
                        f"{page}: «{name}» is collected but never shown on the review step",
                    )

    def test_the_stylesheet_lays_those_lines_out_as_a_list(self):
        rule = CSS.split(".wizard-review-row {")[1].split("}")[0]
        self.assertIn("justify-content: space-between", rule)
        self.assertIn("border-block-end", rule)
        # A separator divides two things; under the last row there is nothing
        # to divide it from.
        self.assertIn(".wizard-review-row:last-child {", CSS)

    def test_a_long_value_wraps_instead_of_widening_the_row(self):
        """A نشانی or a یادداشت is the realistic long value here, and it must
        not push the label off the card."""
        rule = CSS.split(".wizard-review-value {")[1].split("}")[0]
        self.assertIn("min-width: 0", rule)
        self.assertIn("overflow-wrap: anywhere", rule)


class ReviewStepErrorSummaryTests(SimpleTestCase):
    def test_the_summary_is_built_once_and_shared_by_every_wizard(self):
        """In JavaScript rather than in fifteen templates: the markup would be
        identical in all of them, and a wizard added later would silently not
        have it."""
        self.assertIn("function createWizardErrorSummary(", SCRIPT)
        body = _function_body("createWizardErrorSummary")
        self.assertIn('panel.setAttribute("role", "alert")', body)
        # Under the step's own heading, not in front of it.
        self.assertIn("stepHeading.after(panel)", body)

    def test_a_rejected_submit_reaches_the_summary(self):
        show = _function_body("showError")
        self.assertIn("reportWizardErrors(form)", show)

    def test_clearing_a_form_clears_the_summary_with_it(self):
        """It is built from the `[data-error-for]` slots, so it is stale the
        moment they are emptied."""
        clear = _function_body("clearMessages")
        self.assertIn("summary.clear()", clear)

    def test_each_problem_names_its_field_its_reason_and_its_step(self):
        body = _function_body("reportWizardErrors")
        self.assertIn("label: fieldLabelFor(form, name)", body)
        self.assertIn("message,", body)
        self.assertIn("step: wizard.stepOf(", body)

    def test_a_field_is_named_by_its_own_label_not_by_its_api_key(self):
        """`campaign_or_batch` is an internal identifier nobody on this side of
        the screen has ever seen."""
        body = _function_body("fieldLabelFor")
        self.assertIn("label[for=", body)
        self.assertIn("non_field_errors", body)

    def test_the_summary_offers_the_way_back_to_the_failing_step(self):
        body = _function_body("createWizardErrorSummary")
        self.assertIn("goToStep(step)", body)
        self.assertIn("مرحلهٔ", body)

    def test_the_summary_panel_is_styled_as_an_error_not_as_a_card(self):
        rule = CSS.split(".wizard-review-errors {")[1].split("}")[0]
        self.assertIn("var(--bs-danger-light)", rule)
        self.assertIn("var(--bs-danger)", rule)


class StepGateTests(SimpleTestCase):
    def test_a_blocked_next_leaves_its_reason_on_screen(self):
        """The browser's bubble fades; the sentence in the field's own error
        slot does not. Both, because the bubble lands where the cursor is and
        the slot is what a reader who looked away comes back to."""
        body = _function_body("setupWizard")
        self.assertIn("writeNativeValidationMessage(invalid)", body)
        self.assertIn("invalid.reportValidity()", body)

    def test_the_sentence_is_the_browsers_own_not_one_rewritten_here(self):
        body = _function_body("writeNativeValidationMessage")
        self.assertIn("field.validationMessage", body)

    def test_every_wizard_still_has_one_nav_per_step(self):
        """A nav without its content (or the reverse) makes `stepOf` name the
        wrong step in the summary above."""
        for page, dialog in _review_steps():
            with self.subTest(page=page):
                self.assertEqual(
                    dialog.count('data-kt-stepper-element="nav"'),
                    dialog.count('data-kt-stepper-element="content"'),
                )

    def test_the_review_step_is_always_the_last_one(self):
        """`createWizardErrorSummary` prepends into the last step. If a wizard
        ever ended somewhere else, the summary would appear on a step the
        reader never submits from."""
        for page, dialog in _review_steps():
            with self.subTest(page=page):
                last = dialog.rfind('data-kt-stepper-element="content"')
                self.assertRegex(dialog[last:], r'id="[a-z-]*review"')
