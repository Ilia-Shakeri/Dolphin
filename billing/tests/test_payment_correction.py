"""Correcting a recorded payment, and what that costs the ledger.

The product owner asked that the platform admin be able to fix any field on a
recorded document except its number and who recorded it. The fields are the easy
half. The hard half is that a confirmed payment has already posted a credit, so
changing its amount or its customer makes that entry wrong.

Nothing is rewritten: the ledger is append-only, so a correction reverses the old
entry and posts the new one — which is what a correction is in double entry, and
is what `cancel_payment` and `_post_payment_credit` already did between them. No
new accounting is invented; the two existing primitives are called in order.
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase

from accounts.models import User
from billing.ledger import current_balance
from billing.models import Cheque, CustomerLedgerEntry, Payment
from billing.payments import allocate_payment, register_payment, update_payment
from billing.services import create_invoice, issue_invoice
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class PaymentCorrectionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="fix.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.manager = User.objects.create_user(
            username="fix.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری اصلاح",
            phone={"raw_phone": "09121280000", "is_primary": True},
        )
        self.other = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دیگر",
            phone={"raw_phone": "09121280001", "is_primary": True},
        )

    def receipt(self, amount="1000.00", customer=None):
        return register_payment(
            actor=self.manager,
            customer=customer or self.customer,
            method=Payment.Method.CASH,
            amount=Decimal(amount),
        )

    # --- who may -----------------------------------------------------------

    def test_only_the_platform_admin_may_correct(self):
        """Checked in the service, not only where the form is drawn."""
        payment = self.receipt()
        with self.assertRaises(BusinessPermissionDenied):
            update_payment(actor=self.manager, payment=payment, notes="نه")

    def test_the_platform_admin_may(self):
        payment = self.receipt()
        fixed = update_payment(actor=self.admin, payment=payment, notes="اصلاح شد")
        self.assertEqual(fixed.notes, "اصلاح شد")

    def test_the_identity_of_the_document_is_not_editable(self):
        """`number` and `received_by` are refused as unknown fields."""
        payment = self.receipt()
        for field, value in (("number", "PY-999999"), ("received_by", self.admin.pk)):
            with self.subTest(field=field):
                with self.assertRaises(BusinessRuleError):
                    update_payment(actor=self.admin, payment=payment, **{field: value})

    # --- the ledger --------------------------------------------------------

    def test_changing_the_amount_restates_the_ledger_rather_than_rewriting_it(self):
        payment = self.receipt("1000.00")
        self.assertEqual(current_balance(self.customer), Decimal("-1000.00"))

        update_payment(actor=self.admin, payment=payment, amount=Decimal("2500.00"))

        # The balance is what the new amount says, and it got there by adding
        # entries rather than by editing one.
        self.assertEqual(current_balance(self.customer), Decimal("-2500.00"))
        kinds = list(
            CustomerLedgerEntry.objects.filter(reference_id=payment.pk)
            .order_by("id")
            .values_list("entry_type", flat=True)
        )
        self.assertEqual(
            kinds,
            [
                CustomerLedgerEntry.EntryType.PAYMENT_RECEIVED,
                CustomerLedgerEntry.EntryType.PAYMENT_CANCELLED,
                CustomerLedgerEntry.EntryType.PAYMENT_RECEIVED,
            ],
        )

    def test_moving_a_payment_to_another_customer_moves_the_money_with_it(self):
        payment = self.receipt("800.00")
        update_payment(actor=self.admin, payment=payment, customer=self.other)

        # The first customer is left owing what they did before the payment.
        self.assertEqual(current_balance(self.customer), Decimal("0.00"))
        self.assertEqual(current_balance(self.other), Decimal("-800.00"))

    def test_editing_only_words_posts_nothing(self):
        """A note is not money; correcting one must not move a balance."""
        payment = self.receipt("400.00")
        before = CustomerLedgerEntry.objects.count()
        update_payment(actor=self.admin, payment=payment, notes="فقط توضیح")
        self.assertEqual(CustomerLedgerEntry.objects.count(), before)
        self.assertEqual(current_balance(self.customer), Decimal("-400.00"))

    def test_cancelling_through_a_correction_reverses_the_credit(self):
        payment = self.receipt("600.00")
        update_payment(actor=self.admin, payment=payment, status=Payment.Status.CANCELLED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CANCELLED)
        self.assertEqual(current_balance(self.customer), Decimal("0.00"))

    def test_bringing_a_cancelled_payment_back_posts_a_fresh_credit(self):
        """The mirror of cancelling, and appended rather than un-erased."""
        payment = self.receipt("600.00")
        update_payment(actor=self.admin, payment=payment, status=Payment.Status.CANCELLED)
        update_payment(actor=self.admin, payment=payment, status=Payment.Status.CONFIRMED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.CONFIRMED)
        self.assertIsNone(payment.cancelled_at)
        self.assertEqual(current_balance(self.customer), Decimal("-600.00"))

    def test_the_status_has_only_the_two_values_an_operator_decides(self):
        """«در انتظار وصول» is a cheque's business, not an operator's answer."""
        payment = self.receipt()
        with self.assertRaises(BusinessRuleError):
            update_payment(
                actor=self.admin, payment=payment, status=Payment.Status.PENDING
            )

    # --- what a correction may not do --------------------------------------

    def test_an_amount_below_what_is_already_allocated_is_refused_in_words(self):
        """The database refuses this too, but only as a 500 nobody can act on."""
        warehouse = create_warehouse(actor=self.manager, code="fixwh", name="انبار")
        product = create_product(
            actor=self.manager, sku="FIX-1", name="کالا", current_price=Decimal("500.00")
        )
        record_stock_movement(
            actor=self.manager,
            warehouse=warehouse,
            product=product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=10,
            unit_cost=Decimal("100.00"),
        )
        invoice = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                warehouse=warehouse,
                items=[{"product": product, "quantity": 1}],
            ),
        )
        payment = self.receipt("500.00")
        allocate_payment(actor=self.manager, payment=payment, invoice=invoice)

        with self.assertRaises(BusinessRuleError) as caught:
            update_payment(actor=self.admin, payment=payment, amount=Decimal("100.00"))
        self.assertIn("amount", caught.exception.detail)

    def test_a_receipt_cannot_be_left_with_no_customer(self):
        payment = self.receipt()
        with self.assertRaises(BusinessRuleError):
            update_payment(actor=self.admin, payment=payment, customer=None)

    def test_the_cheques_two_axes_are_not_editable_here(self):
        """They move from the cheque page, through services that know the cost."""
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("300.00"),
            cheque={
                "bank_name": "بانک ملت",
                "serial_number": "77001",
                "due_date": date(2027, 3, 1),
            },
        )
        for field in ("status", "is_registered"):
            with self.subTest(field=field):
                with self.assertRaises(BusinessRuleError):
                    update_payment(
                        actor=self.admin, payment=payment, cheque={field: "cleared"}
                    )

    def test_the_cheques_own_details_are_editable(self):
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("300.00"),
            cheque={
                "bank_name": "بانک ملت",
                "serial_number": "77002",
                "due_date": date(2027, 3, 1),
            },
        )
        update_payment(
            actor=self.admin,
            payment=payment,
            cheque={"bank_name": "بانک صادرات", "serial_number": "77003"},
        )
        cheque = Cheque.objects.get(payment=payment)
        self.assertEqual(cheque.bank_name, "بانک صادرات")
        self.assertEqual(cheque.serial_number, "77003")
        # And its axes are untouched by an edit to its description.
        self.assertEqual(cheque.status, Cheque.Status.PENDING)
        self.assertFalse(cheque.is_registered)


class PaymentCorrectionApiTests(TestCase):
    """Over HTTP, because the role check has to hold at the door too."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="api.fix.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.manager = User.objects.create_user(
            username="api.fix.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری",
            phone={"raw_phone": "09121290000", "is_primary": True},
        )
        self.payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("900.00"),
        )

    def correct(self, user, body):
        client = Client()
        client.force_login(user)
        return client.post(
            f"/api/v1/payments/{self.payment.pk}/correct/",
            data=body,
            content_type="application/json",
        )

    def test_the_admin_can_correct_over_the_api(self):
        response = self.correct(self.admin, '{"notes": "اصلاح"}')
        self.assertEqual(response.status_code, 200, response.content.decode())
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.notes, "اصلاح")

    def test_a_manager_is_refused_by_the_api(self):
        """The page hides the controls; this is what actually stops them."""
        response = self.correct(self.manager, '{"notes": "نه"}')
        self.assertEqual(response.status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.notes, "")

    def test_an_anonymous_caller_reaches_nothing(self):
        response = Client().post(
            f"/api/v1/payments/{self.payment.pk}/correct/",
            data='{"notes": "x"}',
            content_type="application/json",
        )
        self.assertIn(response.status_code, (401, 403))
