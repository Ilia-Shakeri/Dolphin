"""The split-allocation endpoint, exercised through HTTP.

`test_payment_split.py` calls `allocate_payment_across()` directly and passes.
It passed while the endpoint was completely broken, because the defect was in
the serializer and a direct service call never touches one:
`AllocatePaymentSerializer` scoped its invoice queryset in `__init__`, and a
serializer nested as a field is constructed once at class-definition time with
no request in context — so the nested copy kept `Invoice.objects.none()` and
rejected every id as an invalid pk.

So these go over the wire. A service test and an API test are not the same
test, and this is the pair that proves it.
"""

import json
from decimal import Decimal

from django.test import Client, TestCase

from accounts.models import User
from billing.models import Invoice, Payment
from billing.payments import register_payment
from billing.services import create_invoice, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class SplitAllocationApiTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="sa.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.product = create_product(
            actor=self.manager, sku="SA-1", name="کالا", current_price=Decimal("100.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="sawh", name="انبار")
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
            full_name="مشتری تقسیم",
            phone={"raw_phone": "09121270000", "is_primary": True},
        )
        self.other = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دیگر",
            phone={"raw_phone": "09121270001", "is_primary": True},
        )
        self.client = Client()
        self.client.force_login(self.manager)

    def issued(self, *, quantity=1, customer=None):
        invoice = create_invoice(
            actor=self.manager,
            customer=customer or self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": quantity}],
        )
        return issue_invoice(actor=self.manager, invoice=invoice)

    def receipt(self, amount):
        return register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal(amount),
        )

    def post_split(self, payment, splits):
        return self.client.post(
            f"/api/v1/payments/{payment.pk}/allocate-across/",
            data=json.dumps({"splits": splits}),
            content_type="application/json",
        )

    # --- the defect this file exists for -----------------------------------

    def test_the_endpoint_accepts_an_invoice_the_caller_can_see(self):
        """The whole bug: every id came back as an invalid pk."""
        first = self.issued(quantity=1)
        second = self.issued(quantity=2)
        payment = self.receipt("300.00")

        response = self.post_split(
            payment,
            [
                {"invoice": first.pk, "amount": "100.00"},
                {"invoice": second.pk, "amount": "200.00"},
            ],
        )
        self.assertEqual(response.status_code, 201, response.content.decode())

        first.refresh_from_db()
        second.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(first.balance_due, Decimal("0.00"))
        self.assertEqual(second.balance_due, Decimal("0.00"))
        self.assertEqual(payment.unallocated_amount, Decimal("0.00"))

    def test_a_single_allocation_still_works_through_its_own_endpoint(self):
        """The same serializer serves `/allocate/`; the fix must not break it."""
        invoice = self.issued(quantity=1)
        payment = self.receipt("100.00")
        response = self.client.post(
            f"/api/v1/payments/{payment.pk}/allocate/",
            data=json.dumps({"invoice": invoice.pk, "amount": "100.00"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content.decode())

    def test_an_omitted_amount_takes_the_whole_balance(self):
        invoice = self.issued(quantity=1)
        payment = self.receipt("100.00")
        response = self.post_split(payment, [{"invoice": invoice.pk}])
        self.assertEqual(response.status_code, 201, response.content.decode())
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_due, Decimal("0.00"))

    # --- what the endpoint must still refuse -------------------------------

    def test_an_invoice_outside_the_split_is_refused_not_reached(self):
        """A scope that resolves per request must still be a scope."""
        mine = self.issued(quantity=1)
        theirs = self.issued(quantity=1, customer=self.other)
        payment = self.receipt("100.00")
        response = self.post_split(
            payment, [{"invoice": mine.pk}, {"invoice": theirs.pk}]
        )
        self.assertEqual(response.status_code, 400)

    def test_a_draft_invoice_is_not_selectable(self):
        issued = self.issued(quantity=1)
        draft = create_invoice(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        payment = self.receipt("100.00")
        response = self.post_split(
            payment, [{"invoice": issued.pk}, {"invoice": draft.pk}]
        )
        self.assertEqual(response.status_code, 400)

    def test_an_invoice_that_does_not_exist_is_refused(self):
        payment = self.receipt("100.00")
        self.assertEqual(self.post_split(payment, [{"invoice": 999999}]).status_code, 400)

    def test_the_same_invoice_twice_is_refused(self):
        invoice = self.issued(quantity=2)
        payment = self.receipt("200.00")
        response = self.post_split(
            payment,
            [
                {"invoice": invoice.pk, "amount": "50.00"},
                {"invoice": invoice.pk, "amount": "50.00"},
            ],
        )
        self.assertEqual(response.status_code, 400)

    def test_an_empty_split_is_refused(self):
        payment = self.receipt("100.00")
        self.assertEqual(self.post_split(payment, []).status_code, 400)

    def test_a_failed_split_allocates_nothing(self):
        first = self.issued(quantity=1)
        second = self.issued(quantity=1)
        payment = self.receipt("200.00")
        response = self.post_split(
            payment,
            [
                {"invoice": first.pk, "amount": "100.00"},
                {"invoice": second.pk, "amount": "500.00"},
            ],
        )
        self.assertEqual(response.status_code, 400)
        first.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(first.paid_amount, Decimal("0.00"))
        self.assertEqual(payment.allocated_amount, Decimal("0.00"))

    def test_an_anonymous_caller_reaches_nothing(self):
        invoice = self.issued(quantity=1)
        payment = self.receipt("100.00")
        anonymous = Client()
        response = anonymous.post(
            f"/api/v1/payments/{payment.pk}/allocate-across/",
            data=json.dumps({"splits": [{"invoice": invoice.pk}]}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (401, 403))
