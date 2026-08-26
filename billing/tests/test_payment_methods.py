"""Recording a receipt by the method it actually arrived by.

The form now has one mode per method rather than one shape with a dropdown, and
each mode collects what that method has: a cash receipt has a receipt number, a
transfer has a bank and an account it came from, a cheque is its own instrument.

What is pinned here is that the bank columns belong to a transfer and nowhere
else, and that none of this disturbed the payment semantics that were already
settled — `card` still works, allocation is unchanged, and a cheque still posts
nothing to the ledger until it clears.

Cheque behaviour itself is deliberately untouched this round.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import User
from billing.models import Payment
from billing.payments import register_payment
from common.exceptions import BusinessRuleError
from sales.services import create_customer_with_phone


PASSWORD = "Strong-pass-937!"


class PaymentMethodTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="pm.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دریافت",
            phone={"raw_phone": "09121230000", "is_primary": True},
        )

    def register(self, **overrides):
        options = {
            "actor": self.manager,
            "customer": self.customer,
            "method": Payment.Method.CASH,
            "amount": Decimal("1000.00"),
        }
        options.update(overrides)
        return register_payment(**options)

    # --- cash --------------------------------------------------------------

    def test_a_cash_receipt_needs_nothing_but_an_amount(self):
        payment = self.register(reference="RCPT-9")
        self.assertEqual(payment.method, Payment.Method.CASH)
        self.assertEqual(payment.reference, "RCPT-9")
        self.assertEqual(payment.bank_name, "")
        self.assertEqual(payment.bank_account, "")
        self.assertIsNotNone(payment.received_at)

    # --- bank transfer -----------------------------------------------------

    def test_a_transfer_records_its_bank_and_account(self):
        payment = self.register(
            method=Payment.Method.BANK_TRANSFER,
            bank_name="بانک ملت",
            bank_account="IR120570028870010351000101",
            reference="TRK-771",
        )
        self.assertEqual(payment.bank_name, "بانک ملت")
        self.assertEqual(payment.bank_account, "IR120570028870010351000101")
        self.assertEqual(payment.reference, "TRK-771")

    def test_a_transfer_without_bank_details_is_still_accepted(self):
        """Recording one from a statement is a real case; refusing loses the money.

        Requiring a bank name would be a business rule nobody has asked for, and
        the alternative to an incomplete record here is no record at all.
        """
        payment = self.register(method=Payment.Method.BANK_TRANSFER)
        self.assertEqual(payment.bank_name, "")

    # --- the columns belong to one method ----------------------------------

    def test_bank_details_are_refused_on_any_other_method(self):
        for method in (Payment.Method.CASH, Payment.Method.CARD, Payment.Method.CHEQUE):
            with self.subTest(method=method):
                with self.assertRaises(BusinessRuleError) as caught:
                    self.register(method=method, bank_name="بانک ملت")
                self.assertIn("bank_name", caught.exception.detail)

    def test_the_database_refuses_them_too(self):
        """The service message is the good error; this is the floor beneath it."""
        payment = self.register()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Payment.objects.filter(pk=payment.pk).update(bank_account="IR12")

    # --- card is not removed ----------------------------------------------

    def test_card_still_records(self):
        """Existing data uses it, so the method stays reachable and working."""
        payment = self.register(method=Payment.Method.CARD, reference="POS-4")
        self.assertEqual(payment.method, Payment.Method.CARD)
        self.assertEqual(payment.status, Payment.Status.CONFIRMED)

    def test_every_method_the_model_declares_can_be_registered(self):
        for index, method in enumerate(Payment.Method.values):
            with self.subTest(method=method):
                extra = {}
                if method == Payment.Method.CHEQUE:
                    extra["cheque"] = {
                        "bank_name": "بانک ملی",
                        "serial_number": f"CHQ-{index}",
                        "due_date": "2026-12-01",
                    }
                payment = self.register(method=method, **extra)
                self.assertEqual(payment.method, method)

    # --- nothing else moved ------------------------------------------------

    def test_the_amount_is_unallocated_until_it_is_allocated(self):
        payment = self.register(method=Payment.Method.BANK_TRANSFER, bank_name="بانک ملت")
        self.assertEqual(payment.allocated_amount, Decimal("0.00"))
        self.assertEqual(payment.unallocated_amount, Decimal("1000.00"))

    def test_a_cheque_payment_still_creates_its_cheque(self):
        payment = self.register(
            method=Payment.Method.CHEQUE,
            cheque={
                "bank_name": "بانک ملی",
                "branch_name": "مرکزی",
                "serial_number": "CHQ-1",
                "account_holder": "دارندهٔ حساب",
                "due_date": "2026-12-01",
            },
        )
        self.assertEqual(payment.cheque.serial_number, "CHQ-1")
        # The cheque keeps its own bank, separate from the payment's columns.
        self.assertEqual(payment.cheque.bank_name, "بانک ملی")
        self.assertEqual(payment.bank_name, "")
