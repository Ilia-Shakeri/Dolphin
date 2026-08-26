"""The two customer charts, and the scope they must never exceed.

The aggregations are built on `customers_for`, so the load-bearing assertion
here is that a marketer's chart counts a marketer's book. A chart that
aggregated wider would leak the shape of data its viewer cannot list — a total
is still information about the rows behind it.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from reports.customer_insights import (
    InvalidReportPeriod,
    build_customer_city_report,
    build_customer_growth_report,
)
from sales.models import Customer
from sales.services import create_customer_with_phone


PASSWORD = "Strong-pass-937!"


class CustomerInsightTests(TestCase):
    def setUp(self):
        # Throttle buckets are keyed by user id, and rolled-back tests reuse
        # those ids, so without this a test inherits whatever the previous one
        # spent and fails as 429 instead of what it was checking.
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="ci.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="ci.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.phone = 0

    def add(self, *, actor=None, city="", province="", created_at=None, kind=None):
        self.phone += 1
        customer = create_customer_with_phone(
            actor=actor or self.manager,
            full_name=f"مشتری {self.phone}",
            city=city,
            province=province,
            **({"kind": kind} if kind else {}),
            phone={"raw_phone": f"09121{self.phone:06d}", "is_primary": True},
        )
        if created_at is not None:
            # `created_at` is auto_now_add, so it is set past the service.
            Customer.objects.filter(pk=customer.pk).update(created_at=created_at)
            customer.refresh_from_db()
        return customer

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    # --- city distribution -------------------------------------------------

    def test_cities_are_counted_largest_first(self):
        for _ in range(3):
            self.add(city="تهران")
        self.add(city="شیراز")
        report = build_customer_city_report(actor=self.manager)
        self.assertEqual(report["total"], 4)
        self.assertEqual([row["label"] for row in report["results"]], ["تهران", "شیراز"])
        self.assertEqual(report["results"][0]["count"], 3)

    def test_percentages_are_taken_against_the_visible_total(self):
        self.add(city="تهران")
        self.add(city="شیراز")
        report = build_customer_city_report(actor=self.manager)
        self.assertEqual({row["percent"] for row in report["results"]}, {50.0})

    def test_a_customer_with_no_city_falls_back_to_its_province(self):
        self.add(province="فارس")
        report = build_customer_city_report(actor=self.manager)
        self.assertEqual(report["results"][0]["label"], "فارس")

    def test_a_customer_with_neither_is_reported_not_dropped(self):
        """Dropping them would make every percentage overstate its share."""
        self.add(city="تهران")
        self.add()
        report = build_customer_city_report(actor=self.manager)
        labels = [row["label"] for row in report["results"]]
        self.assertIn("ثبت‌نشده", labels)
        self.assertEqual(sum(row["count"] for row in report["results"]), report["total"])

    def test_the_aggregate_rows_are_marked_as_such(self):
        self.add()
        report = build_customer_city_report(actor=self.manager)
        row = next(r for r in report["results"] if r["label"] == "ثبت‌نشده")
        self.assertTrue(row["is_aggregate"])

    def test_an_empty_book_reports_zero_rather_than_dividing_by_it(self):
        report = build_customer_city_report(actor=self.manager)
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["results"], [])

    # --- growth ------------------------------------------------------------

    def test_growth_counts_registrations_per_bucket(self):
        now = timezone.now()
        self.add(created_at=now - timedelta(days=40))
        self.add(created_at=now - timedelta(days=5))
        self.add(created_at=now - timedelta(days=3))
        report = build_customer_growth_report(actor=self.manager, granularity="month")
        self.assertEqual(sum(row["count"] for row in report["results"]), 3)
        self.assertEqual(report["closing_total"], 3)

    def test_the_cumulative_line_only_rises(self):
        now = timezone.now()
        for days in (300, 200, 100, 10):
            self.add(created_at=now - timedelta(days=days))
        report = build_customer_growth_report(actor=self.manager, granularity="month")
        totals = [row["cumulative"] for row in report["results"]]
        self.assertEqual(totals, sorted(totals))

    def test_an_empty_bucket_is_reported_as_zero_not_skipped(self):
        """A gap would draw one long straight line and misstate the slope."""
        now = timezone.now()
        self.add(created_at=now - timedelta(days=100))
        self.add(created_at=now - timedelta(days=5))
        report = build_customer_growth_report(actor=self.manager, granularity="month")
        counts = [row["count"] for row in report["results"]]
        self.assertIn(0, counts)
        # Consecutive months with no holes between the first and last.
        self.assertGreaterEqual(len(report["results"]), 3)

    def test_the_series_opens_at_what_the_book_already_held(self):
        """Customers older than the window are the starting height of the line."""
        now = timezone.now()
        self.add(created_at=now - timedelta(days=900))
        self.add(created_at=now - timedelta(days=10))
        report = build_customer_growth_report(
            actor=self.manager, granularity="month",
            period_start=now - timedelta(days=60), period_end=now,
        )
        self.assertEqual(report["opening_total"], 1)
        self.assertEqual(report["closing_total"], 2)

    def test_an_unknown_granularity_is_refused(self):
        with self.assertRaises(InvalidReportPeriod):
            build_customer_growth_report(actor=self.manager, granularity="day")

    def test_a_backwards_period_is_refused(self):
        now = timezone.now()
        with self.assertRaises(InvalidReportPeriod):
            build_customer_growth_report(
                actor=self.manager, period_start=now, period_end=now - timedelta(days=1)
            )

    # --- scope, which is the point ----------------------------------------

    def test_a_marketer_counts_only_their_own_customers(self):
        self.add(actor=self.manager, city="تهران")
        self.add(actor=self.manager, city="تهران")
        self.add(actor=self.agent, city="شیراز")

        mine = build_customer_city_report(actor=self.agent)
        self.assertEqual(mine["total"], 1)
        self.assertEqual([row["label"] for row in mine["results"]], ["شیراز"])
        # The manager's two Tehran customers are not merely unlabelled here —
        # they are not counted at all.
        self.assertNotIn("تهران", [row["label"] for row in mine["results"]])

        everyone = build_customer_city_report(actor=self.manager)
        self.assertEqual(everyone["total"], 3)

    def test_a_marketer_growth_series_is_their_own_book(self):
        now = timezone.now()
        self.add(actor=self.manager, created_at=now - timedelta(days=5))
        self.add(actor=self.agent, created_at=now - timedelta(days=5))
        report = build_customer_growth_report(actor=self.agent)
        self.assertEqual(report["closing_total"], 1)

    def test_a_marketer_never_sees_the_legal_book_in_a_chart(self):
        """`customers_for` confines them to the individual book; so must the chart."""
        self.add(actor=self.manager, city="اصفهان", kind=Customer.Kind.LEGAL)
        self.add(actor=self.agent, city="شیراز")
        report = build_customer_city_report(actor=self.agent)
        self.assertNotIn("اصفهان", [row["label"] for row in report["results"]])

    # --- the endpoints -----------------------------------------------------

    def test_both_endpoints_answer_for_a_permitted_role(self):
        self.add(city="تهران")
        client = self.client_for(self.manager)
        for route in ("/api/v1/reports/customer-cities/", "/api/v1/reports/customer-growth/"):
            with self.subTest(route=route):
                self.assertEqual(client.get(route).status_code, 200)

    def test_an_after_sales_agent_is_refused_rather_than_shown_an_empty_chart(self):
        outsider = User.objects.create_user(
            username="ci.after", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        client = self.client_for(outsider)
        for route in ("/api/v1/reports/customer-cities/", "/api/v1/reports/customer-growth/"):
            with self.subTest(route=route):
                self.assertEqual(client.get(route).status_code, 403)

    def test_a_bad_period_is_a_request_error_not_a_server_one(self):
        now = timezone.now()
        response = self.client_for(self.manager).get(
            "/api/v1/reports/customer-growth/",
            {"period_start": now.isoformat(), "period_end": (now - timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.status_code, 400)
