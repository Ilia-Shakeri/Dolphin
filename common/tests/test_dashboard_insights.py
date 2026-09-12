"""The role-specific dashboard panel: `common.dashboard`, its API, the page.

What is worth proving:

* **the panel is assembled from what a reader may see**, never filtered
  afterwards — a marketer gets no receivables KPI at all, and an after-sales
  specialist gets cases rather than leads;
* **the arithmetic** — a month-over-month comparison must measure the same
  span of the previous month, or every dashboard reads as a collapse on the
  3rd; and the receivables figure must honour `is_manually_settled`, which a
  plain `SUM()` over the columns would not;
* **the feature gate** — off means no section on the page and 404 from the
  API;
* **empty is empty** — a deployment with none of the sources renders a page
  that looks exactly as it did before this existed.
"""

import pathlib
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from aftersales.services import create_after_sales_request
from billing.services import create_invoice, issue_invoice
from common import dashboard
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import (
    assign_lead,
    create_customer_with_phone,
    create_lead,
    create_product,
    mark_sale,
)

PASSWORD = "Strong-pass-338!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class DashboardFixtures(TestCase):
    phone_counter = 0

    def setUp(self):
        self.manager = User.objects.create_user(
            username="dash.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="dash.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales = User.objects.create_user(
            username="dash.aftersales", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        self.now = timezone.now()

    def a_customer(self, name="مشتری داشبورد", actor=None):
        DashboardFixtures.phone_counter += 1
        return create_customer_with_phone(
            actor=actor or self.manager, full_name=name,
            phone={"raw_phone": f"0916000{DashboardFixtures.phone_counter:04d}", "is_primary": True},
        )

    def a_sale(self, *, amount, when=None, seller=None):
        seller = seller or self.agent
        lead = create_lead(actor=self.manager, customer=self.a_customer(), source="کمپین داشبورد")
        assign_lead(actor=self.manager, lead=lead, to_user=seller)
        sale = mark_sale(actor=seller, lead=lead, quantity=1, total_amount=Decimal(amount))
        if when is not None:
            sale.sold_at = when
            sale.save(update_fields=["sold_at"])
        return sale

    def kpi(self, data, key):
        return next((item for item in data["kpis"] if item["key"] == key), None)

    def _an_issued_invoice(self, *, customer=None):
        customer = customer or self.a_customer("مشتری فاکتور")
        product = create_product(
            actor=self.manager, sku=f"DASH-{DashboardFixtures.phone_counter}", name="کالای داشبورد",
            current_price=Decimal("1000000.00"),
        )
        warehouse = create_warehouse(
            actor=self.manager, code=f"dashwh{DashboardFixtures.phone_counter}", name="انبار داشبورد",
        )
        record_stock_movement(
            actor=self.manager, warehouse=warehouse, product=product,
            movement_type=StockMovement.MovementType.OPENING, quantity=10, unit_cost=Decimal("500000.00"),
        )
        return issue_invoice(actor=self.manager, invoice=create_invoice(
            actor=self.manager, customer=customer,
            items=[{"product": product, "quantity": 1}], warehouse=warehouse,
        ))


class RoleShapeTests(DashboardFixtures):
    def test_a_manager_gets_sales_figures_and_a_trend(self):
        self.a_sale(amount="10000000.00")
        data = dashboard.dashboard_for(self.manager)
        self.assertIsNotNone(self.kpi(data, "sales_amount_this_month"))
        self.assertIsNotNone(data["trend"])
        self.assertEqual(len(data["trend"]["points"]), dashboard.TREND_WEEKS)

    def test_a_marketer_gets_no_receivables_figure_at_all(self):
        """Not an empty figure — the KPI is simply not part of their panel."""
        self._an_issued_invoice()
        self.a_sale(amount="5000000.00")
        agent_view = dashboard.dashboard_for(self.agent)
        manager_view = dashboard.dashboard_for(self.manager)
        self.assertIsNone(self.kpi(agent_view, "outstanding"))
        self.assertIsNotNone(self.kpi(manager_view, "outstanding"))

    def test_the_after_sales_side_gets_cases_not_leads(self):
        create_after_sales_request(
            actor=self.manager, customer=self.a_customer("مشتری خدمات"), subject="ایراد",
            description="شرح", status="باز", assigned_to=self.after_sales,
        )
        data = dashboard.dashboard_for(self.after_sales)
        self.assertEqual(data["breakdown"]["title"], "پرونده‌ها به تفکیک وضعیت")
        self.assertIsNotNone(self.kpi(data, "after_sales_open"))
        self.assertIsNone(self.kpi(data, "sales_amount_this_month"))

    def test_the_sales_side_gets_leads_not_cases(self):
        lead = create_lead(actor=self.manager, customer=self.a_customer(), source="کمپین")
        assign_lead(actor=self.manager, lead=lead, to_user=self.agent)
        data = dashboard.dashboard_for(self.agent)
        self.assertEqual(data["breakdown"]["title"], "سرنخ‌ها به تفکیک وضعیت")

    def test_a_reader_with_nothing_in_scope_gets_an_empty_panel(self):
        data = dashboard.dashboard_for(self.after_sales)
        self.assertEqual(data["kpis"], [])
        self.assertIsNone(data["trend"])
        self.assertIsNone(data["breakdown"])

    def test_every_kpi_names_a_glyph_the_theme_actually_has(self):
        """A duotone icon needs its own number of `.path` spans, per glyph."""
        import re

        css = (
            pathlib.Path(__file__).resolve().parents[2]
            / "assets" / "plugins" / "global" / "plugins.bundle.css"
        ).read_text(encoding="utf-8", errors="ignore")
        self._an_issued_invoice()
        self.a_sale(amount="1000000.00")
        create_after_sales_request(
            actor=self.manager, customer=self.a_customer("مشتری آیکون"), subject="ایراد",
            description="شرح", status="باز", assigned_to=self.after_sales,
        )
        seen = dashboard.dashboard_for(self.manager)["kpis"] + dashboard.dashboard_for(self.after_sales)["kpis"]
        self.assertTrue(seen)
        for kpi in seen:
            with self.subTest(icon=kpi["icon"]):
                name = kpi["icon"].removeprefix("ki-")
                found = re.findall(rf"\.ki-{re.escape(name)}\s*\.path(\d+)", css)
                self.assertTrue(found, f"{kpi['icon']} is not a duotone icon in this theme")
                self.assertEqual(kpi["icon_paths"], max(int(number) for number in found))


class ArithmeticTests(DashboardFixtures):
    def test_this_month_is_compared_with_the_same_span_of_last_month(self):
        """Otherwise every dashboard reads as a collapse early in the month.

        A whole previous month against three days of this one is not a
        comparison; `_month_bounds` measures the same elapsed span.
        """
        start, previous_start, previous_end = dashboard._month_bounds(self.now)
        self.assertEqual(previous_end - previous_start, self.now - start)
        self.assertEqual(previous_start.day, 1)
        self.assertEqual(start.day, 1)

    def test_the_month_figure_counts_only_this_months_sales(self):
        start, _previous_start, _previous_end = dashboard._month_bounds(self.now)
        self.a_sale(amount="7000000.00")
        self.a_sale(amount="99000000.00", when=start - timedelta(days=1))
        kpi = self.kpi(dashboard.dashboard_for(self.manager), "sales_amount_this_month")
        self.assertIn("۷", kpi["display"])
        self.assertNotIn("۹۹", kpi["display"])

    def test_a_sales_kpi_carries_the_direction_its_own_hint_names(self):
        start, _previous_start, _previous_end = dashboard._month_bounds(self.now)
        self.a_sale(amount="99000000.00", when=start - timedelta(days=1))
        self.a_sale(amount="7000000.00")
        kpi = self.kpi(dashboard.dashboard_for(self.manager), "sales_amount_this_month")
        self.assertIn("کمتر", kpi["hint"])
        self.assertEqual(kpi["direction"], "down")

    def test_a_kpi_with_no_comparison_base_carries_no_direction(self):
        kpi = self.kpi(dashboard.dashboard_for(self.manager), "outstanding")
        self.assertIsNone(kpi["direction"])

    def test_a_cancelled_sale_is_not_counted(self):
        from sales.services import cancel_sale

        sale = self.a_sale(amount="8000000.00")
        before = self.kpi(dashboard.dashboard_for(self.manager), "sales_count_this_month")["display"]
        cancel_sale(actor=self.manager, sale=sale, reason="اشتباه ثبت شد")
        after = dashboard.dashboard_for(self.manager)
        self.assertEqual(before, "۱")
        # The KPI stays and reads zero rather than disappearing: a figure of
        # zero is a fact about the month, and a section that vanishes when
        # business goes quiet would be worse than one that says so. The panel
        # drops a source only when the reader may not *see* it at all.
        self.assertEqual(self.kpi(after, "sales_amount_this_month")["display"], "۰ ریال")
        self.assertEqual(self.kpi(after, "sales_count_this_month")["display"], "۰")

    def test_a_manually_settled_invoice_owes_nothing_in_the_kpi(self):
        """`balance_due` honours the override; a `SUM()` over the stored
        columns would not — `canonical_balance_due` is deliberately untouched
        by a manual settlement, so the two figures disagree by design.

        Settled through the service rather than by writing the column:
        `is_manually_settled` is a read-only property over `manual_settled_at`,
        and the one-way transition belongs to `record_manual_paid_entry`.
        """
        from billing.services import record_manual_paid_entry

        invoice = self._an_issued_invoice()
        before = self.kpi(dashboard.dashboard_for(self.manager), "outstanding")["display"]
        record_manual_paid_entry(
            actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due,
        )
        invoice.refresh_from_db()
        self.assertTrue(invoice.is_manually_settled)
        after = self.kpi(dashboard.dashboard_for(self.manager), "outstanding")["display"]
        self.assertNotEqual(before, after)
        self.assertEqual(after, "۰ ریال")

    def test_the_change_hint_reads_as_a_sentence_in_every_case(self):
        self.assertEqual(dashboard._change_hint(110, 100, noun="ماه"), "۱۰٪ بیشتر از ماه گذشته")
        self.assertEqual(dashboard._change_hint(90, 100, noun="ماه"), "۱۰٪ کمتر از ماه گذشته")
        self.assertEqual(dashboard._change_hint(100, 100, noun="ماه"), "مثل ماه گذشته")
        self.assertEqual(dashboard._change_hint(5, 0, noun="هفته"), "در هفته گذشته چیزی ثبت نشده بود")
        self.assertEqual(dashboard._change_hint(0, 0, noun="هفته"), "در این هفته چیزی ثبت نشده")

    def test_the_change_direction_matches_the_words_the_hint_uses(self):
        """A KPI tile draws an up/down arrow from this — it must never
        disagree with the sentence sitting right next to it (design review,
        2026-09-12: a tile's own hint text was the only place direction
        showed up at all, and reading a full Persian sentence to tell
        "more" from "less" at a glance is exactly what the arrow is for).
        """
        self.assertEqual(dashboard._change_direction(110, 100), "up")
        self.assertEqual(dashboard._change_direction(90, 100), "down")
        self.assertIsNone(dashboard._change_direction(100, 100))
        self.assertIsNone(dashboard._change_direction(5, 0))
        self.assertIsNone(dashboard._change_direction(0, 0))

    def test_the_trend_is_twelve_weeks_ending_this_week(self):
        self.a_sale(amount="3000000.00")
        points = dashboard.dashboard_for(self.manager)["trend"]["points"]
        self.assertEqual(len(points), dashboard.TREND_WEEKS)
        # Money is already formatted for the reader, like every chart label.
        self.assertTrue(all(point["display"].endswith("ریال") for point in points))

    def test_a_sale_older_than_the_window_is_not_in_the_trend(self):
        self.a_sale(amount="50000000.00", when=self.now - timedelta(weeks=30))
        data = dashboard.dashboard_for(self.manager)
        self.assertEqual(sum(point["value"] for point in data["trend"]["points"]), 0)


class GaugeTests(DashboardFixtures):
    """The three radial-gauge figures (2026-09-11): each a real ratio over a
    module's own scoped data, never a stored/invented target."""

    def gauge(self, data, key):
        return next((item for item in data["gauges"] if item["key"] == key), None)

    def test_lead_conversion_counts_only_decided_leads(self):
        from sales.models import Lead
        from sales.services import update_lead

        customer = self.a_customer()
        completed = create_lead(actor=self.manager, customer=customer, source="کمپین گیج")
        update_lead(actor=self.manager, lead=completed, status=Lead.Status.COMPLETED)
        cancelled = create_lead(actor=self.manager, customer=customer, source="کمپین گیج")
        update_lead(actor=self.manager, lead=cancelled, status=Lead.Status.CANCELLED)
        # A pending lead has not been decided yet; it must not water down the
        # rate as though it were a loss.
        create_lead(actor=self.manager, customer=customer, source="کمپین گیج")

        gauge = self.gauge(dashboard.dashboard_for(self.manager), "lead_conversion_rate")
        self.assertEqual(gauge["value"], 50.0)
        self.assertEqual(gauge["display"], "۵۰٪")

    def test_no_decided_lead_means_no_gauge_rather_than_a_division_by_zero(self):
        create_lead(actor=self.manager, customer=self.a_customer(), source="کمپین گیج")
        gauge = self.gauge(dashboard.dashboard_for(self.manager), "lead_conversion_rate")
        self.assertIsNone(gauge)

    def test_receivables_collection_rate_reflects_what_is_actually_still_owed(self):
        from billing.services import record_manual_paid_entry

        invoice = self._an_issued_invoice()
        before = self.gauge(dashboard.dashboard_for(self.manager), "receivables_collection_rate")
        self.assertEqual(before["value"], 0.0)

        record_manual_paid_entry(actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due)
        after = self.gauge(dashboard.dashboard_for(self.manager), "receivables_collection_rate")
        self.assertEqual(after["value"], 100.0)

    def test_after_sales_closure_rate_counts_closed_over_all_cases(self):
        from aftersales.services import close_after_sales_request

        customer = self.a_customer()
        open_case = create_after_sales_request(
            actor=self.manager, customer=customer, subject="مورد باز", description="د", status="در بررسی",
        )
        closing = create_after_sales_request(
            actor=self.manager, customer=customer, subject="مورد بسته", description="د", status="در بررسی",
        )
        close_after_sales_request(actor=self.manager, request=closing, reason="حل شد")

        gauge = self.gauge(dashboard.dashboard_for(self.manager), "after_sales_closure_rate")
        self.assertEqual(gauge["value"], 50.0)
        del open_case  # kept only to make the fixture's shape explicit

    def test_a_gauge_never_fabricates_a_stored_target(self):
        """No sales-quota gauge exists, because no target is stored anywhere
        in this codebase — see `_gauges`'s own docstring. This pins that
        absence so a future change does not quietly invent one."""
        self.a_sale(amount="1000000.00")
        data = dashboard.dashboard_for(self.manager)
        keys = {gauge["key"] for gauge in data["gauges"]}
        self.assertEqual(
            keys - {"lead_conversion_rate", "receivables_collection_rate", "after_sales_closure_rate"},
            set(),
        )


class SparkAndShareTests(DashboardFixtures):
    """The mixed trend, the KPI sparklines that ride on it, and the
    per-seller share gauge (2026-09-11) — the "colourful and eye-catching"
    round."""

    def test_the_trend_carries_a_count_bucket_alongside_every_amount_bucket(self):
        self.a_sale(amount="3000000.00")
        self.a_sale(amount="4000000.00")
        trend = dashboard.dashboard_for(self.manager)["trend"]
        self.assertEqual(len(trend["counts"]), len(trend["points"]))
        self.assertEqual(sum(trend["counts"]), 2)

    def test_the_sales_kpis_carry_a_spark_the_same_length_as_the_configured_window(self):
        self.a_sale(amount="5000000.00")
        data = dashboard.dashboard_for(self.manager)
        amount_kpi = self.kpi(data, "sales_amount_this_month")
        count_kpi = self.kpi(data, "sales_count_this_month")
        self.assertEqual(len(amount_kpi["spark"]), dashboard.SPARK_WEEKS)
        self.assertEqual(len(count_kpi["spark"]), dashboard.SPARK_WEEKS)
        # This week's own bucket is the spark's last point — the same bucket
        # the trend chart's own last point reads.
        self.assertEqual(count_kpi["spark"][-1], 1)

    def test_a_kpi_with_no_cheap_series_carries_no_spark(self):
        self._an_issued_invoice()
        data = dashboard.dashboard_for(self.manager)
        self.assertIsNone(self.kpi(data, "outstanding")["spark"])

    def test_a_lone_sellers_scope_gets_no_share_gauge(self):
        """One seller's share of their own sales is always 100% — a fact a
        gauge draws nothing useful about. `sales_for` scopes a plain agent to
        only their own rows, so this is also the ordinary agent view."""
        self.a_sale(amount="1000000.00", seller=self.agent)
        data = dashboard.dashboard_for(self.agent)
        self.assertIsNone(data["agent_share"])

    def test_two_sellers_split_the_gauge_by_their_real_share(self):
        self.a_sale(amount="3000000.00", seller=self.agent)
        second = User.objects.create_user(
            username="dash.agent2", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.a_sale(amount="1000000.00", seller=second)
        share = dashboard.dashboard_for(self.manager)["agent_share"]
        by_share = {item["label"]: item["value"] for item in share["items"]}
        self.assertEqual(sum(round(v) for v in by_share.values()), 100)
        self.assertEqual(max(by_share.values()), 75.0)

    def test_a_cancelled_sale_does_not_count_toward_anyones_share(self):
        from sales.services import cancel_sale

        sale = self.a_sale(amount="2000000.00", seller=self.agent)
        second = User.objects.create_user(
            username="dash.agent3", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.a_sale(amount="2000000.00", seller=second)
        cancel_sale(actor=self.manager, sale=sale, reason="اشتباه ثبت شد")
        share = dashboard.dashboard_for(self.manager)["agent_share"]
        # Only `second` has a real, un-cancelled sale left — back to a lone
        # seller, so the gauge is withdrawn rather than shown with one ring.
        self.assertIsNone(share)

    def test_more_than_the_shown_limit_of_sellers_folds_into_one_remainder_ring(self):
        sellers = [
            User.objects.create_user(username=f"dash.bulk{i}", password=PASSWORD, role=User.Role.SALES_AGENT)
            for i in range(dashboard.TOP_SELLERS + 2)
        ]
        for seller in sellers:
            self.a_sale(amount="1000000.00", seller=seller)
        share = dashboard.dashboard_for(self.manager)["agent_share"]
        # TOP_SELLERS named individually, plus exactly one "N دیگر" ring.
        self.assertEqual(len(share["items"]), dashboard.TOP_SELLERS + 1)
        self.assertIn("۲ بازاریاب دیگر", share["items"][-1]["label"])


class FeatureGateTests(DashboardFixtures):
    def test_the_api_is_404_when_the_feature_is_off(self):
        api = APIClient()
        api.force_authenticate(self.manager)
        with override_active_profile(profile_without("dashboard_insights")):
            self.assertEqual(api.get("/api/v1/dashboard/").status_code, 404)

    def test_the_section_is_absent_from_the_page_when_the_feature_is_off(self):
        self.client.force_login(self.manager)
        with override_active_profile(profile_without("dashboard_insights")):
            page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('id="dashboard-insights"', page)

    def test_the_section_is_on_the_page_by_default(self):
        self.client.force_login(self.manager)
        self.assertIn('id="dashboard-insights"', self.client.get("/").content.decode("utf-8"))

    def test_a_deployment_without_sales_keeps_the_rest_of_the_panel(self):
        lead = create_lead(actor=self.manager, customer=self.a_customer(), source="کمپین")
        assign_lead(actor=self.manager, lead=lead, to_user=self.agent)
        self.a_sale(amount="1000000.00")
        with override_active_profile(profile_without("sales")):
            data = dashboard.dashboard_for(self.manager)
        self.assertIsNone(data["trend"])
        self.assertIsNone(self.kpi(data, "sales_amount_this_month"))
        self.assertIsNotNone(data["breakdown"])

    def test_dashboard_insights_is_on_by_default(self):
        from common.deployment.registry import DEFAULT_FEATURES, DEFAULT_OFF_FEATURES

        self.assertIn("dashboard_insights", DEFAULT_FEATURES)
        self.assertNotIn("dashboard_insights", DEFAULT_OFF_FEATURES)


class ApiTests(DashboardFixtures):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.manager)

    def test_the_endpoint_returns_the_five_parts(self):
        self.a_sale(amount="2000000.00")
        response = self.api.get("/api/v1/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"kpis", "trend", "breakdown", "gauges", "agent_share"})

    def test_the_result_may_not_be_cached(self):
        self.assertEqual(self.api.get("/api/v1/dashboard/")["Cache-Control"], "private, no-store")

    def test_an_anonymous_caller_is_refused(self):
        self.assertIn(APIClient().get("/api/v1/dashboard/").status_code, (401, 403))

    def test_the_endpoint_is_not_rate_limited(self):
        from common.dashboard_views import DashboardView
        from common.throttles import SensitiveRateThrottle

        self.assertFalse(
            [t for t in DashboardView().get_throttles() if isinstance(t, SensitiveRateThrottle)]
        )


class ColourfulPaletteTests(SimpleTestCase):
    """`dark` used to be a real accent on the dashboard's capability tiles and
    the last colour in every chart's palette. On this panel's own dark theme
    `--bs-dark` sits only a few shades off the card background it draws on,
    so both were effectively invisible — the concrete half of the
    product-owner's "رنگی و جذاب" request (2026-09-11), not just the new
    widgets."""

    def test_no_capability_tile_accent_is_the_invisible_dark_one(self):
        from common.ui_views import DEFAULT_WIDGET_STYLE, WIDGET_STYLE

        for module, style in {**WIDGET_STYLE, "__default__": DEFAULT_WIDGET_STYLE}.items():
            with self.subTest(module=module):
                self.assertNotEqual(style["accent"], "dark")

    def test_the_chart_palettes_own_last_colour_is_not_the_invisible_dark_one(self):
        script = (
            pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
        ).read_text(encoding="utf-8")
        start = script.index("function chartPalette()")
        end = script.index("\n    }", start)
        body = script[start:end]
        self.assertNotIn('read("--bs-dark"', body)
        self.assertIn('read("--bs-orange"', body)


class ChartOverlapFixTests(SimpleTestCase):
    """Three chart-legibility bugs found in a design review of the live
    panel (2026-09-12), each a value overlapping or vanishing into the
    chart drawing it was supposed to sit on:

    * the trend chart's own "تعداد فروش" bars rendered with the area
      series' fade-to-transparent gradient instead of a solid fill —
      measured live as a near-invisible smudge;
    * that same chart's twelve rotated date labels all overlapped their
      neighbour, because Apex's own tickAmount/hideOverlappingLabels do
      not account for rotated text;
    * the per-seller share gauge's centre "مجموع" total spilled outside
      its own hollow and onto the innermost ring, measured live as a
      19.5px-radius hollow holding a 58px-tall two-line label.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = (
            pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
        ).read_text(encoding="utf-8")

    def _function_body(self, name):
        start = self.script.index(f"function {name}(")
        # Every function this test reads is closed by a `\n    }` at its own
        # nesting depth, exactly like `ColourfulPaletteTests` above already
        # relies on for `chartPalette`.
        end = self.script.index("\n    }", start)
        return self.script[start:end]

    def test_the_mixed_charts_bar_series_is_forced_solid_after_every_render(self):
        body = self._function_body("renderMixedChart")
        self.assertIn("forceSolidBars", body)
        self.assertIn(".apexcharts-bar-series path", body)
        self.assertIn('setAttribute("fill", countColor)', body)
        self.assertIn("mounted:", body)
        self.assertIn("updated:", body)

    def test_both_time_series_charts_thin_their_own_axis_labels(self):
        for name in ("renderAreaChart", "renderMixedChart"):
            with self.subTest(chart=name):
                self.assertIn("thinningFormatter(", self._function_body(name))

    def test_the_multi_gauges_hollow_is_wide_enough_for_its_own_total_label(self):
        body = self._function_body("renderMultiGaugeChart")
        self.assertNotIn('hollow: {size: "18%"}', body)
        self.assertIn('hollow: {size: "34%"}', body)


class KpiDirectionArrowTests(SimpleTestCase):
    """A KPI tile's own hint used to be a plain sentence — "۱۰٪ کمتر از
    ماه گذشته" — with no arrow or colour, so telling an increase from a
    decrease meant reading the whole thing (design review, 2026-09-12).
    `kpiCard` now draws a themed up/down arrow when the backend actually
    computed a direction, and leaves the plain sentence alone otherwise."""

    script = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
    ).read_text(encoding="utf-8")

    def test_the_kpi_card_draws_a_themed_arrow_for_a_real_direction(self):
        start = self.script.index("function kpiCard(kpi)")
        end = self.script.index("\n    function ", start + 1)
        body = self.script[start:end]
        self.assertIn('kpi.direction === "up"', body)
        self.assertIn('ki-arrow-${isUp ? "up" : "down"}', body)
        self.assertIn('text-${isUp ? "success" : "danger"}', body)


class SharedFormattingTests(SimpleTestCase):
    """The grouped-rial rule has one Python home, not one per consumer."""

    def test_the_chart_module_reads_the_shared_formatters(self):
        from common import formatting
        from reports import list_charts

        self.assertIs(list_charts._money, formatting.money)
        self.assertIs(list_charts._persian_digits, formatting.persian_digits)

    def test_money_matches_what_the_panel_prints(self):
        from common import formatting
        from common.templatetags.money_tags import money as template_money

        self.assertEqual(formatting.money(Decimal("12500000.00")), "۱۲،۵۰۰،۰۰۰ ریال")
        # The template filter groups the same way; only its Latin digits and
        # its own missing-value dash differ, which is why the two coexist.
        self.assertIn("۱۲", formatting.money(Decimal("12500000.00")))
        self.assertTrue(str(template_money(Decimal("12500000.00"))).endswith("ریال"))


class MarkupCollisionTests(SimpleTestCase):
    """The KPI cards must not reuse an attribute this page already means.

    `performance_panel.inc` — rendered on the same dashboard — has owned
    `data-kpi` for its own four figures since before this section existed.
    A shared attribute made `[data-kpi]` return ten elements with two
    different meanings, which was harmless on screen and a trap in every
    query written afterwards.
    """

    script = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
    ).read_text(encoding="utf-8")

    def test_the_dashboard_cards_use_their_own_attribute(self):
        self.assertIn("card.dataset.dashboardKpi = kpi.key;", self.script)

    def test_the_performance_panel_keeps_data_kpi_to_itself(self):
        panel = (
            pathlib.Path(__file__).resolve().parents[2]
            / "common" / "templates" / "common" / "includes" / "performance_panel.inc"
        ).read_text(encoding="utf-8")
        self.assertIn('data-kpi="sales_amount"', panel)
        self.assertNotIn("data-dashboard-kpi", panel)


class PerformancePanelSubmitButtonTests(SimpleTestCase):
    """The panel's own submit button moved out of `<form>`; the script that
    disables it during a fetch has to look for it the same way the browser
    does.

    `performance_panel.inc` moved «به‌روزرسانی» out of the filter `<form>`
    and into the panel's header (2026-09-08, "بالا سمت چپ باکس"), keeping it
    wired only through its own `form="..."` HTML attribute — a real submit
    button that is a *sibling* of the form it submits, not a descendant.
    `setupPerformancePanel()` still looked it up with
    `form.querySelector("button[type='submit']")`, which searches
    descendants only, so it always found nothing: every load of this panel
    (dashboard, the dedicated performance report, the profile page) threw
    `Cannot set properties of null` before the fetch it was guarding even
    started, and the panel never populated. Caught live, not by any
    existing test — none of this file's or `test_sales_shell.py`'s browser
    checks happened to load a page carrying this exact panel and then wait
    long enough to notice the report never arrived.
    """

    script = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
    ).read_text(encoding="utf-8")
    panel = (
        pathlib.Path(__file__).resolve().parents[2]
        / "common" / "templates" / "common" / "includes" / "performance_panel.inc"
    ).read_text(encoding="utf-8")

    def test_the_button_is_a_sibling_of_the_form_not_a_descendant(self):
        """Guards the fixture this test class exists for: if the button ever
        moved back inside `<form>`, the fix below would go untested."""
        before_form, _, after_form_open = self.panel.partition('<form id="{{ panel_prefix }}-performance-filter-form"')
        self.assertIn('type="submit" form="{{ panel_prefix }}-performance-filter-form"', before_form)

    def test_the_script_finds_it_through_the_form_attribute_not_a_form_query(self):
        """The same `form.querySelector("button[type='submit']")` shape is
        valid and unrelated elsewhere in this file, for forms whose button
        really is a descendant — the check below is scoped to this one
        function, not the whole script."""
        start = self.script.index("async function setupPerformancePanel(")
        end = self.script.index("\n    async function setupUserPerformance(", start)
        body = self.script[start:end]
        self.assertIn(
            'document.querySelector(`button[type="submit"][form="${form.id}"]`)', body
        )
        self.assertNotIn('form.querySelector("button[type=\'submit\']")', body)


class ChartMountOrderTests(SimpleTestCase):
    """The section is revealed before a chart mounts inside it.

    ApexCharts measures its container when it renders, and a container inside
    a `display: none` ancestor measures zero: the chart draws at zero width
    and never recovers. The first cut of this panel filled the cards, mounted
    both charts, and *then* unhid the section — so both cards showed a title
    and an empty space. Seen in the live browser, not by any test here; this
    pins the ordering that fixed it.

    The same failure has a version of its own in this project's history
    (1.7.19, chart-mounts-at-zero-width), which is why it is worth a test
    rather than a comment alone.
    """

    script = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
    ).read_text(encoding="utf-8")

    def body(self):
        start = self.script.index("async function setupDashboardInsights()")
        return self.script[start:self.script.index("\n    function kpiCard(", start)]

    def test_the_section_is_revealed_before_either_chart_renders(self):
        body = self.body()
        reveal = body.index("section.hidden = false;")
        for call in ("renderMixedChart(", "renderDonutChart(", "renderGaugeChart(", "renderMultiGaugeChart("):
            with self.subTest(call=call):
                self.assertLess(reveal, body.index(call))

    def test_an_empty_panel_hides_itself_again(self):
        body = self.body()
        self.assertIn("!data.kpis.length", body)
        self.assertIn("!data.trend", body)
        self.assertIn("!data.breakdown", body)
        self.assertIn("!(data.gauges || []).length", body)
        self.assertIn("section.hidden = true;", body)
