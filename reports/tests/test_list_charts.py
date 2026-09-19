"""Every chart under a list page, exercised through its real builder.

The registry is eleven entries and one view. The risk that buys is that a
mistake in a single entry — a field name that does not exist, a capability no
role holds, a selector skipped — is invisible until someone opens that one page.
So the first test here runs all eleven, and the second runs all eleven through
the endpoint. Neither names a chart individually, so adding a twelfth is covered
the moment it is declared.
"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.access import ROLE_CAPABILITIES, has_any_capability
from accounts.models import User
from common.deployment.registry import FEATURES
from reports.list_charts import LIST_CHARTS, LIST_TRENDS, TREND_WEEKS, trend_for


PASSWORD = "Strong-pass-937!"


class ListChartRegistryTests(TestCase):
    """Contract checks that need no data at all."""

    def test_every_declared_feature_exists(self):
        for key, (feature, _caps, _builder, _title) in LIST_CHARTS.items():
            with self.subTest(chart=key):
                self.assertIn(feature, FEATURES)

    def test_every_declared_capability_is_held_by_some_role(self):
        """A capability no role holds is a chart nobody can ever open."""
        from accounts.access import AFTER_SALES_AGENT_CAPABILITIES

        known = set(AFTER_SALES_AGENT_CAPABILITIES)
        for capabilities in ROLE_CAPABILITIES.values():
            known |= set(capabilities)
        for key, (_feature, capabilities, _builder, _title) in LIST_CHARTS.items():
            for capability in capabilities:
                with self.subTest(chart=key, capability=capability):
                    self.assertIn(capability, known)

    def test_every_chart_has_a_title(self):
        for key, (_f, _c, _b, title) in LIST_CHARTS.items():
            with self.subTest(chart=key):
                self.assertTrue(title.strip())


class ListChartBuilderTests(TestCase):
    def setUp(self):
        # Throttle buckets are keyed by user id, and rolled-back tests reuse
        # those ids, so without this a test inherits whatever the previous one
        # spent and fails as 429 instead of what it was checking.
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user(
            username="lc.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.manager = User.objects.create_user(
            username="lc.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="lc.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def test_every_builder_runs_against_an_empty_database(self):
        """The query has to be valid before there is anything to aggregate.

        A misspelled field or a bad join raises here rather than on the day a
        deployment first opens that page.
        """
        for key, (_feature, _caps, builder, _title) in LIST_CHARTS.items():
            with self.subTest(chart=key):
                rows = builder(self.manager)
                self.assertIsInstance(rows, list)

    def test_every_builder_returns_the_shape_the_renderer_expects(self):
        for key, (_feature, _caps, builder, _title) in LIST_CHARTS.items():
            with self.subTest(chart=key):
                for row in builder(self.manager):
                    self.assertEqual(set(row), {"label", "value", "display"})
                    self.assertIsInstance(row["label"], str)
                    self.assertIsInstance(row["display"], str)
                    self.assertIsInstance(row["value"], (int, float))

    def test_every_builder_runs_for_a_marketer_too(self):
        """A narrower scope must not turn a working query into an exception."""
        for key, (_feature, _caps, builder, _title) in LIST_CHARTS.items():
            with self.subTest(chart=key):
                self.assertIsInstance(builder(self.agent), list)

    def test_no_label_is_ever_blank(self):
        """A nameless bar tells the reader nothing about what it measures."""
        for key, (_feature, _caps, builder, _title) in LIST_CHARTS.items():
            for row in builder(self.manager):
                with self.subTest(chart=key):
                    self.assertTrue(row["label"].strip())


class ListChartTrendTests(TestCase):
    """The direction chart drawn beside each composition chart (2026-09-19).

    Same risk as the registry above and the same answer: twelve trends, each
    starting from its own module's selector and reading its own dated column,
    and a mistake in one of them is invisible until someone opens that one
    page. So every one of them is run here, and none is named individually.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="lct.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="lct.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def test_every_trend_runs_against_an_empty_database(self):
        """A column name that does not exist raises here, not on the day a
        deployment first opens that page."""
        for key in LIST_TRENDS:
            with self.subTest(trend=key):
                trend = trend_for(key, self.manager)
                self.assertEqual(set(trend), {"title", "points", "summary"})

    def test_every_trend_runs_for_a_marketer_too(self):
        for key in LIST_TRENDS:
            with self.subTest(trend=key):
                self.assertIsNotNone(trend_for(key, self.agent))

    def test_every_trend_returns_one_point_per_week_in_the_shape_the_renderer_reads(self):
        for key in LIST_TRENDS:
            with self.subTest(trend=key):
                points = trend_for(key, self.manager)["points"]
                self.assertEqual(len(points), TREND_WEEKS)
                for point in points:
                    self.assertEqual(set(point), {"label", "value", "display"})
                    self.assertTrue(point["label"].strip())
                    self.assertIsInstance(point["value"], int)

    def test_a_key_with_no_trend_declared_answers_none_rather_than_raising(self):
        """So the panel can render one chart there and two elsewhere without
        its own table of which is which."""
        self.assertIsNone(trend_for("nonsense", self.manager))

    def test_a_row_inside_the_window_lands_in_the_last_bucket(self):
        from sales.models import Lead

        Lead.objects.create(created_by=self.manager, source="trend-now")
        trend = trend_for("leads", self.manager)
        self.assertEqual(trend["points"][-1]["value"], 1)
        self.assertEqual(sum(point["value"] for point in trend["points"]), 1)

    def test_a_row_older_than_the_window_is_not_counted(self):
        from datetime import timedelta

        from sales.models import Lead

        old = Lead.objects.create(created_by=self.manager, source="trend-old")
        # `created_at` is auto_now_add, so it is moved afterwards by update().
        Lead.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(weeks=TREND_WEEKS + 2)
        )
        trend = trend_for("leads", self.manager)
        self.assertEqual(sum(point["value"] for point in trend["points"]), 0)

    def test_a_trend_never_counts_a_row_its_own_chart_could_not_list(self):
        """The scope guarantee, exercised rather than asserted from source: an
        after-sales marketer reads no leads at all, so the leads trend beside
        the leads chart must be empty for them."""
        from sales.models import Lead

        outsider = User.objects.create_user(
            username="lct.after", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        Lead.objects.create(created_by=self.manager, source="trend-scope")
        trend = trend_for("leads", outsider)
        self.assertEqual(sum(point["value"] for point in trend["points"]), 0)

    def test_the_endpoint_sends_the_trend_alongside_the_chart(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        for key, (_feature, capabilities, _builder, _title) in LIST_CHARTS.items():
            if not has_any_capability(self.manager, *capabilities):
                continue
            with self.subTest(chart=key):
                response = client.get(f"/api/v1/reports/list-chart/{key}/")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIn("trend", response.data)
                self.assertEqual(len(response.data["trend"]["points"]), TREND_WEEKS)


class ListChartWithDataTests(TestCase):
    """A few charts checked against rows, to prove they count what they claim."""

    def setUp(self):
        # Throttle buckets are keyed by user id, and rolled-back tests reuse
        # those ids, so without this a test inherits whatever the previous one
        # spent and fails as 429 instead of what it was checking.
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="lcd.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )

    def _customer(self, suffix):
        from sales.services import create_customer_with_phone

        return create_customer_with_phone(
            actor=self.manager,
            full_name=f"مشتری {suffix}",
            phone={"raw_phone": f"0912555{suffix:04d}", "is_primary": True},
        )

    def test_payments_are_summed_by_method_and_exclude_cancellations(self):
        from billing.models import Payment
        from billing.payments import cancel_payment, register_payment

        customer = self._customer(1)
        register_payment(
            actor=self.manager, customer=customer,
            method=Payment.Method.CASH, amount=Decimal("100.00"),
        )
        register_payment(
            actor=self.manager, customer=customer,
            method=Payment.Method.CASH, amount=Decimal("50.00"),
        )
        doomed = register_payment(
            actor=self.manager, customer=customer,
            method=Payment.Method.CARD, amount=Decimal("999.00"),
        )
        cancel_payment(actor=self.manager, payment=doomed, reason="آزمون")

        rows = {row["label"]: row["value"] for row in LIST_CHARTS["payments"][2](self.manager)}
        self.assertEqual(rows.get("نقدی"), 150.0)
        # The cancelled card receipt is money that was taken back.
        self.assertNotIn("کارت", rows)

    def test_amounts_are_formatted_the_way_the_panel_formats_money(self):
        from billing.models import Payment
        from billing.payments import register_payment

        register_payment(
            actor=self.manager, customer=self._customer(2),
            method=Payment.Method.CASH, amount=Decimal("12500000.00"),
        )
        row = LIST_CHARTS["payments"][2](self.manager)[0]
        self.assertEqual(row["display"], "۱۲،۵۰۰،۰۰۰ ریال")

    def test_counts_are_formatted_in_persian_digits(self):
        from sales.services import create_product

        create_product(
            actor=self.manager, sku="LC-1", name="کالا", current_price=Decimal("10.00")
        )
        rows = LIST_CHARTS["products"][2](self.manager)
        self.assertEqual(rows[0]["display"], "۱")


class ListChartEndpointTests(TestCase):
    def setUp(self):
        # Throttle buckets are keyed by user id, and rolled-back tests reuse
        # those ids, so without this a test inherits whatever the previous one
        # spent and fails as 429 instead of what it was checking.
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="lce.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_every_chart_answers_for_a_role_that_holds_its_capability(self):
        for key, (_feature, capabilities, _builder, _title) in LIST_CHARTS.items():
            if not has_any_capability(self.manager, *capabilities):
                continue
            with self.subTest(chart=key):
                response = self.client.get(f"/api/v1/reports/list-chart/{key}/")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["key"], key)
                self.assertIn("results", response.data)

    def test_an_unknown_key_is_not_found(self):
        response = self.client.get("/api/v1/reports/list-chart/nonsense/")
        self.assertEqual(response.status_code, 404)

    def test_a_role_without_the_capability_is_refused(self):
        """The chart is refused, not silently emptied."""
        outsider = User.objects.create_user(
            username="lce.after", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        client = APIClient()
        client.force_authenticate(outsider)
        refused = 0
        for key, (_feature, capabilities, _builder, _title) in LIST_CHARTS.items():
            if has_any_capability(outsider, *capabilities):
                continue
            with self.subTest(chart=key):
                response = client.get(f"/api/v1/reports/list-chart/{key}/")
                self.assertIn(response.status_code, (403, 404))
                refused += 1
        # If this role could reach everything the test would prove nothing.
        self.assertGreater(refused, 0)

    def test_a_disabled_feature_hides_its_chart(self):
        from common.deployment.profile import DeploymentProfile, override_active_profile

        reduced = DeploymentProfile(
            profile_id="client-1",
            features=frozenset(FEATURES) - {"invoices"},
            source="signed-manifest",
        )
        with override_active_profile(reduced):
            response = self.client.get("/api/v1/reports/list-chart/invoices/")
        self.assertEqual(response.status_code, 404)
