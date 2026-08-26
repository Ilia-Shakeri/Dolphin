from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from billing.models import Cheque, Payment
from billing.payments import (
    allocate_payment,
    create_installment_plan,
    register_payment,
    transition_cheque,
)
from billing.services import create_invoice, create_order, create_quotation, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.models import Customer, CustomerPhone, Interaction, Lead, Product, Sale
from sales.services import create_customer_with_phone, create_product


class ListQueryGrowthTests(TestCase):
    paths = (
        "/api/v1/users/",
        "/api/v1/activity-logs/",
        "/api/v1/customers/",
        "/api/v1/customer-phones/",
        "/api/v1/leads/",
        "/api/v1/interactions/",
        "/api/v1/products/",
        "/api/v1/sales/",
    )

    def setUp(self):
        # Throttle history is keyed by user id and lives in the process cache,
        # which the test database rollback does not touch. Without this, a
        # user id reused from an earlier test arrives already throttled and
        # this test fails on a 429 that has nothing to do with query counts.
        cache.clear()
        self.admin = User.objects.create_user(
            username="query-admin",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _add_graph(self, index):
        worker = User.objects.create(username=f"query-worker-{index}", role=User.Role.SALES_AGENT)
        customer = Customer.objects.create(full_name=f"Customer {index}", created_by=worker)
        CustomerPhone.objects.create(
            customer=customer,
            raw_phone=f"0912{index:07d}",
            normalized_phone=f"+98912{index:07d}",
            is_primary=True,
        )
        product = Product.objects.create(
            sku=f"QUERY-{index}",
            name=f"Product {index}",
            current_price=Decimal("10.00"),
            created_by=self.admin,
            updated_by=self.admin,
        )
        now = timezone.now()
        lead = Lead.objects.create(
            customer=customer,
            created_by=worker,
            assigned_to=worker,
            assigned_by=self.admin,
            assigned_at=now,
            interested_product=product,
        )
        Interaction.objects.create(
            lead=lead,
            customer=customer,
            agent=worker,
            phone=f"0912{index:07d}",
            direction="outbound",
            outcome="answered",
            occurred_at=now,
        )
        Sale.objects.create(
            lead=lead,
            customer=customer,
            sold_by=worker,
            quantity=1,
            total_amount=Decimal("10.00"),
            sold_at=now,
        )
        ActivityLog.objects.create(
            actor=worker,
            actor_role_snapshot=User.Role.SALES_AGENT,
            operation="query.probe",
            object_type="sales.customer",
            object_id=str(customer.pk),
        )

    def _query_count(self, path):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return len(captured)

    def test_list_query_count_does_not_grow_with_rows(self):
        self._add_graph(1)
        for path in self.paths:
            self.client.get(path)
        small_counts = {path: self._query_count(path) for path in self.paths}

        for index in range(2, 6):
            self._add_graph(index)
        large_counts = {path: self._query_count(path) for path in self.paths}

        for path in self.paths:
            with self.subTest(path=path):
                self.assertLessEqual(large_counts[path], small_counts[path])


class CommercialListQueryGrowthTests(TestCase):
    """The new list endpoints must not issue one query per row.

    A commercial document list is the worst case in this codebase: each row has
    a customer, a creator, and a set of lines. Without `select_related` and
    `prefetch_related` the query count would climb linearly with the page, which
    is exactly what this measures rather than assumes.
    """

    paths = (
        "/api/v1/warehouses/",
        "/api/v1/stock-items/",
        "/api/v1/stock-movements/",
        "/api/v1/quotations/",
        "/api/v1/orders/",
        "/api/v1/invoices/",
        "/api/v1/payments/",
        "/api/v1/cheques/",
        "/api/v1/installments/",
        "/api/v1/customer-ledger/",
    )

    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(
            username="growth-manager",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.warehouse = create_warehouse(
            actor=self.manager, code="growthwh", name="Growth warehouse"
        )
        self.product = create_product(
            actor=self.manager, sku="GROWTH-1", name="Growth product", current_price=Decimal("100.00")
        )
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=10_000,
            unit_cost=Decimal("50.00"),
        )

    def _add_commercial_graph(self, index):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name=f"Growth customer {index}",
            phone={"raw_phone": f"0912555{index:04d}", "is_primary": True},
        )
        create_quotation(
            actor=self.manager,
            customer=customer,
            items=[{"product": self.product, "quantity": 1}, {"product": self.product, "quantity": 2}],
        )
        create_order(
            actor=self.manager,
            customer=customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        invoice = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=customer,
                items=[{"product": self.product, "quantity": 1}, {"product": self.product, "quantity": 3}],
                warehouse=self.warehouse,
            ),
        )
        payment = register_payment(
            actor=self.manager,
            customer=customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("50.00"),
            cheque={
                "bank_name": "Growth bank",
                "serial_number": f"GS-{index}",
                "due_date": date(2026, 12, 1),
            },
        )
        cheque = Cheque.objects.get(payment=payment)
        transition_cheque(actor=self.manager, cheque=cheque, to_status=Cheque.Status.CLEARED)
        allocate_payment(
            actor=self.manager,
            payment=Payment.objects.get(pk=payment.pk),
            invoice=invoice,
            amount=Decimal("50.00"),
        )
        create_installment_plan(
            actor=self.manager, invoice=invoice, installment_count=3, start_date=date(2026, 9, 1)
        )

    def _query_count(self, path):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return len(captured)

    def test_list_query_count_does_not_grow_with_rows(self):
        self._add_commercial_graph(1)
        for path in self.paths:
            self.client.get(path)
        small_counts = {path: self._query_count(path) for path in self.paths}

        for index in range(2, 6):
            self._add_commercial_graph(index)
        large_counts = {path: self._query_count(path) for path in self.paths}

        for path in self.paths:
            with self.subTest(path=path):
                self.assertLessEqual(large_counts[path], small_counts[path])

    def test_every_commercial_list_is_paginated(self):
        for index in range(1, 4):
            self._add_commercial_graph(index)
        for path in self.paths:
            with self.subTest(path=path):
                payload = self.client.get(path).json()
                # A page envelope, not a bare array: an unbounded list is how a
                # report page becomes unusable once the data is real.
                self.assertIn("count", payload)
                self.assertIn("results", payload)
                self.assertLessEqual(len(payload["results"]), 25)
