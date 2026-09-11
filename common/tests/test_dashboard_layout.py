"""`common.dashboard_layout`: which dashboard widgets show, and in what
order — the admin-facing half of `common.dashboard`'s "what does this role's
home page show" question.

What is worth proving:

* a hidden widget is genuinely removed from `dashboard_for`'s own output,
  not merely marked — the same "disabled means gone, not merely hidden by
  the frontend" posture every other feature in this codebase already takes;
* `widget_order` reorders without requiring every key to be listed, and an
  unlisted key keeps its original relative position rather than vanishing;
* only a Platform Admin may change it, at the service layer, not merely
  hidden from a lower role's navigation;
* an unknown widget key is refused outright, never silently stored — a typo
  in a hand-written request body must not create a permanently-hidden
  "ghost" key nobody can find in the settings page to un-hide;
* the API is feature-gated the same way `/api/v1/branding/` is (404, not
  403, when the feature is off).
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common import dashboard, dashboard_layout
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales.services import assign_lead, create_customer_with_phone, create_lead, mark_sale

PASSWORD = "Strong-pass-471!"


def without_dashboard_insights():
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset({"dashboard_insights"}),
        source="signed-manifest",
    )


class LayoutFixtures(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="layout.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="layout.agent", password=PASSWORD, role=User.Role.SALES_AGENT)


class ServiceTests(LayoutFixtures):
    def test_get_dashboard_settings_creates_the_singleton_once(self):
        first = dashboard_layout.get_dashboard_settings()
        second = dashboard_layout.get_dashboard_settings()
        self.assertEqual(first.pk, second.pk)

    def test_only_a_platform_admin_may_update_it(self):
        with self.assertRaises(BusinessPermissionDenied):
            dashboard_layout.update_dashboard_settings(actor=self.agent, hidden_widgets=["outstanding"])
        self.assertEqual(dashboard_layout.get_dashboard_settings().hidden_widgets, [])

    def test_an_unknown_widget_key_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            dashboard_layout.update_dashboard_settings(actor=self.admin, hidden_widgets=["not_a_real_widget"])
        self.assertEqual(dashboard_layout.get_dashboard_settings().hidden_widgets, [])

    def test_hidden_widgets_and_order_are_independent(self):
        dashboard_layout.update_dashboard_settings(actor=self.admin, hidden_widgets=["outstanding"])
        dashboard_layout.update_dashboard_settings(actor=self.admin, widget_order=["trend", "breakdown"])
        row = dashboard_layout.get_dashboard_settings()
        self.assertEqual(row.hidden_widgets, ["outstanding"])
        self.assertEqual(row.widget_order, ["trend", "breakdown"])

    def test_duplicate_keys_are_de_duplicated_in_order(self):
        dashboard_layout.update_dashboard_settings(actor=self.admin, widget_order=["trend", "outstanding", "trend"])
        self.assertEqual(dashboard_layout.get_dashboard_settings().widget_order, ["trend", "outstanding"])

    def test_a_successful_update_is_audit_logged(self):
        row = dashboard_layout.update_dashboard_settings(actor=self.admin, hidden_widgets=["outstanding"])
        self.assertTrue(
            ActivityLog.objects.filter(operation="dashboard_settings.updated", object_id=str(row.pk)).exists()
        )


class ApplyLayoutTests(LayoutFixtures):
    def base_payload(self):
        return {
            "kpis": [
                {"key": "sales_amount_this_month", "label": "a"},
                {"key": "outstanding", "label": "b"},
                {"key": "calls_this_week", "label": "c"},
            ],
            "trend": {"weeks": []},
            "breakdown": {"rows": []},
            "gauges": [
                {"key": "lead_conversion_rate", "label": "d"},
                {"key": "receivables_collection_rate", "label": "e"},
            ],
        }

    def test_a_hidden_kpi_is_removed(self):
        dashboard_layout.update_dashboard_settings(actor=self.admin, hidden_widgets=["outstanding"])
        result = dashboard_layout.apply_layout(self.base_payload())
        self.assertNotIn("outstanding", [kpi["key"] for kpi in result["kpis"]])
        self.assertEqual(len(result["kpis"]), 2)

    def test_hiding_trend_or_breakdown_sets_them_to_none(self):
        dashboard_layout.update_dashboard_settings(actor=self.admin, hidden_widgets=["trend", "breakdown"])
        result = dashboard_layout.apply_layout(self.base_payload())
        self.assertIsNone(result["trend"])
        self.assertIsNone(result["breakdown"])

    def test_a_hidden_gauge_is_removed(self):
        dashboard_layout.update_dashboard_settings(actor=self.admin, hidden_widgets=["lead_conversion_rate"])
        result = dashboard_layout.apply_layout(self.base_payload())
        self.assertNotIn("lead_conversion_rate", [gauge["key"] for gauge in result["gauges"]])
        self.assertEqual(len(result["gauges"]), 1)

    def test_gauge_order_is_applied_the_same_way_as_kpi_order(self):
        dashboard_layout.update_dashboard_settings(
            actor=self.admin, widget_order=["receivables_collection_rate", "lead_conversion_rate"],
        )
        result = dashboard_layout.apply_layout(self.base_payload())
        self.assertEqual(
            [gauge["key"] for gauge in result["gauges"]],
            ["receivables_collection_rate", "lead_conversion_rate"],
        )

    def test_explicit_order_is_applied(self):
        dashboard_layout.update_dashboard_settings(
            actor=self.admin, widget_order=["outstanding", "calls_this_week", "sales_amount_this_month"],
        )
        result = dashboard_layout.apply_layout(self.base_payload())
        self.assertEqual(
            [kpi["key"] for kpi in result["kpis"]],
            ["outstanding", "calls_this_week", "sales_amount_this_month"],
        )

    def test_a_kpi_missing_from_the_order_keeps_its_relative_position_at_the_end(self):
        dashboard_layout.update_dashboard_settings(actor=self.admin, widget_order=["outstanding"])
        result = dashboard_layout.apply_layout(self.base_payload())
        self.assertEqual(
            [kpi["key"] for kpi in result["kpis"]],
            ["outstanding", "sales_amount_this_month", "calls_this_week"],
        )

    def test_a_stale_key_from_a_removed_widget_is_ignored_not_an_error(self):
        # Written directly, bypassing validation — simulates a widget that
        # existed in an older version and was later removed.
        row = dashboard_layout.get_dashboard_settings()
        row.hidden_widgets = ["some_widget_removed_later"]
        row.save(update_fields=["hidden_widgets"])
        result = dashboard_layout.apply_layout(self.base_payload())
        self.assertEqual(len(result["kpis"]), 3)

    def test_no_settings_saved_leaves_the_payload_unchanged(self):
        payload = self.base_payload()
        result = dashboard_layout.apply_layout(payload)
        self.assertEqual(result, payload)


class DashboardIntegrationTests(LayoutFixtures):
    """`common.dashboard.dashboard_for` actually calls `apply_layout` —
    proven with a real KPI, not just the isolated payload above.
    """

    def test_hiding_a_real_kpi_removes_it_from_dashboard_for(self):
        manager = User.objects.create_user(username="layout.mgr", password=PASSWORD, role=User.Role.SALES_MANAGER)
        seller = User.objects.create_user(username="layout.seller", password=PASSWORD, role=User.Role.SALES_AGENT)
        customer = create_customer_with_phone(
            actor=manager, full_name="مشتری چیدمان", phone={"raw_phone": "09121110000", "is_primary": True},
        )
        lead = create_lead(actor=manager, customer=customer, source="کمپین چیدمان")
        assign_lead(actor=manager, lead=lead, to_user=seller)
        mark_sale(actor=seller, lead=lead, quantity=1, total_amount=Decimal("1000000"))
        before = dashboard.dashboard_for(manager)
        self.assertIn("sales_amount_this_month", [kpi["key"] for kpi in before["kpis"]])

        dashboard_layout.update_dashboard_settings(actor=self.admin, hidden_widgets=["sales_amount_this_month"])
        after = dashboard.dashboard_for(manager)
        self.assertNotIn("sales_amount_this_month", [kpi["key"] for kpi in after["kpis"]])


class APITests(LayoutFixtures):
    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_get_requires_platform_admin(self):
        response = self.client_for(self.agent).get("/api/v1/dashboard-layout/")
        self.assertEqual(response.status_code, 403)

    def test_get_is_404_when_the_feature_is_off(self):
        with override_active_profile(without_dashboard_insights()):
            response = self.client_for(self.admin).get("/api/v1/dashboard-layout/")
        self.assertEqual(response.status_code, 404)

    def test_get_returns_the_full_catalog(self):
        response = self.client_for(self.admin).get("/api/v1/dashboard-layout/")
        self.assertEqual(response.status_code, 200)
        keys = {entry["key"] for entry in response.data["catalog"]}
        self.assertEqual(keys, dashboard_layout.WIDGET_KEYS)

    def test_platform_admin_can_update_through_the_api(self):
        client = self.client_for(self.admin)
        response = client.post(
            "/api/v1/dashboard-layout/",
            {"hidden_widgets": ["outstanding"], "widget_order": ["trend", "breakdown"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["hidden_widgets"], ["outstanding"])
        self.assertEqual(response.data["widget_order"], ["trend", "breakdown"])

    def test_a_sales_agent_cannot_update_even_with_a_well_formed_request(self):
        response = self.client_for(self.agent).post(
            "/api/v1/dashboard-layout/", {"hidden_widgets": ["outstanding"]}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(dashboard_layout.get_dashboard_settings().hidden_widgets, [])

    def test_an_unknown_widget_key_is_a_400_through_the_api(self):
        response = self.client_for(self.admin).post(
            "/api/v1/dashboard-layout/", {"hidden_widgets": ["nope"]}, format="json",
        )
        self.assertEqual(response.status_code, 400)


class SettingsPageAccessTests(LayoutFixtures):
    def test_a_platform_admin_can_open_the_settings_page(self):
        self.client.force_login(self.admin)
        response = self.client.get("/settings/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dashboard-layout-form")
        self.assertTemplateUsed(response, "common/dashboard_layout/settings.html")

    def test_a_sales_agent_gets_a_403_card_not_a_crash(self):
        self.client.force_login(self.agent)
        response = self.client.get("/settings/dashboard/")
        self.assertEqual(response.status_code, 403)

    def test_the_page_is_404_when_the_feature_is_off(self):
        self.client.force_login(self.admin)
        with override_active_profile(without_dashboard_insights()):
            response = self.client.get("/settings/dashboard/")
        self.assertEqual(response.status_code, 404)

    def test_the_nav_link_only_shows_for_a_platform_admin_with_the_feature_on(self):
        self.client.force_login(self.admin)
        with_feature = self.client.get("/")
        self.assertContains(with_feature, "چیدمان داشبورد", status_code=200)
        with override_active_profile(without_dashboard_insights()):
            without_feature = self.client.get("/")
        self.assertNotContains(without_feature, "چیدمان داشبورد", status_code=200)

        self.client.force_login(self.agent)
        agent_view = self.client.get("/")
        self.assertNotContains(agent_view, "چیدمان داشبورد", status_code=200)
