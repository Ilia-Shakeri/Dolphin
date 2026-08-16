"""Every inventory, billing, and financial-report page is really wired.

The point of this module is the connection, not the arithmetic (which
`billing/tests/test_end_to_end.py` covers): each served page loads, each role
sees exactly the pages its capabilities allow, each `data-page` has a handler in
the maintained script, and a feature this deployment does not run is absent
rather than merely hidden.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import User
from billing.models import Invoice, Payment, Quotation
from billing.payments import register_payment
from billing.services import (
    convert_order_to_invoice,
    convert_quotation_to_order,
    create_quotation,
    issue_invoice,
    transition_order,
    transition_quotation,
)
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product, create_product_category


ROOT = Path(__file__).resolve().parents[2]

MANAGER_PAGES = (
    "/warehouses/",
    "/stock/",
    "/stock/movements/",
    "/quotations/",
    "/orders/",
    "/invoices/",
    "/payments/",
    "/cheques/",
    "/installments/",
    "/reports/receivables/",
    "/reports/profit/",
    "/reports/stock-valuation/",
    "/reports/customer-ledger/",
)
# What a Sales Agent may reach: they prepare documents and read stock, and they
# never touch money. These three lists are the whole of the difference.
AGENT_ALLOWED_PAGES = ("/warehouses/", "/stock/", "/stock/movements/", "/quotations/", "/orders/", "/invoices/")
AGENT_FORBIDDEN_PAGES = (
    "/payments/",
    "/cheques/",
    "/installments/",
    "/reports/receivables/",
    "/reports/profit/",
    "/reports/stock-valuation/",
    "/reports/customer-ledger/",
)


class BillingScriptContractTests(SimpleTestCase):
    def test_every_new_page_has_a_handler_and_no_dead_control_pattern(self):
        script = (ROOT / "common" / "static" / "common" / "kariz-app.js").read_text(encoding="utf-8")
        for page in (
            "warehouses", "warehouse-detail", "stock-levels", "stock-movements",
            "quotations", "quotation-detail", "orders", "order-detail",
            "invoices", "invoice-detail", "payments", "payment-detail",
            "cheques", "installments", "customer-ledger",
            "receivables-report", "profit-report", "stock-valuation-report",
            "invoice-print", "quotation-print",
        ):
            self.assertIn(f'page === "{page}"', script)
        for endpoint in (
            "/api/v1/warehouses/", "/api/v1/stock-items/", "/api/v1/stock-movements/",
            "/api/v1/quotations/", "/api/v1/orders/", "/api/v1/invoices/",
            "/api/v1/payments/", "/api/v1/cheques/", "/api/v1/installments/",
            "/api/v1/customer-ledger/", "/api/v1/reports/receivables/",
            "/api/v1/reports/profit/", "/api/v1/reports/stock-valuation/",
        ):
            self.assertIn(endpoint, script)

    def test_new_templates_carry_no_placeholder_control(self):
        templates = ROOT / "common" / "templates" / "common"
        for folder in ("warehouses", "inventory", "quotations", "orders", "invoices", "payments"):
            for path in (templates / folder).glob("*.html"):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn('href="#"', text, path.name)
                self.assertNotIn("javascript:void", text, path.name)
                self.assertNotIn('action=""', text, path.name)


class CommercialWorldMixin:
    """One manager, one agent, and a fully populated commercial chain."""

    def build_world(self):
        self.manager = User.objects.create_user(
            username="shell.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="shell.agent", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )
        self.other_agent = User.objects.create_user(
            username="shell.other", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری آزمون",
            phone={"raw_phone": "09121110000", "is_primary": True},
        )
        category = create_product_category(actor=self.manager, code="shell", name="دسته آزمون")
        self.product = create_product(
            actor=self.manager,
            sku="SHELL-1",
            name="کالای آزمون",
            category=category,
            current_price=Decimal("250.00"),
        )
        self.warehouse = create_warehouse(
            actor=self.manager, code="shellwh", name="انبار آزمون", is_default=True
        )
        record_stock_movement(
            actor=self.manager,
            warehouse=self.warehouse,
            product=self.product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=50,
            unit_cost=Decimal("100.00"),
        )
        self.quotation = create_quotation(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 4}],
        )
        transition_quotation(actor=self.manager, quotation=self.quotation, to_status=Quotation.Status.SENT)
        self.quotation.refresh_from_db()
        transition_quotation(actor=self.manager, quotation=self.quotation, to_status=Quotation.Status.ACCEPTED)
        self.quotation.refresh_from_db()
        self.order = convert_quotation_to_order(actor=self.manager, quotation=self.quotation)
        transition_order(actor=self.manager, order=self.order, to_status="confirmed")
        self.order.refresh_from_db()
        self.invoice = convert_order_to_invoice(
            actor=self.manager, order=self.order, warehouse=self.warehouse
        )
        self.invoice = issue_invoice(actor=self.manager, invoice=self.invoice)
        self.payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CASH,
            amount=Decimal("500.00"),
        )


class BillingPageAccessTests(CommercialWorldMixin, TestCase):
    def setUp(self):
        self.build_world()

    def test_manager_reaches_every_page_including_details_and_print(self):
        self.client.force_login(self.manager)
        for path in MANAGER_PAGES:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for path in (
            f"/warehouses/{self.warehouse.pk}/",
            f"/quotations/{self.quotation.pk}/",
            f"/orders/{self.order.pk}/",
            f"/invoices/{self.invoice.pk}/",
            f"/payments/{self.payment.pk}/",
            f"/quotations/{self.quotation.pk}/print/",
            f"/invoices/{self.invoice.pk}/print/",
        ):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_printed_invoice_shows_the_stored_snapshot_not_a_blank_form(self):
        self.client.force_login(self.manager)
        response = self.client.get(f"/invoices/{self.invoice.pk}/print/")
        content = response.content.decode("utf-8")
        self.assertIn(self.invoice.number, content)
        self.assertIn("مشتری آزمون", content)
        self.assertIn("SHELL-1", content)
        self.assertIn(str(self.invoice.total_amount), content)
        # The print page carries no navigation and no editing control.
        self.assertNotIn('id="app-sidebar"', content)
        self.assertNotIn("data-close-dialog", content)

    def test_agent_prepares_documents_and_is_refused_every_money_page(self):
        self.client.force_login(self.agent)
        for path in AGENT_ALLOWED_PAGES:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for path in AGENT_FORBIDDEN_PAGES:
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_agent_navigation_offers_no_money_link(self):
        self.client.force_login(self.agent)
        content = self.client.get("/").content.decode("utf-8")
        self.assertIn('href="/quotations/"', content)
        for href in ('href="/payments/"', 'href="/cheques/"', 'href="/reports/receivables/"'):
            self.assertNotIn(href, content)


class BillingScopeTests(CommercialWorldMixin, TestCase):
    def setUp(self):
        self.build_world()

    def test_one_agent_cannot_read_another_agents_document_by_direct_id(self):
        own = create_quotation(
            actor=self.agent,
            customer=create_customer_with_phone(
                actor=self.agent,
                full_name="مشتری بازاریاب",
                phone={"raw_phone": "09121110001", "is_primary": True},
            ),
            items=[{"product": self.product, "quantity": 1}],
        )
        self.client.force_login(self.other_agent)
        self.assertEqual(self.client.get(f"/quotations/{own.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/quotations/{own.pk}/").status_code, 404)
        listing = self.client.get("/api/v1/quotations/").json()
        self.assertEqual(listing["count"], 0)

    def test_agent_is_refused_the_payment_and_ledger_apis_outright(self):
        self.client.force_login(self.agent)
        for path in ("/api/v1/payments/", "/api/v1/cheques/", "/api/v1/customer-ledger/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        for path in ("/api/v1/reports/receivables/", "/api/v1/reports/stock-valuation/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_agent_may_read_stock_and_may_not_move_it(self):
        self.client.force_login(self.agent)
        self.assertEqual(self.client.get("/api/v1/stock-items/").status_code, 200)
        response = self.client.post(
            "/api/v1/stock-movements/",
            data={
                "warehouse": self.warehouse.pk,
                "product": self.product.pk,
                "movement_type": "adjustment_in",
                "quantity": 5,
                "unit_cost": "10.00",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class BillingFeatureGateTests(CommercialWorldMixin, TestCase):
    """A feature this deployment does not run is absent, not merely hidden."""

    def setUp(self):
        self.build_world()

    @staticmethod
    def without(*names):
        return DeploymentProfile(
            profile_id="client-1",
            features=frozenset(ALL_FEATURES) - frozenset(names),
            source="signed-manifest",
        )

    def test_disabled_billing_answers_404_on_page_and_api_alike(self):
        self.client.force_login(self.manager)
        with override_active_profile(self.without("invoices", "payments")):
            for path in (
                "/invoices/",
                f"/invoices/{self.invoice.pk}/",
                f"/invoices/{self.invoice.pk}/print/",
                "/payments/",
                "/api/v1/invoices/",
                "/api/v1/payments/",
                "/api/v1/reports/receivables/",
            ):
                self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_disabling_a_feature_deletes_no_row_and_restores_on_re_enable(self):
        before = Invoice.objects.count()
        self.client.force_login(self.manager)
        with override_active_profile(self.without("invoices")):
            self.assertEqual(self.client.get("/api/v1/invoices/").status_code, 404)
        self.assertEqual(Invoice.objects.count(), before)
        self.assertEqual(self.client.get("/api/v1/invoices/").json()["count"], before)

    def test_disabled_inventory_hides_its_navigation_group(self):
        self.client.force_login(self.manager)
        with override_active_profile(self.without("inventory")):
            content = self.client.get("/").content.decode("utf-8")
            self.assertNotIn('href="/stock/"', content)
            self.assertNotIn('href="/warehouses/"', content)


class FinancialReportShellTests(CommercialWorldMixin, TestCase):
    def setUp(self):
        self.build_world()
        self.client.force_login(self.manager)

    def test_receivables_report_and_export_agree(self):
        report = self.client.get("/api/v1/reports/receivables/").json()
        self.assertEqual(report["total_outstanding"], str(self.invoice.total_amount))
        self.assertEqual(report["results"][0]["customer_id"], self.customer.pk)
        export = self.client.get("/api/v1/exports/receivables.xlsx")
        self.assertEqual(export.status_code, 200)
        self.assertIn("spreadsheetml", export["Content-Type"])
        self.assertIn("forooshbin-receivables.xlsx", export["Content-Disposition"])

    def test_profit_report_sources_cost_from_the_issue_time_snapshot(self):
        now = timezone.now()
        query = {
            "period_start": (now - timedelta(days=1)).isoformat(),
            "period_end": (now + timedelta(days=1)).isoformat(),
        }
        report = self.client.get("/api/v1/reports/profit/", query).json()
        # 4 units sold at 250 against a 100 opening cost.
        self.assertEqual(report["revenue"], "1000.00")
        self.assertEqual(report["cost"], "400.00")
        self.assertEqual(report["profit"], "600.00")
        self.assertEqual(report["measured_invoice_count"], 1)
        self.assertEqual(report["unmeasured_invoice_count"], 0)

    def test_an_invoice_issued_without_a_warehouse_is_reported_unmeasured_not_free(self):
        from billing.services import create_invoice

        invoice = create_invoice(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": self.product, "quantity": 1}],
        )
        issue_invoice(actor=self.manager, invoice=invoice)
        now = timezone.now()
        report = self.client.get(
            "/api/v1/reports/profit/",
            {
                "period_start": (now - timedelta(days=1)).isoformat(),
                "period_end": (now + timedelta(days=1)).isoformat(),
            },
        ).json()
        self.assertEqual(report["unmeasured_invoice_count"], 1)
        self.assertEqual(report["measured_invoice_count"], 1)
        # The unmeasured invoice contributes nothing to either side, so profit
        # is not overstated by treating an unknown cost as zero.
        self.assertEqual(report["revenue"], "1000.00")
        self.assertEqual(report["profit"], "600.00")

    def test_stock_valuation_matches_quantity_times_average_cost(self):
        report = self.client.get("/api/v1/reports/stock-valuation/").json()
        self.assertEqual(report["total_quantity"], 46)
        self.assertEqual(report["total_value"], "4600.00")

    def test_customer_ledger_balance_endpoint_matches_the_last_entry(self):
        balance = self.client.get(
            "/api/v1/customer-ledger/balance/", {"customer": self.customer.pk}
        ).json()
        self.assertEqual(balance["balance"], "500.00")
        entries = self.client.get(
            "/api/v1/customer-ledger/", {"customer": self.customer.pk}
        ).json()
        self.assertEqual(entries["results"][0]["balance_after"], "500.00")

    def test_opening_balance_is_accepted_once_per_customer(self):
        payload = {"customer": self.customer.pk, "amount": "250.00"}
        first = self.client.post(
            "/api/v1/customer-ledger/opening-balance/", data=payload, content_type="application/json"
        )
        self.assertEqual(first.status_code, 201)
        second = self.client.post(
            "/api/v1/customer-ledger/opening-balance/", data=payload, content_type="application/json"
        )
        self.assertEqual(second.status_code, 409)


class InstallmentShellTests(CommercialWorldMixin, TestCase):
    def setUp(self):
        self.build_world()
        self.client.force_login(self.manager)

    def test_a_plan_sums_to_the_invoice_and_absorbs_rounding_on_the_first_row(self):
        response = self.client.post(
            "/api/v1/installment-plans/",
            data={
                "invoice": self.invoice.pk,
                "installment_count": 3,
                "start_date": date(2026, 9, 1).isoformat(),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        plan = response.json()
        amounts = [Decimal(item["amount"]) for item in plan["installments"]]
        self.assertEqual(sum(amounts), self.invoice.total_amount)
        self.assertGreaterEqual(amounts[0], amounts[1])
