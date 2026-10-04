"""Issuing an invoice fails in a way the operator can read, and fails whole.

The invoice page changes status from a select and calls `POST …/issue/`. Every
refusal below used to reach the reader as a generic «داده‌های واردشده درست نیست»
(the server's reason was dropped), and one database constraint was reported as a
duplicate document number. These tests pin both halves: each refusal carries its
own Persian reason, and a refused issue leaves no trace — still a draft, no
official number spent, no ledger entry, no stock movement.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import CustomerLedgerEntry, DocumentSequence, Invoice
from billing.services import create_invoice, issue_invoice
from common.exceptions import BusinessRuleError
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-937!"


class IssueFailureTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="issue.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="issue.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.product = create_product(
            actor=self.manager, sku="ISS-1", name="کالا", current_price=Decimal("1000.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="isswh", name="انبار")
        record_stock_movement(
            actor=self.manager, warehouse=self.warehouse, product=self.product,
            movement_type=StockMovement.MovementType.OPENING, quantity=5, unit_cost=Decimal("400.00"),
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری آزمون", phone={"raw_phone": "09121110001"}
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def draft(self, *, quantity=1, **extra):
        return create_invoice(
            actor=self.manager, customer=self.customer,
            items=[{"product": self.product, "quantity": quantity, "unit_price": self.product.current_price}],
            **extra,
        )

    def issue(self, invoice):
        return self.client.post(f"/api/v1/invoices/{invoice.pk}/issue/", {}, format="json")

    def assertUntouched(self, invoice, *, movements_before):
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        self.assertEqual(invoice.official_number, "")
        self.assertFalse(invoice.stock_applied)
        self.assertEqual(CustomerLedgerEntry.objects.filter(customer=self.customer).count(), 0)
        self.assertEqual(StockMovement.objects.count(), movements_before)

    def test_an_official_invoice_without_the_sellers_identity_says_what_is_missing(self):
        invoice = self.draft(invoice_type=Invoice.InvoiceType.OFFICIAL)
        before = StockMovement.objects.count()
        sequence = DocumentSequence.objects.filter(kind="official_invoice").first()
        next_before = sequence.next_value if sequence else None

        response = self.issue(invoice)

        self.assertEqual(response.status_code, 400)
        self.assertIn("seller_legal_name", response.json())
        self.assertUntouched(invoice, movements_before=before)
        sequence = DocumentSequence.objects.filter(kind="official_invoice").first()
        self.assertEqual(sequence.next_value if sequence else None, next_before)

    @override_settings(BILLING_INVOICE_AFFECTS_STOCK=True)
    def test_a_stock_shortfall_is_refused_with_its_reason_and_leaves_no_trace(self):
        invoice = self.draft(quantity=50, warehouse=self.warehouse)
        before = StockMovement.objects.count()

        response = self.issue(invoice)

        self.assertIn(response.status_code, (400, 409))
        self.assertTrue(any(isinstance(value, str) and value for key, value in response.json().items() if key != "error"))
        self.assertUntouched(invoice, movements_before=before)

    def test_issuing_twice_is_a_conflict_not_a_second_ledger_entry(self):
        invoice = self.draft()
        self.assertEqual(self.issue(invoice).status_code, 200)
        entries = CustomerLedgerEntry.objects.filter(customer=self.customer).count()

        response = self.issue(invoice)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(CustomerLedgerEntry.objects.filter(customer=self.customer).count(), entries)

    def test_a_marketer_cannot_issue(self):
        invoice = self.draft()
        client = APIClient()
        client.force_authenticate(self.agent)

        response = client.post(f"/api/v1/invoices/{invoice.pk}/issue/", {}, format="json")

        self.assertIn(response.status_code, (403, 404))
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)

    def test_an_instalment_invoice_without_its_first_due_date_is_not_reported_as_a_duplicate_number(self):
        with self.assertRaises(BusinessRuleError) as raised:
            self.draft(
                payment_type=Invoice.PaymentType.INSTALLMENT,
                installment_down_payment=Decimal("100.00"), installment_count=3,
                installment_interval_days=30,
            )
        detail = raised.exception.detail
        self.assertIn("installment_first_due", detail)
        self.assertNotIn("number", detail)

    def test_a_complete_instalment_invoice_issues(self):
        invoice = self.draft(
            payment_type=Invoice.PaymentType.INSTALLMENT,
            installment_down_payment=Decimal("100.00"), installment_count=3,
            installment_first_due=date.today() + timedelta(days=30), installment_interval_days=30,
        )
        issue_invoice(actor=self.manager, invoice=invoice)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)
        self.assertEqual(invoice.installment_plan.installments.count(), 4)


class IssueQueryCountTests(TestCase):
    def test_issuing_reads_costs_once_however_many_lines(self):
        from inventory.services import create_warehouse

        manager = User.objects.create_user(username="qc.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER)
        customer = create_customer_with_phone(actor=manager, full_name="م", phone={"raw_phone": "09121110088"})
        warehouse = create_warehouse(actor=manager, code="qcwh", name="انبار")
        products = [
            create_product(actor=manager, sku=f"QC-{n}", name=f"کالا {n}", current_price=Decimal("10.00")) for n in range(6)
        ]

        def issue(count):
            draft = create_invoice(
                actor=manager, customer=customer, warehouse=warehouse,
                items=[{"product": product, "quantity": 1, "unit_price": product.current_price} for product in products[:count]],
            )
            with CaptureQueriesContext(connection) as queries:
                issue_invoice(actor=manager, invoice=draft)
            return len(queries)

        issue(1)  # first issue creates one-off rows (number sequence…) that are not per line
        self.assertEqual(issue(2), issue(6))
