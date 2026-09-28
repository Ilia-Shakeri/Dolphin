"""Allocating a receipt to invoices from the «ثبت دریافت» wizard (2.28.0).

`POST /api/v1/payments/` accepts optional `allocations` — the same rows
`allocate-across/` takes — and records the payment and its allocations in one
transaction: an allocation the rules refuse means no payment either.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Payment, PaymentAllocation
from billing.services import create_invoice, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-939!"


class PaymentCreateAllocationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="pca.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(actor=self.manager, sku="PCA-1", name="کالا", current_price=Decimal("100.00"))
        warehouse = create_warehouse(actor=self.manager, code="pcawh", name="انبار")
        record_stock_movement(
            actor=self.manager, warehouse=warehouse, product=self.product,
            movement_type=StockMovement.MovementType.OPENING, quantity=500, unit_cost=Decimal("40.00"),
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری", phone={"raw_phone": "09121271111", "is_primary": True}
        )
        self.other = create_customer_with_phone(
            actor=self.manager, full_name="دیگری", phone={"raw_phone": "09121272222", "is_primary": True}
        )
        self.api = APIClient()
        self.api.force_authenticate(self.manager)

    def issued(self, customer, quantity):
        return issue_invoice(actor=self.manager, invoice=create_invoice(
            actor=self.manager, customer=customer, items=[{"product": self.product, "quantity": quantity}],
        ))

    def post(self, **body):
        payload = {"method": "cash", "direction": "receipt", "customer": self.customer.pk, "amount": "500.00", **body}
        return self.api.post("/api/v1/payments/", payload, format="json")

    def test_a_receipt_is_recorded_and_allocated_together(self):
        first, second = self.issued(self.customer, 2), self.issued(self.customer, 4)
        response = self.post(allocations=[{"invoice": first.pk}, {"invoice": second.pk, "amount": "150.00"}])
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(Decimal(body["allocated_amount"]), Decimal("350.00"))
        self.assertEqual(Decimal(body["unallocated_amount"]), Decimal("150.00"))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.balance_due, Decimal("0.00"))
        self.assertEqual(second.balance_due, Decimal("250.00"))

    def test_without_allocations_it_is_the_ordinary_receipt(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Decimal(response.json()["allocated_amount"]), Decimal("0.00"))

    def test_a_refused_allocation_records_no_payment_at_all(self):
        """Another customer's invoice: the receipt is not left behind half-done."""
        foreign = self.issued(self.other, 1)
        response = self.post(allocations=[{"invoice": foreign.pk}])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("allocations", response.json()["errors"] if "errors" in response.json() else response.json())
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(PaymentAllocation.objects.exists())

    def test_more_than_the_invoice_owes_is_refused_as_an_allocation_error(self):
        invoice = self.issued(self.customer, 1)
        # Enough owed overall that the receipt itself is valid — a receipt may
        # not exceed the customer's debt (`_refuse_overpayment`) — so what is
        # refused is the allocation alone: 400 against an invoice of 100.
        self.issued(self.customer, 5)
        response = self.post(allocations=[{"invoice": invoice.pk, "amount": "400.00"}])
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        errors = body.get("errors", body)
        self.assertIn("allocations", errors)
        self.assertNotIn("amount", errors)
        self.assertFalse(Payment.objects.exists())

    def test_the_same_invoice_twice_is_refused(self):
        invoice = self.issued(self.customer, 1)
        response = self.post(allocations=[{"invoice": invoice.pk}, {"invoice": invoice.pk}])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(Payment.objects.exists())
