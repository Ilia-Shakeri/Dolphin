"""A resent allocation is answered, not repeated; a release keeps its reason (2.39.18)."""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Payment, PaymentAllocation
from billing.payments import allocate_payment_across, register_payment, release_allocation
from billing.services import create_invoice, issue_invoice
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-937!"


class AllocationIdempotencyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(username="idem.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.customer = create_customer_with_phone(actor=self.manager, full_name="مشتری", phone={"raw_phone": "09121110066"})
        product = create_product(actor=self.manager, sku="ID-1", name="کالا", current_price=Decimal("20000000.00"))
        self.invoice = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager, customer=self.customer,
                items=[{"product": product, "quantity": 1, "unit_price": product.current_price}],
            ),
        )
        self.receipt = register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH, amount=Decimal("20000000.00")
        )

    def test_the_same_submission_twice_makes_its_rows_once(self):
        split = [{"invoice": self.invoice, "amount": Decimal("5000000.00")}]
        first = allocate_payment_across(actor=self.manager, payment=self.receipt, splits=split, request_key="k-1")
        again = allocate_payment_across(actor=self.manager, payment=self.receipt, splits=split, request_key="k-1")
        self.assertEqual([row.pk for row in first], [row.pk for row in again])
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.receipt).count(), 1)

    def test_four_deliberate_allocations_of_the_same_amount_are_all_kept(self):
        split = [{"invoice": self.invoice, "amount": Decimal("5000000.00")}]
        for number in range(4):
            allocate_payment_across(actor=self.manager, payment=self.receipt, splits=split, request_key=f"k-{number}")
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("20000000.00"))
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.receipt).count(), 4)

    def test_the_api_takes_the_key(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        body = {"splits": [{"invoice": self.invoice.pk, "amount": "5000000.00"}], "request_key": "api-1"}
        url = f"/api/v1/payments/{self.receipt.pk}/allocate-across/"
        self.assertEqual(client.post(url, body, format="json").status_code, 201)
        self.assertEqual(client.post(url, body, format="json").status_code, 201)
        self.assertEqual(PaymentAllocation.objects.filter(payment=self.receipt).count(), 1)

    def test_a_release_keeps_the_reason_written(self):
        [row] = allocate_payment_across(
            actor=self.manager, payment=self.receipt, splits=[{"invoice": self.invoice, "amount": Decimal("1.00")}]
        )
        release_allocation(actor=self.manager, allocation=row, reason="اشتباه در مبلغ")
        row.refresh_from_db()
        self.assertEqual(row.release_reason, "اشتباه در مبلغ")
