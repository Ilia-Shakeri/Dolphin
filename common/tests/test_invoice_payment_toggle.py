"""The invoice wizard's payment step: one centred, large toggle (2.40.5).

The step's own title says «نوع پرداخت», so the words above the toggle went;
the name stays for assistive technology and in the review step. «اقساط»
reveals the instalment fields directly under it, «نقدی» folds them away and
switches them off, and the arrow keys move the way the options read.
"""

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "common" / "templates" / "common" / "invoices" / "list.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "common" / "static" / "common" / "js" / "features" / "billing" / "invoices.js").read_text(encoding="utf-8")
SEGMENTED = (ROOT / "common" / "static" / "common" / "js" / "ui" / "segmented.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")


def _payment_step():
    start = TEMPLATE.index('id="create-invoice-payment-type-label"')
    return TEMPLATE[start - 400:TEMPLATE.index('id="create-invoice-installment-reveal"', start)]


class ToggleMarkupTests(SimpleTestCase):
    def test_no_visible_words_above_the_toggle_but_an_accessible_name(self):
        step = _payment_step()
        self.assertIn('<span class="visually-hidden" id="create-invoice-payment-type-label">نوع پرداخت</span>', step)
        self.assertIn('role="radiogroup" aria-labelledby="create-invoice-payment-type-label"', step)

    def test_the_toggle_is_centred_and_large(self):
        step = _payment_step()
        self.assertIn('class="col-12 d-flex flex-column align-items-center"', step)
        self.assertIn("dolphin-segmented dolphin-segmented-lg", step)
        rule = CSS.split(".dolphin-segmented-lg .dolphin-segmented-option {")[1].split("}")[0]
        self.assertIn("min-height: 48px", rule)
        self.assertIn("font-size: 1rem", rule)

    def test_the_review_step_still_names_the_choice(self):
        self.assertIn('["نوع پرداخت", selectedOptionText(paymentTypeSelect)]', SCRIPT)

    def test_the_field_name_and_payload_branching_are_unchanged(self):
        self.assertIn('name="payment_type" value="cash"', TEMPLATE)
        self.assertIn('if (data.get("payment_type") === "installment") {', SCRIPT)


class RevealTests(SimpleTestCase):
    def test_instalments_reveal_under_the_toggle_and_cash_switches_them_off(self):
        self.assertLess(TEMPLATE.index('data-segmented-for="create-invoice-payment-type"'),
                        TEMPLATE.index('id="create-invoice-installment-reveal" inert'))
        self.assertIn('installmentReveal?.classList.toggle("is-open", installment);', SCRIPT)
        self.assertIn('installmentReveal?.toggleAttribute("inert", !installment);', SCRIPT)
        self.assertIn("field.disabled = !installment;", SCRIPT)

    def test_the_instalment_fields_are_two_columns(self):
        fields = TEMPLATE.split('id="create-invoice-installment-fields"')[1].split("</div>\n                </div></div>")[0]
        self.assertEqual(fields.count('<div class="col-md-6">'), 4)


class KeyboardTests(SimpleTestCase):
    def test_arrow_keys_follow_the_reading_direction(self):
        self.assertIn('const rtl = getComputedStyle(group).direction === "rtl";', SEGMENTED)
        self.assertIn('event.key === (rtl ? "ArrowLeft" : "ArrowRight")', SEGMENTED)
