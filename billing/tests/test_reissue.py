"""بند ۸ — correcting an issued invoice by cancelling and raising a new one.

The product owner was asked how an issued official invoice is corrected —
edited, replaced by a corrective invoice, or offset by a credit note — and
answered: **cancel it and issue a new one, with the reason in the notes**.
Cancellation is the panel administrator's, at any time, with no deadline.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.models import Invoice
from billing.services import (
    cancel_invoice,
    create_invoice,
    issue_invoice,
    reissue_invoice,
)
from common.exceptions import BusinessConflictError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class ReissueTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="reissue.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(
            actor=self.manager, sku="RI-1", name="کالا", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="riwh", name="انبار")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=500,
            unit_cost=Decimal("40.00"),
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری ابطال",
            phone={"raw_phone": "09121240000", "is_primary": True},
        )

    def issued(self, *, quantity=2, notes=""):
        invoice = create_invoice(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": quantity}],
            notes=notes,
        )
        return issue_invoice(actor=self.manager, invoice=invoice)

    # --- ۸.۲: the reason lands on the document ----------------------------

    def test_cancelling_writes_the_reason_into_the_notes(self):
        invoice = self.issued()
        cancel_invoice(actor=self.manager, invoice=invoice, reason="اشتباه در مقدار")
        invoice.refresh_from_db()
        self.assertIn("اشتباه در مقدار", invoice.notes)
        self.assertIn("[ابطال]", invoice.notes)

    def test_the_reason_is_appended_and_does_not_replace_what_was_there(self):
        invoice = self.issued(notes="یادداشت اولیه")
        cancel_invoice(actor=self.manager, invoice=invoice, reason="دلیل ابطال")
        invoice.refresh_from_db()
        self.assertIn("یادداشت اولیه", invoice.notes)
        self.assertIn("دلیل ابطال", invoice.notes)

    def test_cancelling_without_a_reason_leaves_the_notes_alone(self):
        invoice = self.issued(notes="یادداشت اولیه")
        cancel_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.notes, "یادداشت اولیه")

    # --- ۸.۲: cancel and raise a replacement ------------------------------

    def test_reissuing_cancels_the_old_and_returns_a_new_draft(self):
        original = self.issued()
        replacement = reissue_invoice(
            actor=self.manager, invoice=original, reason="اصلاح مشخصات خریدار"
        )
        original.refresh_from_db()
        self.assertEqual(original.status, Invoice.Status.CANCELLED)
        self.assertIn("اصلاح مشخصات خریدار", original.notes)
        # A draft, so the operator can correct what caused the reissue before it
        # becomes a document — and so it takes its official number at issue.
        self.assertEqual(replacement.status, Invoice.Status.DRAFT)
        self.assertNotEqual(replacement.number, original.number)

    def test_the_replacement_carries_the_same_lines_and_totals(self):
        original = self.issued(quantity=3)
        replacement = reissue_invoice(actor=self.manager, invoice=original, reason="اصلاح")
        self.assertEqual(replacement.items.count(), original.items.count())
        self.assertEqual(replacement.total_amount, original.total_amount)
        self.assertEqual(
            list(replacement.items.values_list("quantity", flat=True)),
            list(original.items.values_list("quantity", flat=True)),
        )

    def test_the_replacement_points_back_at_what_it_replaces(self):
        """The only link that survives being printed."""
        original = self.issued()
        replacement = reissue_invoice(actor=self.manager, invoice=original, reason="اصلاح")
        self.assertIn(original.number, replacement.notes)

    def test_the_replacement_starts_with_no_money_on_it(self):
        original = self.issued()
        replacement = reissue_invoice(actor=self.manager, invoice=original, reason="اصلاح")
        self.assertEqual(replacement.paid_amount, Decimal("0.00"))
        self.assertEqual(replacement.official_number, "")

    def test_the_replacement_keeps_the_type_of_what_it_replaces(self):
        original = self.issued()
        original.invoice_type = Invoice.InvoiceType.UNOFFICIAL
        original.save(update_fields=["invoice_type"])
        replacement = reissue_invoice(actor=self.manager, invoice=original, reason="اصلاح")
        self.assertEqual(replacement.invoice_type, original.invoice_type)

    # --- what reissue refuses ---------------------------------------------

    def test_only_an_issued_invoice_can_be_reissued(self):
        draft = create_invoice(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        with self.assertRaises(BusinessConflictError):
            reissue_invoice(actor=self.manager, invoice=draft, reason="اصلاح")

    def test_an_invoice_with_money_on_it_is_refused_until_it_is_released(self):
        """Reissue relaxes nothing that cancelling already refused."""
        from billing.models import Payment
        from billing.payments import allocate_payment, register_payment

        original = self.issued()
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("50.00"),
        )
        allocate_payment(actor=self.manager, payment=payment, invoice=original)
        with self.assertRaises(BusinessConflictError):
            reissue_invoice(actor=self.manager, invoice=original, reason="اصلاح")
        original.refresh_from_db()
        self.assertEqual(original.status, Invoice.Status.ISSUED)

    def test_a_failed_reissue_leaves_nothing_behind(self):
        """All of it or none of it — the cancel and the replacement share one transaction."""
        before = Invoice.objects.count()
        draft = create_invoice(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        with self.assertRaises(BusinessConflictError):
            reissue_invoice(actor=self.manager, invoice=draft, reason="اصلاح")
        self.assertEqual(Invoice.objects.count(), before + 1)
