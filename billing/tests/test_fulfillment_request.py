"""Warehouse fulfilment requests made from an issued invoice (2.37.0).

The request is an `Order` carrying `invoice`; the order's stock mechanism is
unchanged. What these tests pin is the new contract around it: it exists only for
an issued invoice, at most one is open per invoice, nothing about it is typed in
(customer, lines, prices), the warehouse side approves it, and approval cannot
take the same goods twice.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice, Order
from billing.services import (
    cancel_invoice,
    create_fulfillment_request,
    create_invoice,
    issue_invoice,
    replace_order_items,
    transition_order,
    update_order,
)
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockItem, StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-937!"


class Fixtures(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="ful.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="ful.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.product = create_product(actor=self.manager, sku="FUL-1", name="کالا", current_price=Decimal("1000.00"))
        self.warehouse = create_warehouse(actor=self.manager, code="fulwh", name="انبار")
        record_stock_movement(
            actor=self.manager, warehouse=self.warehouse, product=self.product,
            movement_type=StockMovement.MovementType.OPENING, quantity=10, unit_cost=Decimal("400.00"),
        )
        # the marketer's own customer, so the marketer sees the invoice
        self.customer = create_customer_with_phone(actor=self.agent, full_name="خریدار", phone={"raw_phone": "09121110001"})

    def issued(self, quantity=2):
        # A marketer sees the documents they raised, so the marketer drafts and
        # the manager issues.
        draft = create_invoice(
            actor=self.agent, customer=self.customer,
            items=[{"product": self.product, "quantity": quantity, "unit_price": self.product.current_price}],
        )
        return issue_invoice(actor=self.manager, invoice=draft)

    def on_hand(self):
        item = StockItem.objects.filter(warehouse=self.warehouse, product=self.product).first()
        return item.quantity if item else 0

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class CreationTests(Fixtures):
    def test_only_an_issued_invoice_can_be_requested(self):
        draft = create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        )
        with self.assertRaises(BusinessConflictError):
            create_fulfillment_request(actor=self.manager, invoice=draft, warehouse=self.warehouse)

    def test_everything_is_derived_from_the_invoice(self):
        invoice = self.issued(quantity=3)
        request = create_fulfillment_request(actor=self.agent, invoice=invoice, warehouse=self.warehouse, notes="فوری")
        self.assertEqual(request.invoice, invoice)
        self.assertEqual(request.customer, invoice.customer)
        self.assertEqual(request.status, Order.Status.DRAFT)
        self.assertEqual(request.total_amount, invoice.total_amount)
        lines = list(request.items.values_list("product_id", "quantity"))
        self.assertEqual(lines, [(self.product.pk, 3)])

    def test_a_warehouse_is_required(self):
        with self.assertRaises(BusinessRuleError):
            create_fulfillment_request(actor=self.manager, invoice=self.issued(), warehouse=None)

    def test_only_one_open_request_per_invoice_until_it_is_cancelled(self):
        invoice = self.issued()
        first = create_fulfillment_request(actor=self.manager, invoice=invoice, warehouse=self.warehouse)
        with self.assertRaises(BusinessConflictError):
            create_fulfillment_request(actor=self.manager, invoice=invoice, warehouse=self.warehouse)
        transition_order(actor=self.manager, order=first, to_status=Order.Status.CANCELLED)
        again = create_fulfillment_request(actor=self.manager, invoice=invoice, warehouse=self.warehouse)
        self.assertNotEqual(again.pk, first.pk)

    def test_the_api_refuses_anything_that_belongs_to_the_invoice(self):
        invoice = self.issued()
        body = {"invoice": invoice.pk, "warehouse": self.warehouse.pk}
        for extra in ({"unit_price": "1"}, {"discount_amount": "5"}, {"customer": self.customer.pk}, {"items": []}, {"quantity": 9}):
            with self.subTest(extra=extra):
                response = self.api(self.manager).post("/api/v1/orders/from-invoice/", {**body, **extra}, format="json")
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(Order.objects.filter(invoice=invoice).count(), 0)
        ok = self.api(self.manager).post("/api/v1/orders/from-invoice/", body, format="json")
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(ok.data["invoice"], invoice.pk)
        self.assertEqual(ok.data["invoice_number"], invoice.number)

    def test_the_request_cannot_be_edited_away_from_the_invoice(self):
        request = create_fulfillment_request(actor=self.manager, invoice=self.issued(), warehouse=self.warehouse)
        with self.assertRaises(BusinessConflictError):
            replace_order_items(actor=self.manager, order=request, items=[
                {"product": self.product, "quantity": 1, "unit_price": Decimal("1.00")}
            ])
        with self.assertRaises(BusinessConflictError):
            update_order(actor=self.manager, order=request, discount_amount=Decimal("10"))
        update_order(actor=self.manager, order=request, notes="یادداشت")  # a note is fine


class ApprovalTests(Fixtures):
    def test_the_warehouse_side_approves_and_stock_leaves_exactly_once(self):
        request = create_fulfillment_request(actor=self.agent, invoice=self.issued(quantity=4), warehouse=self.warehouse)
        with self.assertRaises(BusinessPermissionDenied):
            transition_order(actor=self.agent, order=request, to_status=Order.Status.CONFIRMED)
        self.assertEqual(self.on_hand(), 10)
        transition_order(actor=self.manager, order=request, to_status=Order.Status.CONFIRMED)
        self.assertEqual(self.on_hand(), 6)
        request.refresh_from_db()
        self.assertTrue(request.stock_applied)
        with self.assertRaises(BusinessConflictError):  # no second approval
            transition_order(actor=self.manager, order=request, to_status=Order.Status.CONFIRMED)
        self.assertEqual(self.on_hand(), 6)
        transition_order(actor=self.manager, order=request, to_status=Order.Status.CANCELLED)
        self.assertEqual(self.on_hand(), 10)  # the goods come back once

    def test_it_cannot_double_deduct_against_an_invoice_that_already_took_stock(self):
        with override_settings(BILLING_INVOICE_AFFECTS_STOCK=True):
            draft = create_invoice(
                actor=self.agent, customer=self.customer, warehouse=self.warehouse,
                items=[{"product": self.product, "quantity": 2, "unit_price": self.product.current_price}],
            )
            invoice = issue_invoice(actor=self.manager, invoice=draft)
        invoice.refresh_from_db()
        self.assertTrue(invoice.stock_applied)
        self.assertEqual(self.on_hand(), 8)
        with self.assertRaises(BusinessConflictError):
            create_fulfillment_request(actor=self.manager, invoice=invoice, warehouse=self.warehouse)
        self.assertEqual(self.on_hand(), 8)


class InvoiceCancellationTests(Fixtures):
    def test_an_invoice_with_an_open_request_cannot_be_cancelled(self):
        invoice = self.issued()
        request = create_fulfillment_request(actor=self.manager, invoice=invoice, warehouse=self.warehouse)
        with self.assertRaises(BusinessConflictError) as caught:
            cancel_invoice(actor=self.manager, invoice=invoice, reason="آزمون")
        self.assertIn(request.number, str(caught.exception.detail))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        transition_order(actor=self.manager, order=request, to_status=Order.Status.CANCELLED)
        cancel_invoice(actor=self.manager, invoice=invoice, reason="آزمون")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.CANCELLED)


class BatchTests(Fixtures):
    def test_several_invoices_of_different_customers_go_out_as_one_numbered_document(self):
        first = self.issued(quantity=1)
        other = create_customer_with_phone(actor=self.agent, full_name="خریدار دو", phone={"raw_phone": "09121110002"})
        second = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.agent, customer=other,
                items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
            ),
        )
        response = self.api(self.agent).post(
            "/api/v1/orders/from-invoices/",
            {"invoices": [first.pk, second.pk], "warehouse": self.warehouse.pk}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertTrue(body["batch_number"].startswith("SB-"))
        self.assertEqual(len(body["orders"]), 2)
        self.assertEqual({row["batch_number"] for row in body["orders"]}, {body["batch_number"]})

    def test_one_bad_invoice_fails_the_whole_document(self):
        good = self.issued(quantity=1)
        draft = create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        )
        response = self.api(self.manager).post(
            "/api/v1/orders/from-invoices/",
            {"invoices": [good.pk, draft.pk], "warehouse": self.warehouse.pk}, format="json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertFalse(Order.objects.exclude(batch_number="").exists())
        self.assertFalse(Order.objects.filter(invoice=good).exists())


class CancelFulfilledTests(Fixtures):
    def test_a_fulfilled_request_can_be_cancelled_and_the_goods_come_back(self):
        request = create_fulfillment_request(actor=self.agent, invoice=self.issued(quantity=4), warehouse=self.warehouse)
        transition_order(actor=self.manager, order=request, to_status=Order.Status.CONFIRMED)
        transition_order(actor=self.manager, order=request, to_status=Order.Status.FULFILLED)
        self.assertEqual(self.on_hand(), 6)
        transition_order(actor=self.manager, order=request, to_status=Order.Status.CANCELLED)
        request.refresh_from_db()
        self.assertEqual((request.status, self.on_hand()), (Order.Status.CANCELLED, 10))

    def test_an_ordinary_fulfilled_order_stays_final(self):
        order = Order.objects.create(
            number="SO-TEST-1", customer=self.customer, created_by=self.manager, status=Order.Status.FULFILLED
        )
        with self.assertRaises(BusinessConflictError):
            transition_order(actor=self.manager, order=order, to_status=Order.Status.CANCELLED)


class HeaderCopyTests(Fixtures):
    def test_the_request_restates_the_invoices_header_discount_tax_and_total(self):
        invoice = self.issued(quantity=2)
        request = create_fulfillment_request(actor=self.agent, invoice=invoice, warehouse=self.warehouse)
        self.assertEqual(
            (request.discount_amount, request.tax_rate, request.total_amount),
            (invoice.discount_amount, invoice.tax_rate, invoice.total_amount),
        )
