"""«فروش‌های شرکت» counts issued invoices, not the retired Sale rows (2.39.16)."""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from billing.services import create_invoice, issue_invoice
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-937!"


class InvoiceSalesTileTests(TestCase):
    def test_the_company_sales_tile_counts_issued_invoices_and_links_to_them(self):
        manager = User.objects.create_user(username="tile.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        product = create_product(actor=manager, sku="TL-1", name="کالا", current_price=Decimal("100.00"))
        customer = create_customer_with_phone(actor=manager, full_name="خریدار", phone={"raw_phone": "09121110090"})
        draft = create_invoice(
            actor=manager, customer=customer,
            items=[{"product": product, "quantity": 1, "unit_price": product.current_price}],
        )
        issue_invoice(actor=manager, invoice=draft)
        self.client.force_login(manager)
        page = self.client.get("/")
        tiles = [w for w in page.context["dashboard_widgets"] if w["capability"] == "sales.company"]
        self.assertEqual(len(tiles), 1)
        self.assertEqual(tiles[0]["value"], 1)
        self.assertEqual(tiles[0]["url_name"], "common_ui:invoices")


class InvoiceSalesKpiTests(TestCase):
    def test_this_months_sales_kpis_read_issued_invoices(self):
        from common import dashboard

        manager = User.objects.create_user(username="kpi.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER)
        product = create_product(actor=manager, sku="KP-1", name="کالا", current_price=Decimal("3000000.00"))
        customer = create_customer_with_phone(actor=manager, full_name="خریدار", phone={"raw_phone": "09121110091"})
        for _ in range(2):
            issue_invoice(actor=manager, invoice=create_invoice(
                actor=manager, customer=customer,
                items=[{"product": product, "quantity": 1, "unit_price": product.current_price}],
            ))
        kpis = {kpi["key"]: kpi for kpi in dashboard.dashboard_for(manager)["kpis"]}
        self.assertEqual(kpis["sales_count_this_month"]["display"], "۲")
        self.assertEqual(kpis["sales_amount_this_month"]["url"], "/invoices/")
