"""The seller profile's trend chart, and the scope it must never exceed.

Mirrors `test_customer_insights.py`: the load-bearing assertion is that the
bucketing is correct and that `user_id` never lets a caller sum sales outside
`users_for_performance_report`'s scope for them — a Sales Agent gets only
their own row, an elevated role gets any seller in the company.
"""

from datetime import UTC, datetime
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from reports.sales_insights import (
    InvalidReportPeriod,
    InvalidReportUser,
    build_sales_growth_report,
)
from sales.models import Customer, Lead, Product, Sale


PASSWORD = "Strong-pass-937!"


class SalesGrowthReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="sg.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="sg.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.other_agent = User.objects.create_user(
            username="sg.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales_agent = User.objects.create_user(
            username="sg.aftersales",
            password=PASSWORD,
            role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        self.product = Product.objects.create(
            sku="SG-A", name="Growth product", current_price=Decimal("100.00"),
            created_by=self.manager, updated_by=self.manager,
        )
        self.customer = Customer.objects.create(full_name="مشتری رشد", created_by=self.manager)

    def _sale(self, user, amount, sold_at, *, status=Sale.Status.CONFIRMED):
        lead = Lead.objects.create(customer=self.customer, created_by=user)
        return Sale.objects.create(
            lead=lead, customer=self.customer, sold_by=user, product=self.product,
            quantity=1, unit_price_snapshot=amount, total_amount=amount,
            status=status, sold_at=sold_at,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    # --- bucketing -----------------------------------------------------------

    def test_confirmed_sales_are_summed_per_month(self):
        self._sale(self.agent, Decimal("100.00"), datetime(2026, 1, 5, tzinfo=UTC))
        self._sale(self.agent, Decimal("50.00"), datetime(2026, 1, 20, tzinfo=UTC))
        self._sale(self.agent, Decimal("30.00"), datetime(2026, 3, 1, tzinfo=UTC))
        report = build_sales_growth_report(
            actor=self.agent,
            user_id=self.agent.pk,
            granularity="month",
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period_end=datetime(2026, 4, 1, tzinfo=UTC),
        )
        buckets = {row["bucket"]: row for row in report["results"]}
        self.assertEqual(buckets["2026-01-01"]["sales_count"], 2)
        self.assertEqual(buckets["2026-01-01"]["sales_amount"], Decimal("150.00"))
        # February had nothing, and is still emitted at zero — a line drawn
        # straight from January to March would lie about the slope.
        self.assertEqual(buckets["2026-02-01"]["sales_count"], 0)
        self.assertEqual(buckets["2026-02-01"]["sales_amount"], Decimal("0.00"))
        self.assertEqual(buckets["2026-03-01"]["sales_count"], 1)

    def test_a_cancelled_sale_is_not_a_result(self):
        self._sale(self.agent, Decimal("900.00"), datetime(2026, 1, 5, tzinfo=UTC), status=Sale.Status.CANCELLED)
        report = build_sales_growth_report(actor=self.agent, user_id=self.agent.pk)
        self.assertEqual(report["results"], [])

    def test_an_empty_scope_returns_no_buckets_rather_than_erroring(self):
        report = build_sales_growth_report(actor=self.agent, user_id=self.agent.pk)
        self.assertEqual(report["results"], [])

    def test_an_invalid_granularity_is_refused(self):
        with self.assertRaises(InvalidReportPeriod):
            build_sales_growth_report(actor=self.agent, user_id=self.agent.pk, granularity="year")

    def test_period_end_before_start_is_refused(self):
        with self.assertRaises(InvalidReportPeriod):
            build_sales_growth_report(
                actor=self.agent, user_id=self.agent.pk,
                period_start=datetime(2026, 2, 1, tzinfo=UTC),
                period_end=datetime(2026, 1, 1, tzinfo=UTC),
            )

    # --- scope -----------------------------------------------------------

    def test_an_agent_may_trend_only_themselves(self):
        with self.assertRaises(InvalidReportUser):
            build_sales_growth_report(actor=self.agent, user_id=self.other_agent.pk)

    def test_an_after_sales_agent_has_no_scope_at_all(self):
        with self.assertRaises(InvalidReportUser):
            build_sales_growth_report(actor=self.after_sales_agent, user_id=self.after_sales_agent.pk)

    def test_a_manager_may_trend_any_seller_in_the_company(self):
        self._sale(self.other_agent, Decimal("40.00"), datetime(2026, 1, 5, tzinfo=UTC))
        report = build_sales_growth_report(
            actor=self.manager, user_id=self.other_agent.pk,
            period_start=datetime(2026, 1, 1, tzinfo=UTC), period_end=datetime(2026, 2, 1, tzinfo=UTC),
        )
        self.assertEqual(report["results"][0]["sales_amount"], Decimal("40.00"))

    def test_a_manager_trending_one_seller_never_sums_another(self):
        self._sale(self.agent, Decimal("40.00"), datetime(2026, 1, 5, tzinfo=UTC))
        self._sale(self.other_agent, Decimal("999.00"), datetime(2026, 1, 6, tzinfo=UTC))
        report = build_sales_growth_report(
            actor=self.manager, user_id=self.agent.pk,
            period_start=datetime(2026, 1, 1, tzinfo=UTC), period_end=datetime(2026, 2, 1, tzinfo=UTC),
        )
        self.assertEqual(report["results"][0]["sales_amount"], Decimal("40.00"))

    def test_a_nonexistent_user_id_is_refused(self):
        with self.assertRaises(InvalidReportUser):
            build_sales_growth_report(actor=self.manager, user_id=999999)


class SalesGrowthEndpointTests(TestCase):
    url = "/api/v1/reports/user-performance/trend/"

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="sge.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="sge.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.other_agent = User.objects.create_user(
            username="sge.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_omitting_user_id_defaults_to_the_caller(self):
        response = self.client_for(self.agent).get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], self.agent.pk)

    def test_an_agent_asking_for_another_seller_is_refused(self):
        response = self.client_for(self.agent).get(self.url, {"user_id": self.other_agent.pk})
        self.assertEqual(response.status_code, 400)

    def test_a_manager_may_ask_for_any_seller(self):
        response = self.client_for(self.manager).get(self.url, {"user_id": self.other_agent.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], self.other_agent.pk)

    def test_the_response_never_caches(self):
        response = self.client_for(self.agent).get(self.url)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_a_repeated_query_parameter_is_refused(self):
        response = self.client_for(self.agent).get(f"{self.url}?granularity=week&granularity=month")
        self.assertEqual(response.status_code, 400)
