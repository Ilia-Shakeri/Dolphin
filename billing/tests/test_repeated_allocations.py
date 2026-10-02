"""One receipt may be applied to the same invoice several times.

Example from the product owner: a 20,000,000 receipt allocated as 5,000,000 four
times to one invoice. Every row is its own allocation, and the receipt's
remainder, the invoice's balance and the instalments stay consistent through
allocating and through releasing any one row.
"""

from decimal import Decimal
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice, Payment, PaymentAllocation
from billing.payments import release_allocation
from billing.services import create_invoice, issue_invoice
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-939!"


class RepeatedAllocationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="rep.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(
            actor=self.manager, sku="REP-1", name="کالا", current_price=Decimal("5000000.00")
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری", phone={"raw_phone": "09121273333", "is_primary": True}
        )
        self.api = APIClient()
        self.api.force_authenticate(self.manager)
        invoice = create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": 4}], tax_rate=Decimal("0.00"),
        )
        self.invoice = issue_invoice(actor=self.manager, invoice=invoice)
        self.assertEqual(self.invoice.total_amount, Decimal("20000000.00"))

    def receipt(self, amount):
        response = self.api.post("/api/v1/payments/", {
            "method": "cash", "direction": "receipt", "customer": self.customer.pk, "amount": amount,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return Payment.objects.get(pk=response.json()["id"])

    def allocate(self, payment, rows):
        return self.api.post(f"/api/v1/payments/{payment.pk}/allocate-across/", {"splits": rows}, format="json")

    def test_four_allocations_of_one_receipt_to_one_invoice_settle_it(self):
        payment = self.receipt("20000000.00")
        for _ in range(4):
            response = self.allocate(payment, [{"invoice": self.invoice.pk, "amount": "5000000.00"}])
            self.assertEqual(response.status_code, 201, response.content)
        payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(payment.unallocated_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("20000000.00"))
        self.assertEqual(self.invoice.settlement_status, Invoice.SettlementStatus.PAID)
        self.assertEqual(PaymentAllocation.objects.filter(payment=payment, is_reversed=False).count(), 4)

    def test_the_same_invoice_may_be_listed_twice_in_one_request(self):
        payment = self.receipt("20000000.00")
        response = self.allocate(payment, [
            {"invoice": self.invoice.pk, "amount": "5000000.00"},
            {"invoice": self.invoice.pk, "amount": "7000000.00"},
        ])
        self.assertEqual(response.status_code, 201, response.content)
        payment.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("12000000.00"))

    def test_rows_that_add_up_past_the_invoice_balance_are_refused_whole(self):
        second = create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": 2}], tax_rate=Decimal("0.00"),
        )
        issue_invoice(actor=self.manager, invoice=second)
        payment = self.receipt("30000000.00")
        response = self.allocate(payment, [
            {"invoice": self.invoice.pk, "amount": "15000000.00"},
            {"invoice": self.invoice.pk, "amount": "6000000.00"},
        ])
        self.assertEqual(response.status_code, 400, response.content)
        payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(payment.allocated_amount, Decimal("0.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_rows_that_add_up_past_the_receipt_remainder_are_refused_whole(self):
        payment = self.receipt("8000000.00")
        response = self.allocate(payment, [
            {"invoice": self.invoice.pk, "amount": "5000000.00"},
            {"invoice": self.invoice.pk, "amount": "5000000.00"},
        ])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(PaymentAllocation.objects.count(), 0)

    def test_releasing_one_row_returns_exactly_its_amount(self):
        payment = self.receipt("20000000.00")
        for _ in range(4):
            self.allocate(payment, [{"invoice": self.invoice.pk, "amount": "5000000.00"}])
        one = PaymentAllocation.objects.filter(payment=payment).order_by("id")[1]
        release_allocation(actor=self.manager, allocation=one)
        payment.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertEqual(payment.unallocated_amount, Decimal("5000000.00"))
        self.assertEqual(self.invoice.paid_amount, Decimal("15000000.00"))
        self.assertEqual(self.invoice.settlement_status, Invoice.SettlementStatus.PARTIALLY_PAID)

    def test_the_integrity_check_is_clean_after_repeats_and_names_a_drift(self):
        payment = self.receipt("20000000.00")
        for _ in range(3):
            self.allocate(payment, [{"invoice": self.invoice.pk, "amount": "5000000.00"}])
        out = StringIO()
        call_command("check_allocation_integrity", stdout=out)
        self.assertIn("agree", out.getvalue())

        Payment.objects.filter(pk=payment.pk).update(allocated_amount=Decimal("1.00"))
        with self.assertRaises(SystemExit):
            call_command("check_allocation_integrity", stdout=StringIO())
