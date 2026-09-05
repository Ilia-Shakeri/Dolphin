"""The invoice/order creation dialogs as multi-step Metronic wizards.

Product-owner request (2026-09-05): the fields crammed into one dialog should
become "ویزارد چندمرحله‌ای" — a multi-step wizard, matching the purchased
theme's own pattern rather than a page-long single form.

Both dialogs already existed as native `<dialog>` create forms wired through
the shared `setupDocumentList`. What changed here is purely presentational
plus one real capability fix, and this is what is worth pinning:

* the dialog content is now split across the theme's own real `KTStepper`
  steps (`utilities/modals/wizards/create-account.html` is the vendor
  reference), not a hand-rolled tab system;
* "next" is gated on the current step's own required fields — no
  FormValidation.js, SweetAlert2, jQuery or Bootstrap modal is pulled in for
  it, since none of those are used anywhere else in this codebase;
* the actual submit is still the form's own native `submit` event, so
  `setupDocumentList`'s existing request/redirect logic needed no change;
* the order dialog's item editor is no longer capped at one product — it now
  reuses the exact row-adding component the invoice dialog already had,
  because the `items` array the order API accepts already supported more
  than one line and nothing server-side changes here;
* reopening a cancelled wizard starts clean: the form resets, the item rows
  collapse back to one, and the stepper returns to its first step.
"""

import pathlib

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User

PASSWORD = "Strong-pass-274!"

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
).read_text(encoding="utf-8")


def _function_body(name, end_marker):
    start = SCRIPT.index(f"function {name}(")
    end = SCRIPT.index(end_marker, start)
    return SCRIPT[start:end]


class WizardRenderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="wizard.viewer", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_invoice_dialog_carries_a_real_stepper(self):
        page = self.client.get("/invoices/").content.decode("utf-8")
        self.assertIn('id="create-invoice-stepper"', page)
        self.assertIn('class="stepper stepper-links d-flex flex-column"', page)
        self.assertEqual(page.count('data-kt-stepper-element="nav"'), 3)
        self.assertEqual(page.count('data-kt-stepper-element="content"'), 3)

    def test_the_order_dialog_carries_a_real_stepper_too(self):
        page = self.client.get("/orders/").content.decode("utf-8")
        self.assertIn('id="create-order-stepper"', page)
        self.assertEqual(page.count('data-kt-stepper-element="nav"'), 3)
        self.assertEqual(page.count('data-kt-stepper-element="content"'), 3)

    def test_both_wizards_end_on_a_review_step_before_the_real_submit(self):
        for path, review_id in (("/invoices/", "create-invoice-review"), ("/orders/", "create-order-review")):
            with self.subTest(path=path):
                page = self.client.get(path).content.decode("utf-8")
                self.assertIn(f'id="{review_id}"', page)
                # The real submit is still a native form submit — nothing new
                # for `setupDocumentList`'s own handler to learn.
                self.assertIn('type="submit" data-kt-stepper-action="submit"', page)

    def test_previous_and_next_are_plain_buttons_not_submits(self):
        """Only the last step's button may submit the form — an earlier
        step's "next" must never trigger a premature POST."""
        for path in ("/invoices/", "/orders/"):
            with self.subTest(path=path):
                page = self.client.get(path).content.decode("utf-8")
                self.assertIn('type="button" data-kt-stepper-action="previous"', page)
                self.assertIn('type="button" data-kt-stepper-action="next"', page)

    def test_the_order_dialog_no_longer_has_the_single_item_fields(self):
        """Superseded by the shared multi-row item editor below."""
        page = self.client.get("/orders/").content.decode("utf-8")
        self.assertNotIn('id="create-order-product"', page)
        self.assertNotIn('id="create-order-quantity"', page)
        self.assertIn('id="create-order-lines"', page)
        self.assertIn('id="create-order-add-line"', page)

    def test_the_order_customer_is_searchable_like_the_invoices_one(self):
        page = self.client.get("/orders/").content.decode("utf-8")
        self.assertIn('id="create-order-customer-search"', page)
        self.assertIn('data-searchable-source', page)


class ScriptBehaviourTests(SimpleTestCase):
    """What the wizard's own script does, pinned by source pattern — the
    same style already used for the chat drawer and the filter popovers."""

    def test_setup_wizard_is_the_real_kt_stepper_not_a_reinvention(self):
        body = _function_body("setupWizard", "\n    /**\n     * One dynamic")
        self.assertIn("new KTStepper(root)", body)
        # No validation/dialog library this codebase does not otherwise use.
        self.assertNotIn("FormValidation", body)
        self.assertNotIn("Swal", body)
        self.assertNotIn("bootstrap.Modal", body)

    def test_next_is_gated_on_the_current_steps_own_required_fields(self):
        body = _function_body("setupWizard", "\n    /**\n     * One dynamic")
        self.assertIn('querySelector(":invalid")', body)
        self.assertIn("invalid.reportValidity()", body)
        self.assertIn("stepper.goNext()", body)

    def test_reaching_the_last_step_is_reported_back_to_the_caller(self):
        body = _function_body("setupWizard", "\n    /**\n     * One dynamic")
        self.assertIn("onReachLastStep?.()", body)

    def test_the_line_item_editor_is_one_shared_component(self):
        """Not a copy pasted between the invoice and order wizards."""
        self.assertEqual(SCRIPT.count("function createLineItemRows("), 1)
        body = _function_body("createLineItemRows", "\n    /** A field's chosen option text")
        self.assertIn("function addLine()", body)
        self.assertIn("function reset()", body)
        self.assertIn("function collect()", body)

    def test_the_order_wizard_now_sends_every_row_not_just_the_first(self):
        """The single-line `documentFirstLine` helper is gone; the order's
        `items` payload is the same `lines.collect()` the invoice wizard
        already used, and the order API already accepted more than one."""
        self.assertNotIn("documentFirstLine", SCRIPT)
        orders_body_start = SCRIPT.index("async function setupOrders()")
        orders_body = SCRIPT[orders_body_start:SCRIPT.index("async function setupInvoices()")]
        self.assertIn("items: lines.collect()", orders_body)
        self.assertIn("createLineItemRows(lineHost, products)", orders_body)

    def test_reopening_a_wizard_resets_the_form_the_lines_and_the_step(self):
        for fn_name, end_marker in (
            ("setupOrders", "async function setupInvoices()"),
            ("setupInvoices", "\n    // --- "),
        ):
            with self.subTest(fn=fn_name):
                body = _function_body(fn_name, end_marker)
                self.assertIn("onOpen: () => {", body)
                self.assertIn(".reset();", body)
                self.assertIn("lines.reset();", body)
                self.assertIn("wizard?.goFirst();", body)

    def test_open_create_dialog_calls_onopen_before_showing_it(self):
        body = _function_body("setupDocumentList", "\n    /**\n     * Wire the theme's own real")
        self.assertIn("onOpen?.();", body)
        self.assertIn("dialog.showModal();", body)
        # `onOpen` must run first — reset before reveal, not after.
        self.assertLess(body.index("onOpen?.();"), body.index("dialog.showModal();"))
