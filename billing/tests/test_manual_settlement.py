"""The manual "پرداخت شده" box on an invoice.

Client-1 wants an operator to be able to type the outstanding amount and have
the invoice read as settled. That is a display decision, and these tests pin
the two things that make it safe: it writes no accounting record of any kind,
and once it has fired it cannot be undone by editing the number again.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.ledger import current_balance
from billing.models import Invoice, Payment, PaymentAllocation
from billing.models import CustomerLedgerEntry
from billing.payments import allocate_payment, register_payment
from billing.services import create_invoice, issue_invoice, record_manual_paid_entry
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class ManualSettlementTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="ms.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری تسویه",
            phone={"raw_phone": "09121112222", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="MS-1", name="کالای تسویه", current_price=Decimal("1000.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="mswh", name="انبار تسویه")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=100,
            unit_cost=Decimal("400.00"),
        )

    def _issued_invoice(self, quantity=1):
        return issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": self.product, "quantity": quantity}],
            ),
        )

    # --- the transition ----------------------------------------------------

    def test_matching_the_outstanding_amount_settles_the_invoice(self):
        invoice = self._issued_invoice()
        self.assertEqual(invoice.settlement_status, Invoice.SettlementStatus.UNPAID)
        outstanding = invoice.canonical_balance_due

        settled = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=outstanding
        )
        self.assertTrue(settled.is_manually_settled)
        self.assertEqual(settled.balance_due, Decimal("0.00"))
        self.assertEqual(settled.settlement_status, Invoice.SettlementStatus.PAID)
        self.assertEqual(settled.manual_settled_by, self.manager)

    def test_a_value_that_is_not_the_outstanding_amount_changes_nothing(self):
        invoice = self._issued_invoice()
        outstanding = invoice.canonical_balance_due

        for amount in (outstanding - Decimal("1.00"), Decimal("0.00")):
            with self.subTest(amount=amount):
                result = record_manual_paid_entry(
                    actor=self.manager, invoice=invoice, amount=amount
                )
                self.assertFalse(result.is_manually_settled)
                self.assertEqual(result.balance_due, outstanding)
                self.assertEqual(result.settlement_status, Invoice.SettlementStatus.UNPAID)
                # The typed value is still remembered for display.
                self.assertEqual(result.manual_paid_entry, amount)

    def test_more_than_the_total_is_refused(self):
        invoice = self._issued_invoice()
        with self.assertRaises(BusinessRuleError):
            record_manual_paid_entry(
                actor=self.manager, invoice=invoice, amount=invoice.total_amount + Decimal("1.00")
            )

    # --- irreversibility ---------------------------------------------------

    def test_settlement_survives_a_later_smaller_entry(self):
        invoice = self._issued_invoice()
        outstanding = invoice.canonical_balance_due
        record_manual_paid_entry(actor=self.manager, invoice=invoice, amount=outstanding)

        # The operator edits the number downwards afterwards.
        after = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=Decimal("1.00")
        )
        self.assertTrue(after.is_manually_settled)
        self.assertEqual(after.balance_due, Decimal("0.00"))
        self.assertEqual(after.settlement_status, Invoice.SettlementStatus.PAID)
        self.assertEqual(after.manual_paid_entry, Decimal("1.00"))

    def test_settlement_survives_a_later_zero(self):
        invoice = self._issued_invoice()
        record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due
        )
        after = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=Decimal("0.00")
        )
        self.assertTrue(after.is_manually_settled)
        self.assertEqual(after.settlement_status, Invoice.SettlementStatus.PAID)

    def test_the_settlement_stamp_is_never_rewritten(self):
        invoice = self._issued_invoice()
        first = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due
        )
        stamp = first.manual_settled_at
        again = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=Decimal("5.00")
        )
        self.assertEqual(again.manual_settled_at, stamp)

    # --- no accounting side effects ---------------------------------------

    def test_nothing_is_posted_to_payments_allocations_or_the_ledger(self):
        invoice = self._issued_invoice()
        payments_before = Payment.objects.count()
        allocations_before = PaymentAllocation.objects.count()
        ledger_before = CustomerLedgerEntry.objects.count()
        balance_before = current_balance(self.customer)

        record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due
        )

        self.assertEqual(Payment.objects.count(), payments_before)
        self.assertEqual(PaymentAllocation.objects.count(), allocations_before)
        self.assertEqual(CustomerLedgerEntry.objects.count(), ledger_before)
        # The customer still owes what the records say they owe.
        self.assertEqual(current_balance(self.customer), balance_before)

    def test_the_canonical_paid_amount_is_untouched(self):
        invoice = self._issued_invoice()
        record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("0.00"))
        # Receivables reporting reads this, and it still tells the truth.
        self.assertEqual(invoice.canonical_balance_due, invoice.total_amount)

    def test_a_real_payment_still_moves_the_canonical_figures(self):
        """The override does not disable ordinary payment handling."""
        invoice = self._issued_invoice()
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("300.00"),
        )
        allocate_payment(
            actor=self.manager, payment=payment, invoice=invoice, amount=Decimal("300.00")
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("300.00"))
        self.assertEqual(
            invoice.canonical_balance_due, invoice.total_amount - Decimal("300.00")
        )

    def test_the_entry_must_match_what_is_outstanding_after_real_payments(self):
        invoice = self._issued_invoice()
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("300.00"),
        )
        allocate_payment(
            actor=self.manager, payment=payment, invoice=invoice, amount=Decimal("300.00")
        )
        invoice.refresh_from_db()
        # The full total no longer settles it; only the remainder does.
        not_settled = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.total_amount
        )
        self.assertFalse(not_settled.is_manually_settled)

        settled = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due
        )
        self.assertTrue(settled.is_manually_settled)

    # --- scope -------------------------------------------------------------

    def test_a_marketer_cannot_settle_an_invoice_outside_their_scope(self):
        invoice = self._issued_invoice()
        agent = User.objects.create_user(
            username="ms.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        with self.assertRaises(BusinessPermissionDenied):
            record_manual_paid_entry(
                actor=agent, invoice=invoice, amount=invoice.canonical_balance_due
            )
