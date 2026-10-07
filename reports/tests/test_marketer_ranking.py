"""Marketers ranked side by side (2.40.34, `reports.marketers`)."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.services import create_invoice, issue_invoice
from reports.marketers import build_marketer_ranking
from reports.services import ReportAccessDenied
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-274!"


class RankingTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mr.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.first = User.objects.create_user(username="mr.first", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.second = User.objects.create_user(username="mr.second", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.idle = User.objects.create_user(username="mr.idle", password=PASSWORD, role=User.Role.SALES_AGENT)
        User.objects.create_user(username="mr.after", password=PASSWORD, role=User.Role.SALES_AGENT,
                                 workstream=User.Workstream.AFTER_SALES)
        self.product = create_product(actor=self.manager, sku="MR-1", name="کالا", current_price=Decimal("100.00"))
        self.sell(self.first, "09121110201", 5)
        self.sell(self.first, "09121110202", 1)
        self.sell(self.second, "09121110203", 3)

    def sell(self, agent, phone, quantity):
        customer = create_customer_with_phone(actor=agent, full_name=f"مشتری {phone}", phone={"raw_phone": phone})
        invoice = create_invoice(actor=agent, customer=customer, items=[
            {"product": self.product, "quantity": quantity, "unit_price": self.product.current_price},
        ])
        issue_invoice(actor=self.manager, invoice=invoice)

    def window(self):
        now = timezone.now()
        return {"period_start": now - timedelta(days=1), "period_end": now + timedelta(minutes=1)}

    def test_marketers_are_ranked_by_what_they_sold(self):
        report = build_marketer_ranking(actor=self.manager, **self.window())
        rows = {row.name: row for row in report["results"]}
        self.assertEqual([row.name for row in report["results"]][:2], ["mr.first", "mr.second"])
        self.assertEqual(rows["mr.first"].sales_count, 2)
        self.assertEqual(rows["mr.first"].customers_count, 2)
        self.assertEqual(rows["mr.idle"].rank, 3)
        self.assertNotIn("mr.after", rows)  # after-sales is not marketing
        self.assertEqual(report["totals"]["sales_count"], 3)
        self.assertEqual(sum(row.share for row in report["results"]), Decimal("100.0"))

    def test_another_figure_reorders_and_equals_share_a_place(self):
        report = build_marketer_ranking(actor=self.manager, ordering="calls_count", **self.window())
        self.assertEqual({row.rank for row in report["results"]}, {1})

    def test_only_company_reports_may_see_it(self):
        with self.assertRaises(ReportAccessDenied):
            build_marketer_ranking(actor=self.first, **self.window())
        client = APIClient()
        client.force_login(self.first)
        window = {key: value.isoformat() for key, value in self.window().items()}
        self.assertEqual(client.get("/api/v1/reports/marketers/", window).status_code, 403)
        client.force_login(self.manager)
        response = client.get("/api/v1/reports/marketers/", window)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["results"][0]["name"], "mr.first")
        self.assertEqual(client.get("/reports/marketers/").status_code, 200)
