"""The manual-settlement and order-link endpoints, over HTTP.

The service layer is tested separately; what matters here is that the routes
enforce the same scope, refuse the same things, and publish enough for a reader
to tell a manual settlement from a real one.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import CustomerLedgerEntry, Invoice, Payment, PaymentAllocation
from billing.services import create_invoice, create_order, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


PASSWORD = "Strong-pass-937!"


class InvoiceActionApiTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="ia.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="ia.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری API",
            phone={"raw_phone": "09129990000", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="IA-1", name="کالای API", current_price=Decimal("250.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="iawh", name="انبار API")
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=50,
            unit_cost=Decimal("100.00"),
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.manager)

    def _issued(self, quantity=2):
        return issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": self.product, "quantity": quantity}],
            ),
        )

    # --- manual settlement --------------------------------------------------

    def test_the_endpoint_settles_on_an_exact_match_and_says_so(self):
        invoice = self._issued()
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["is_manually_settled"])
        self.assertEqual(Decimal(body["balance_due"]), Decimal("0.00"))
        self.assertEqual(body["settlement_status"], Invoice.SettlementStatus.PAID)
        # The canonical figure is published alongside, still telling the truth.
        self.assertEqual(Decimal(body["canonical_balance_due"]), invoice.total_amount)
        self.assertEqual(Decimal(body["paid_amount"]), Decimal("0.00"))

    def test_the_endpoint_writes_no_accounting_records(self):
        invoice = self._issued()
        before = (
            Payment.objects.count(),
            PaymentAllocation.objects.count(),
            CustomerLedgerEntry.objects.count(),
        )
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        after = (
            Payment.objects.count(),
            PaymentAllocation.objects.count(),
            CustomerLedgerEntry.objects.count(),
        )
        self.assertEqual(before, after)

    def test_a_later_edit_cannot_unsettle_it_over_http(self):
        invoice = self._issued()
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/", {"amount": "1.00"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_manually_settled"])
        self.assertEqual(response.json()["settlement_status"], Invoice.SettlementStatus.PAID)

    def test_settlement_status_cannot_be_written_directly(self):
        invoice = self._issued()
        response = self.client_api.patch(
            f"/api/v1/invoices/{invoice.pk}/",
            {"settlement_status": Invoice.SettlementStatus.PAID},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_marketer_cannot_settle_an_invoice_they_do_not_own(self):
        invoice = self._issued()
        agent_client = APIClient()
        agent_client.force_authenticate(self.agent)
        response = agent_client.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        self.assertIn(response.status_code, (403, 404))

    # --- linking ------------------------------------------------------------

    def test_an_invoice_can_be_attached_to_an_order_over_http(self):
        invoice = self._issued()
        order = create_order(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/link-order/", {"order": order.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["order"], order.pk)

    def test_the_link_can_be_cleared_with_null(self):
        invoice = self._issued()
        order = create_order(
            actor=self.manager,
            customer=self.customer,
            warehouse=self.warehouse,
            items=[{"product": self.product, "quantity": 1}],
        )
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/link-order/", {"order": order.pk}, format="json"
        )
        response = self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/link-order/", {"order": None}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["order"])

    def test_the_settlement_filter_agrees_with_the_document(self):
        invoice = self._issued()
        self.client_api.post(
            f"/api/v1/invoices/{invoice.pk}/manual-paid/",
            {"amount": str(invoice.canonical_balance_due)},
            format="json",
        )
        paid = self.client_api.get("/api/v1/invoices/?settlement=paid").json()
        unpaid = self.client_api.get("/api/v1/invoices/?settlement=unpaid").json()
        self.assertIn(invoice.pk, [row["id"] for row in paid["results"]])
        self.assertNotIn(invoice.pk, [row["id"] for row in unpaid["results"]])
