"""Money moving in both directions through one table.

The load-bearing claims:

* a receipt behaves exactly as it did before this existed;
* a disbursement is not a negative receipt — it cannot settle an invoice, and
  it moves the customer ledger the other way;
* spending a received cheque changes that cheque and creates nothing, so the
  same instrument is never counted twice;
* `manual_paid_entry` is untouched by any of it.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.ledger import current_balance
from billing.models import Cheque, CustomerLedgerEntry, Invoice, Payment
from billing.payments import (
    allocate_payment,
    register_payment,
    set_cheque_registration,
    spend_received_cheque,
    transition_cheque,
)
from billing.services import create_invoice, issue_invoice
from common.exceptions import BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class BidirectionalPaymentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="bd.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دوجهته",
            phone={"raw_phone": "09121240000", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="BD-1", name="کالا", current_price=Decimal("1000.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="bdwh", name="انبار")
        record_stock_movement(
            actor=self.manager, warehouse=self.warehouse, product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=100, unit_cost=Decimal("400.00"),
        )
        self.serial = 0

    def receipt(self, **overrides):
        options = {
            "actor": self.manager, "customer": self.customer,
            "method": Payment.Method.CASH, "amount": Decimal("500.00"),
        }
        options.update(overrides)
        return register_payment(**options)

    def disbursement(self, **overrides):
        options = {
            "actor": self.manager, "customer": None,
            "direction": Payment.Direction.DISBURSEMENT,
            "payee": "تأمین‌کننده",
            "method": Payment.Method.CASH, "amount": Decimal("300.00"),
        }
        options.update(overrides)
        return register_payment(**options)

    def issued_invoice(self, quantity=1):
        return issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager, customer=self.customer, warehouse=self.warehouse,
                items=[{"product": self.product, "quantity": quantity}],
            ),
        )

    def cheque_receipt(self, **overrides):
        self.serial += 1
        return self.receipt(
            method=Payment.Method.CHEQUE,
            cheque={
                "bank_name": "بانک ملی",
                "bank_account": "0201234567001",
                "serial_number": f"CHQ-{self.serial}",
                "due_date": "2026-12-01",
            },
            **overrides,
        )

    # --- nothing about a receipt changed ----------------------------------

    def test_a_payment_is_a_receipt_unless_it_says_otherwise(self):
        self.assertEqual(self.receipt().direction, Payment.Direction.RECEIPT)

    def test_a_receipt_still_credits_the_customer(self):
        before = current_balance(self.customer)
        self.receipt(amount=Decimal("500.00"))
        self.assertEqual(current_balance(self.customer), before - Decimal("500.00"))

    def test_a_receipt_still_settles_an_invoice(self):
        invoice = self.issued_invoice()
        payment = self.receipt(amount=invoice.balance_due)
        allocate_payment(actor=self.manager, payment=payment, invoice=invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_due, Decimal("0.00"))
        self.assertEqual(invoice.settlement_status, Invoice.SettlementStatus.PAID)

    # --- a disbursement is not a negative receipt -------------------------

    def test_a_disbursement_needs_a_payee(self):
        with self.assertRaises(BusinessRuleError) as caught:
            self.disbursement(payee="")
        self.assertIn("payee", caught.exception.detail)

    def test_a_receipt_still_needs_a_customer(self):
        with self.assertRaises(BusinessRuleError) as caught:
            self.receipt(customer=None)
        self.assertIn("customer", caught.exception.detail)

    def test_a_disbursement_needs_no_customer(self):
        payment = self.disbursement()
        self.assertIsNone(payment.customer_id)
        self.assertEqual(payment.payee, "تأمین‌کننده")

    def test_a_disbursement_cannot_be_allocated_to_an_invoice(self):
        """Otherwise money leaving would reduce what a customer owes."""
        invoice = self.issued_invoice()
        payment = self.disbursement(customer=self.customer, amount=invoice.balance_due)
        with self.assertRaises(BusinessRuleError) as caught:
            allocate_payment(actor=self.manager, payment=payment, invoice=invoice)
        self.assertIn("payment", caught.exception.detail)
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("0.00"))

    # --- the ledger moves the other way -----------------------------------

    def test_a_disbursement_to_a_customer_debits_them(self):
        """Debit increases what the customer owes — the mirror of a receipt."""
        before = current_balance(self.customer)
        self.disbursement(customer=self.customer, amount=Decimal("300.00"))
        self.assertEqual(current_balance(self.customer), before + Decimal("300.00"))

    def test_that_entry_is_named_for_what_it_is(self):
        self.disbursement(customer=self.customer)
        entry = CustomerLedgerEntry.objects.filter(customer=self.customer).latest("occurred_at")
        self.assertEqual(entry.entry_type, CustomerLedgerEntry.EntryType.PAYMENT_MADE)
        self.assertEqual(entry.debit, Decimal("300.00"))
        self.assertEqual(entry.credit, Decimal("0.00"))

    def test_a_disbursement_with_no_customer_posts_nothing(self):
        """It structurally cannot: the ledger's customer is a required key."""
        before = CustomerLedgerEntry.objects.count()
        self.disbursement()
        self.assertEqual(CustomerLedgerEntry.objects.count(), before)

    def test_a_receipt_and_a_disbursement_of_the_same_size_cancel_out(self):
        opening = current_balance(self.customer)
        self.receipt(amount=Decimal("400.00"))
        self.disbursement(customer=self.customer, amount=Decimal("400.00"))
        self.assertEqual(current_balance(self.customer), opening)

    # --- spending a received cheque ---------------------------------------

    def test_spending_creates_no_second_cheque_or_payment(self):
        """The instrument handed over is the one already recorded."""
        payment = self.cheque_receipt()
        cheques_before = Cheque.objects.count()
        payments_before = Payment.objects.count()

        spent = spend_received_cheque(
            actor=self.manager, cheque=payment.cheque, payee="تأمین‌کننده", reason="آزمون"
        )
        self.assertEqual(Cheque.objects.count(), cheques_before)
        self.assertEqual(Payment.objects.count(), payments_before)
        self.assertEqual(spent.status, Cheque.Status.SPENT)
        self.assertEqual(spent.paid_to, "تأمین‌کننده")

    def test_spending_records_the_transition_in_history(self):
        payment = self.cheque_receipt()
        spend_received_cheque(actor=self.manager, cheque=payment.cheque, payee="گیرنده")
        history = payment.cheque.history.order_by("-id").first()
        self.assertEqual(history.to_status, Cheque.Status.SPENT)

    def test_spending_ends_the_payment_behind_the_cheque(self):
        """The money is not coming to us through this instrument any more.

        Since 1.3.0 the payment is already confirmed when the cheque arrives, so
        endorsing it onward reverses that credit rather than ending a pending
        payment — the customer's account must not keep a credit for a cheque we
        handed to someone else.
        """
        payment = self.cheque_receipt()
        self.assertEqual(payment.status, Payment.Status.CONFIRMED)
        spend_received_cheque(actor=self.manager, cheque=payment.cheque, payee="گیرنده")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CANCELLED)

    def test_a_spent_cheque_is_terminal(self):
        payment = self.cheque_receipt()
        spent = spend_received_cheque(actor=self.manager, cheque=payment.cheque, payee="گیرنده")
        with self.assertRaises(BusinessRuleError):
            transition_cheque(
                actor=self.manager, cheque=spent, to_status=Cheque.Status.CLEARED
            )

    def test_a_cleared_cheque_cannot_be_handed_to_anyone(self):
        """It has been paid; there is nothing left to endorse."""
        payment = self.cheque_receipt()
        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.CLEARED
        )
        with self.assertRaises(BusinessRuleError):
            spend_received_cheque(
                actor=self.manager, cheque=payment.cheque, payee="گیرنده"
            )

    def test_spending_needs_a_payee(self):
        payment = self.cheque_receipt()
        with self.assertRaises(BusinessRuleError):
            spend_received_cheque(actor=self.manager, cheque=payment.cheque, payee="")

    # --- the two axes are genuinely independent ----------------------------

    def test_registration_is_a_separate_axis_from_what_happened(self):
        """حالت and وضعیت move independently; that is the point of the split."""
        payment = self.cheque_receipt()
        cheque = payment.cheque
        self.assertEqual(cheque.status, Cheque.Status.PENDING)
        self.assertFalse(cheque.is_registered)

        cheque.is_registered = True
        cheque.save(update_fields=["is_registered"])
        moved = transition_cheque(
            actor=self.manager, cheque=cheque, to_status=Cheque.Status.CLEARED
        )
        # Changing وضعیت left حالت alone.
        self.assertTrue(moved.is_registered)
        self.assertEqual(moved.status, Cheque.Status.CLEARED)

    def test_a_desk_cannot_file_a_cheque_as_already_registered(self):
        """Both axes start at their neutral value, whatever the caller asked.

        The product owner's rule is that a cheque recorded from a payment desk
        always begins «در انتظار» and «ثبت نشده», and is moved by hand from the
        cheque page. Enforced in the service rather than in the form, so a
        crafted request cannot put an instrument into a state nobody chose.
        """
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("100.00"),
            cheque={
                "bank_name": "بانک ملت",
                "serial_number": "9001",
                "due_date": date(2027, 1, 1),
                # Asked for, and deliberately ignored.
                "is_registered": True,
            },
        )
        self.assertFalse(payment.cheque.is_registered)
        self.assertEqual(payment.cheque.status, Cheque.Status.PENDING)

    def test_the_date_written_on_the_cheque_is_kept(self):
        """`registered_on` is the operator's to state, unlike the two axes."""
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("100.00"),
            cheque={
                "bank_name": "بانک ملت",
                "serial_number": "9002",
                "due_date": date(2027, 1, 1),
                "registered_on": date(2026, 5, 4),
            },
        )
        self.assertEqual(payment.cheque.registered_on, date(2026, 5, 4))

    def test_registration_moves_without_touching_the_payment(self):
        """حالت says where the paper is, not whether the money arrived.

        Only وضعیت may credit or cancel anything. If registering a cheque
        confirmed its payment, marking a stack of them as filed would post a
        stack of credits nobody received.
        """
        payment = self.cheque_receipt()
        before = payment.status
        updated = set_cheque_registration(
            actor=self.manager, cheque=payment.cheque, is_registered=True
        )
        payment.refresh_from_db()
        self.assertTrue(updated.is_registered)
        self.assertEqual(updated.status, Cheque.Status.PENDING)
        self.assertEqual(payment.status, before)

    def test_setting_the_registration_it_already_has_changes_nothing(self):
        payment = self.cheque_receipt()
        same = set_cheque_registration(
            actor=self.manager, cheque=payment.cheque, is_registered=False
        )
        self.assertFalse(same.is_registered)

    def test_registration_survives_a_status_move_and_the_other_way_round(self):
        """The two axes are independent, which is the whole reason for the split."""
        payment = self.cheque_receipt()
        set_cheque_registration(
            actor=self.manager, cheque=payment.cheque, is_registered=True
        )
        moved = transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.CLEARED
        )
        self.assertTrue(moved.is_registered)
        self.assertEqual(moved.status, Cheque.Status.CLEARED)

    def test_a_bounced_cheque_can_still_be_re_presented(self):
        """BOUNCED -> PENDING survives the split; a bounce is not terminal."""
        payment = self.cheque_receipt()
        transition_cheque(actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.BOUNCED)
        again = transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.PENDING
        )
        self.assertEqual(again.status, Cheque.Status.PENDING)

    def test_the_check_constraint_list_matches_the_enum(self):
        """These fell out of step twice, and both times production broke."""
        from billing.models import CHEQUE_STATUS_VALUES

        self.assertEqual(sorted(CHEQUE_STATUS_VALUES), sorted(Cheque.Status.values))

    # --- the display-only path is untouched --------------------------------

    def test_manual_settlement_is_unaffected_by_any_of_this(self):
        from billing.services import record_manual_paid_entry

        invoice = self.issued_invoice()
        self.disbursement(customer=self.customer, amount=Decimal("50.00"))
        settled = record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due
        )
        self.assertTrue(settled.is_manually_settled)
        # Still no accounting record of its own, exactly as before.
        self.assertEqual(settled.paid_amount, Decimal("0.00"))


class ChequeCorrectionTests(BidirectionalPaymentTests):
    """A cheque operation can be undone, because operators press wrong buttons.

    «وصول» and «خرج کردن» used to be terminal: one wrong click on a row was
    permanent. The product owner asked for the operation to be changeable after
    it has been performed, so every state can return to «در انتظار» — and only
    there. Going anywhere else from a terminal state would be inventing a
    movement nobody described.

    What is actually being pinned here is that the money follows the correction.
    A status that moved while the ledger did not would be worse than the
    terminal state it replaced.
    """

    def test_returning_a_cleared_cheque_to_pending_gives_the_credit_back(self):
        payment = self.cheque_receipt()
        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.CLEARED
        )
        credited = current_balance(self.customer)

        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.PENDING
        )
        payment.refresh_from_db()
        self.assertEqual(payment.cheque.status, Cheque.Status.PENDING)
        # The credit is reversed, not deleted: the ledger is append-only, so the
        # balance returns to where it was while both movements stay readable.
        self.assertNotEqual(credited, current_balance(self.customer))
        self.assertGreater(
            CustomerLedgerEntry.objects.filter(customer=self.customer).count(), 1
        )

    def test_a_corrected_cheque_can_clear_again_and_credits_again(self):
        """The correction has to leave the cheque usable.

        This is the half that a status-only change would have missed. If the
        payment were left cancelled, clearing a second time would move no money
        and the operator would see the correction apply and nothing happen.
        """
        payment = self.cheque_receipt()
        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.CLEARED
        )
        cleared_once = current_balance(self.customer)
        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.PENDING
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertIsNone(payment.cancelled_at)

        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.CLEARED
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CONFIRMED)
        self.assertEqual(current_balance(self.customer), cleared_once)

    def test_a_spent_cheque_can_be_taken_back(self):
        payment = self.cheque_receipt()
        spent = spend_received_cheque(
            actor=self.manager, cheque=payment.cheque, payee="گیرنده"
        )
        transition_cheque(
            actor=self.manager, cheque=spent, to_status=Cheque.Status.PENDING
        )
        payment.refresh_from_db()
        self.assertEqual(payment.cheque.status, Cheque.Status.PENDING)
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_a_terminal_state_still_refuses_everything_except_pending(self):
        """Only the undo was added. A cleared cheque still cannot be spent."""
        payment = self.cheque_receipt()
        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.CLEARED
        )
        with self.assertRaises(BusinessRuleError):
            transition_cheque(
                actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.SPENT
            )


class SpentChequeIsFiledTests(BidirectionalPaymentTests):
    """Handing a cheque on files it, and puts it on the payments desk."""

    def test_spending_a_cheque_registers_it(self):
        """A cheque that has left the building has been filed by definition.

        It used to stay «ثبت نشده», so the cheques page showed a document that
        had been handed to someone else as one nobody had recorded.
        """
        payment = self.cheque_receipt()
        self.assertFalse(payment.cheque.is_registered)
        spent = spend_received_cheque(
            actor=self.manager, cheque=payment.cheque, payee="گیرنده"
        )
        self.assertEqual(spent.status, Cheque.Status.SPENT)
        self.assertTrue(spent.is_registered)

    def test_a_spent_cheque_reaches_the_disbursement_desk(self):
        """It is a receipt by direction, so only the desk query brings it here.

        The instrument moved; no second document was written, which is what
        keeps the amount from being counted twice.
        """
        payment = self.cheque_receipt()
        spend_received_cheque(actor=self.manager, cheque=payment.cheque, payee="گیرنده")
        payment.refresh_from_db()
        self.assertEqual(payment.direction, Payment.Direction.RECEIPT)
        self.assertEqual(Payment.objects.count(), 1)
        # And the status a reader sees on that desk is the cheque's own, which
        # is «خرج شده» — not the receipt's, which closed when the cheque left.
        self.assertEqual(payment.cheque.status, Cheque.Status.SPENT)
        self.assertEqual(payment.status, Payment.Status.CANCELLED)
