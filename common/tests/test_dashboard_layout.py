"""`common.dashboard_layout`: which dashboard widgets show, in what order,
and how wide — this deployment's default and each reader's own overlay.

Rewritten for 2.8.0, when the product owner asked for the deployment-wide
settings page («صفحهٔ چیدمان داشبورد») to be deleted and the dashboard
itself to become customisable in place. The two-layer model is what
replaced it, and the layering is the part most worth pinning down, because
getting it wrong would turn a presentation preference into a permission:

* a hidden widget is genuinely removed from `dashboard_for`'s own output,
  not merely marked — the same "disabled means gone, not merely hidden by
  the frontend" posture every other feature in this codebase already takes;
* **a user's overlay can only ever narrow.** A widget this deployment's
  default hides stays hidden no matter what that user saves;
* a user's saved arrangement is *theirs* — one user's order never reaches
  another's dashboard;
* `widget_order` reorders without requiring every key to be listed, and an
  unlisted key keeps its original relative position rather than vanishing;
* an unknown widget key or size is refused outright, never silently stored
  — a typo in a hand-written request body must not create a permanently
  hidden "ghost" key with no control left to un-hide it;
* "reset" is the *absence* of an overlay, not a saved empty one, so a user
  who resets follows a later change to the deployment default;
* the API is feature-gated the same way `/api/v1/branding/` is (404, not
  403, when the feature is off) and open to every signed-in role, because
  arranging your own screen is not a privilege.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common import dashboard, dashboard_layout
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessRuleError
from common.models import UserDashboardLayout
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

    def base_payload(self):
        return {
            "kpis": [
                {"key": "sales_amount_this_month", "display": "۱"},
                {"key": "outstanding", "display": "۲"},
                {"key": "calls_this_week", "display": "۳"},
            ],
            "trend": {"title": "روند"},
            "breakdown": {"title": "تفکیک"},
            "gauges": [{"key": "lead_conversion_rate"}, {"key": "receivables_collection_rate"}],
            "agent_share": {"title": "سهم"},
        }

    def keys(self, result):
        return [kpi["key"] for kpi in result["kpis"]]


class ValidationTests(LayoutFixtures):
    def test_an_unknown_widget_key_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            dashboard_layout.update_user_dashboard_layout(
                actor=self.admin, hidden_widgets=["not_a_real_widget"],
            )

    def test_an_unknown_size_token_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            dashboard_layout.update_user_dashboard_layout(
                actor=self.admin, widget_sizes={"trend": "enormous"},
            )

    def test_a_size_keyed_by_an_unknown_widget_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            dashboard_layout.update_user_dashboard_layout(
                actor=self.admin, widget_sizes={"not_a_real_widget": "half"},
            )

    def test_a_non_list_order_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            dashboard_layout.update_user_dashboard_layout(actor=self.admin, widget_order="trend")

    def test_a_repeated_key_is_stored_once_not_twice(self):
        row = dashboard_layout.update_user_dashboard_layout(
            actor=self.admin, widget_order=["trend", "outstanding", "trend"],
        )
        self.assertEqual(row.widget_order, ["trend", "outstanding"])

    def test_each_field_is_independent(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.admin, hidden_widgets=["outstanding"])
        row = dashboard_layout.update_user_dashboard_layout(actor=self.admin, widget_order=["trend"])
        self.assertEqual(row.hidden_widgets, ["outstanding"])
        self.assertEqual(row.widget_order, ["trend"])


class ApplyLayoutTests(LayoutFixtures):
    def test_no_settings_saved_leaves_every_widget_present(self):
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(self.keys(result), ["sales_amount_this_month", "outstanding", "calls_this_week"])
        self.assertIsNotNone(result["trend"])
        self.assertIsNotNone(result["breakdown"])
        self.assertIsNotNone(result["agent_share"])
        self.assertEqual(len(result["gauges"]), 2)

    def test_a_users_own_hidden_widget_is_removed_from_their_payload(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, hidden_widgets=["outstanding"])
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertNotIn("outstanding", self.keys(result))

    def test_hiding_the_chart_pseudo_widgets_removes_those_sections(self):
        dashboard_layout.update_user_dashboard_layout(
            actor=self.agent, hidden_widgets=["trend", "breakdown", "agent_share"],
        )
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertIsNone(result["trend"])
        self.assertIsNone(result["breakdown"])
        self.assertIsNone(result["agent_share"])

    def test_hiding_a_gauge_removes_only_that_gauge(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, hidden_widgets=["lead_conversion_rate"])
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual([gauge["key"] for gauge in result["gauges"]], ["receivables_collection_rate"])

    def test_an_unlisted_key_keeps_its_position_rather_than_vanishing(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, widget_order=["outstanding"])
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(
            self.keys(result), ["outstanding", "sales_amount_this_month", "calls_this_week"],
        )

    def test_a_stale_key_from_a_removed_widget_is_ignored_not_an_error(self):
        # Written directly, bypassing validation — simulates a widget that
        # existed in an older version and was later removed.
        UserDashboardLayout.objects.create(
            user=self.agent, hidden_widgets=["some_widget_removed_later"],
        )
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(len(result["kpis"]), 3)

    def test_every_part_carries_the_column_classes_it_should_render_at(self):
        """The browser holds no second copy of `WIDGET_SIZES`, so the size
        has to arrive with the widget or the grid cannot place it."""
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(result["kpis"][0]["size"], dashboard_layout.WIDGET_SIZES["quarter"][1])
        self.assertEqual(result["trend"]["size"], dashboard_layout.WIDGET_SIZES["half"][1])
        self.assertEqual(result["agent_share"]["size"], dashboard_layout.WIDGET_SIZES["full"][1])

    def test_a_saved_size_overrides_the_designed_default(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, widget_sizes={"trend": "full"})
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(result["trend"]["size"], dashboard_layout.WIDGET_SIZES["full"][1])


class LayeringTests(LayoutFixtures):
    """The deployment default is a floor a reader's own overlay may narrow
    but never lift. Getting this backwards would turn a display preference
    into a way around an admin's decision.
    """

    def hide_for_the_deployment(self, *keys):
        row = dashboard_layout.get_dashboard_settings()
        row.hidden_widgets = list(keys)
        row.save(update_fields=["hidden_widgets"])

    def test_a_deployment_hidden_widget_stays_hidden_for_a_user_who_did_not_hide_it(self):
        self.hide_for_the_deployment("outstanding")
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertNotIn("outstanding", self.keys(result))

    def test_a_user_cannot_unhide_what_the_deployment_hid(self):
        self.hide_for_the_deployment("outstanding")
        # An empty hidden set is the strongest "put everything back" a user
        # can express; it still must not reach the deployment's own choice.
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, hidden_widgets=[])
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertNotIn("outstanding", self.keys(result))

    def test_the_deployment_order_applies_to_a_user_who_saved_none(self):
        row = dashboard_layout.get_dashboard_settings()
        row.widget_order = ["calls_this_week"]
        row.save(update_fields=["widget_order"])
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(self.keys(result)[0], "calls_this_week")

    def test_a_users_own_order_replaces_the_deployment_order(self):
        row = dashboard_layout.get_dashboard_settings()
        row.widget_order = ["calls_this_week"]
        row.save(update_fields=["widget_order"])
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, widget_order=["outstanding"])
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(self.keys(result)[0], "outstanding")

    def test_one_users_arrangement_does_not_reach_another(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, hidden_widgets=["outstanding"])
        mine = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        theirs = dashboard_layout.apply_layout(self.base_payload(), self.admin)
        self.assertNotIn("outstanding", self.keys(mine))
        self.assertIn("outstanding", self.keys(theirs))

    def test_reset_is_the_absence_of_an_overlay_not_a_saved_empty_one(self):
        dashboard_layout.update_user_dashboard_layout(actor=self.agent, hidden_widgets=["outstanding"])
        dashboard_layout.reset_user_dashboard_layout(actor=self.agent)
        self.assertFalse(UserDashboardLayout.objects.filter(pk=self.agent.pk).exists())
        self.assertFalse(dashboard_layout.effective_layout(self.agent)["is_customised"])
        # …and the deployment's own later change is then followed again.
        self.hide_for_the_deployment("calls_this_week")
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertNotIn("calls_this_week", self.keys(result))

    def test_what_the_deployment_hid_is_reported_as_locked(self):
        """The editor needs to know which hidden widgets it must not offer
        to restore, or it would render a control that silently does
        nothing."""
        self.hide_for_the_deployment("outstanding")
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertEqual(result["layout"]["locked_hidden"], ["outstanding"])


class DashboardIntegrationTests(LayoutFixtures):
    """`common.dashboard.dashboard_for` actually applies the reader's own
    layout — proven with a real KPI, not just the isolated payload above.
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

        dashboard_layout.update_user_dashboard_layout(
            actor=manager, hidden_widgets=["sales_amount_this_month"],
        )
        after = dashboard.dashboard_for(manager)
        self.assertNotIn("sales_amount_this_month", [kpi["key"] for kpi in after["kpis"]])


class APITests(LayoutFixtures):
    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_every_signed_in_role_may_read_its_own_layout(self):
        """Not a privilege: arranging your own screen is neither a business
        permission nor a data-scope question (CLAUDE.md §5.1)."""
        response = self.client_for(self.agent).get("/api/v1/dashboard-layout/")
        self.assertEqual(response.status_code, 200)

    def test_an_anonymous_visitor_is_refused(self):
        response = APIClient().get("/api/v1/dashboard-layout/")
        self.assertIn(response.status_code, (401, 403))

    def test_get_is_404_when_the_feature_is_off(self):
        with override_active_profile(without_dashboard_insights()):
            response = self.client_for(self.admin).get("/api/v1/dashboard-layout/")
        self.assertEqual(response.status_code, 404)

    def test_get_returns_the_full_catalog_and_the_size_vocabulary(self):
        response = self.client_for(self.admin).get("/api/v1/dashboard-layout/")
        self.assertEqual(response.status_code, 200)
        keys = {entry["key"] for entry in response.data["catalog"]}
        self.assertEqual(keys, dashboard_layout.WIDGET_KEYS)
        sizes = {entry["value"] for entry in response.data["sizes"]}
        self.assertEqual(sizes, set(dashboard_layout.WIDGET_SIZES))

    def test_a_sales_agent_can_save_their_own_arrangement(self):
        response = self.client_for(self.agent).post(
            "/api/v1/dashboard-layout/",
            {
                "hidden_widgets": ["outstanding"],
                "widget_order": ["trend", "breakdown"],
                "widget_sizes": {"trend": "full"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["hidden_widgets"], ["outstanding"])
        self.assertEqual(response.data["widget_order"], ["trend", "breakdown"])
        self.assertEqual(response.data["widget_sizes"], {"trend": "full"})
        self.assertTrue(response.data["is_customised"])

    def test_saving_reaches_only_the_callers_own_row(self):
        self.client_for(self.agent).post(
            "/api/v1/dashboard-layout/", {"hidden_widgets": ["outstanding"]}, format="json",
        )
        self.assertFalse(UserDashboardLayout.objects.filter(pk=self.admin.pk).exists())
        self.assertEqual(dashboard_layout.get_dashboard_settings().hidden_widgets, [])

    def test_a_request_naming_another_user_is_refused_as_an_unknown_field(self):
        """There is no `user` parameter to forward — the serializer refuses
        anything it does not declare, and the service takes an actor only."""
        response = self.client_for(self.agent).post(
            "/api/v1/dashboard-layout/",
            {"user": self.admin.pk, "hidden_widgets": ["outstanding"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_widget_key_is_a_400_through_the_api(self):
        response = self.client_for(self.admin).post(
            "/api/v1/dashboard-layout/", {"hidden_widgets": ["nope"]}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_drops_the_overlay(self):
        client = self.client_for(self.agent)
        client.post("/api/v1/dashboard-layout/", {"hidden_widgets": ["outstanding"]}, format="json")
        response = client.delete("/api/v1/dashboard-layout/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_customised"])
        self.assertFalse(UserDashboardLayout.objects.filter(pk=self.agent.pk).exists())

    def test_the_response_is_never_cached(self):
        response = self.client_for(self.agent).get("/api/v1/dashboard-layout/")
        self.assertEqual(response["Cache-Control"], "private, no-store")


class RetiredSettingsPageTests(LayoutFixtures):
    """The deployment-wide layout page is gone (product owner, 2026-09-20).
    Its data is not: the row and everything saved in it still apply as this
    deployment's default.
    """

    def test_the_old_url_is_no_longer_routed(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/settings/dashboard/").status_code, 404)

    def test_the_admin_accordion_no_longer_offers_it(self):
        self.client.force_login(self.admin)
        page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn("چیدمان داشبورد", page)

    def test_the_deployment_row_is_still_read(self):
        row = dashboard_layout.get_dashboard_settings()
        row.hidden_widgets = ["outstanding"]
        row.save(update_fields=["hidden_widgets"])
        result = dashboard_layout.apply_layout(self.base_payload(), self.agent)
        self.assertNotIn("outstanding", self.keys(result))


class DashboardEditorMarkupTests(LayoutFixtures):
    """The controls the product owner asked for are actually on the page:
    a small pencil at the start of the section, and one grid for the
    widgets to be dragged between.
    """

    def page(self):
        self.client.force_login(self.admin)
        return self.client.get("/").content.decode("utf-8")

    def test_the_dashboard_has_one_widget_grid(self):
        self.assertIn('id="dashboard-widgets"', self.page())

    def test_the_pencil_control_is_present_and_labelled(self):
        page = self.page()
        self.assertIn('id="dashboard-edit-toggle"', page)
        self.assertIn("ki-pencil", page)
        self.assertIn("شخصی‌سازی داشبورد", page)

    def test_the_editor_bar_starts_hidden(self):
        """Revealed by script once a payload arrives — a pencil over an
        empty section would offer to arrange nothing."""
        page = self.page()
        bar = page.split('id="dashboard-editor-bar"')[1].split(">")[0]
        self.assertIn("hidden", bar)
