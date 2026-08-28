"""One document, seen from both desks.

A cheque taken in from a customer and later handed to someone else is a single
document. It is still the receipt that was recorded, and it is also money that
has left — so the product owner's rule is that it appears on both screens, and
that its state is changed from the cheque page alone.

The important half of that rule is what it forbids. Endorsing a cheque does not
record a disbursement: a second document would count the same money twice, and
would debit a customer for a cheque that was never ours. So the paying desk is
a second *view* of the same row, expressed as a query, and never a second row.
"""

from datetime import date
from decimal import Decimal

from django.test import Client, TestCase

from accounts.models import User
from billing.models import Cheque, Payment
from billing.payments import register_payment, spend_received_cheque
from sales.services import create_customer_with_phone


PASSWORD = "Strong-pass-937!"


class PaymentDeskTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="desk.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری میز",
            phone={"raw_phone": "09121300000", "is_primary": True},
        )
        self.client = Client()
        self.client.force_login(self.manager)

    def cheque_receipt(self, serial="D-1"):
        return register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("500.00"),
            cheque={
                "bank_name": "بانک ملت",
                "serial_number": serial,
                "due_date": date(2027, 5, 1),
            },
        )

    def desk(self, which):
        response = self.client.get(f"/api/v1/payments/?desk={which}")
        self.assertEqual(response.status_code, 200, response.content.decode())
        return [row["number"] for row in response.json()["results"]]

    # --- the two desks ------------------------------------------------------

    def test_a_receipt_is_on_the_receiving_desk_only(self):
        payment = self.cheque_receipt()
        self.assertIn(payment.number, self.desk("receipt"))
        self.assertNotIn(payment.number, self.desk("disbursement"))

    def test_a_disbursement_is_on_the_paying_desk_only(self):
        payment = register_payment(
            actor=self.manager,
            customer=None,
            direction=Payment.Direction.DISBURSEMENT,
            method=Payment.Method.CASH,
            amount=Decimal("300.00"),
            payee="هزینه",
        )
        self.assertIn(payment.number, self.desk("disbursement"))
        self.assertNotIn(payment.number, self.desk("receipt"))

    def test_a_spent_cheque_appears_on_both_desks(self):
        """The product owner's rule: one document, two lists."""
        payment = self.cheque_receipt()
        spend_received_cheque(
            actor=self.manager, cheque=payment.cheque, payee="تأمین‌کننده"
        )
        self.assertIn(payment.number, self.desk("receipt"))
        self.assertIn(payment.number, self.desk("disbursement"))

    def test_spending_records_no_second_document(self):
        """The whole reason the paying desk is a query and not a new row.

        A disbursement for the endorsement would count the same money twice and
        would debit a customer for a cheque that was never ours.
        """
        before = Payment.objects.count()
        payment = self.cheque_receipt()
        spend_received_cheque(
            actor=self.manager, cheque=payment.cheque, payee="تأمین‌کننده"
        )
        self.assertEqual(Payment.objects.count(), before + 1)
        self.assertEqual(Cheque.objects.filter(payment=payment).count(), 1)

    def test_a_cheque_still_waiting_is_not_on_the_paying_desk(self):
        """Only a spent one has left; a pending cheque is still ours."""
        payment = self.cheque_receipt()
        self.assertNotIn(payment.number, self.desk("disbursement"))

    def test_a_cleared_cheque_is_not_on_the_paying_desk_either(self):
        """It was banked, not handed on — that is money arriving, not leaving."""
        from billing.payments import transition_cheque

        payment = self.cheque_receipt()
        transition_cheque(
            actor=self.manager, cheque=payment.cheque, to_status=Cheque.Status.CLEARED
        )
        self.assertIn(payment.number, self.desk("receipt"))
        self.assertNotIn(payment.number, self.desk("disbursement"))

    # --- the parameter itself ----------------------------------------------

    def test_an_unknown_desk_is_refused(self):
        response = self.client.get("/api/v1/payments/?desk=nowhere")
        self.assertEqual(response.status_code, 400)

    def test_direction_still_filters_on_its_own(self):
        """`desk` did not replace it; they answer different questions."""
        payment = self.cheque_receipt()
        spend_received_cheque(
            actor=self.manager, cheque=payment.cheque, payee="تأمین‌کننده"
        )
        response = self.client.get("/api/v1/payments/?direction=disbursement")
        numbers = [row["number"] for row in response.json()["results"]]
        # By direction it is a receipt, and it says so — only the desk view
        # gathers it up with money going out.
        self.assertNotIn(payment.number, numbers)
