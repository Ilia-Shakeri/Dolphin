"""The profile header's stat cards #4–#7, the completion bar, and the task and
note tabs (2.20.0). A card a reader may not see must be absent from the page
*and* from the API — its value never reaches the browser."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from profiles.cards import period_for
from profiles.completion import completion_for
from sales.models import Lead
from sales.services import create_customer_with_phone, create_lead, mark_sale, reassign_lead

PASSWORD = "Strong-pass-448!"


def without(*features):
    return DeploymentProfile(profile_id="client-1", features=frozenset(ALL_FEATURES) - frozenset(features), source="signed-manifest")


class Fixtures(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="cc.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="cc.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(
            username="cc.agent", password=PASSWORD, role=User.Role.SALES_AGENT, first_name="رضا", phone="09120001234"
        )
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری کارت", phone={"raw_phone": "09150004444", "is_primary": True}
        )

    def cards(self, viewer, person_type, person_id, period="this_month"):
        api = APIClient()
        api.force_authenticate(viewer)
        return api.get(f"/api/v1/profiles/{person_type}/{person_id}/cards/?period={period}")


class UserCardTests(Fixtures):
    def test_a_manager_sees_a_marketers_four_cards(self):
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین")
        reassign_lead(actor=self.manager, lead=lead, to_user=self.agent)
        mark_sale(actor=self.agent, lead=lead, total_amount=Decimal("250000.00"), sold_at=timezone.now())
        response = self.cards(self.manager, "user", self.agent.pk)
        self.assertEqual(response.status_code, 200)
        cards = {card["key"]: card for card in response.data["cards"]}
        self.assertEqual(list(cards), ["income", "active_customers", "conversion", "score"])
        self.assertEqual(cards["income"]["raw"], "250000.00")
        self.assertIn("نه کمیسیون", cards["income"]["tooltip"])

    def test_conversion_without_decided_leads_is_a_dash_with_a_reason(self):
        card = next(c for c in self.cards(self.manager, "user", self.agent.pk).data["cards"] if c["key"] == "conversion")
        self.assertTrue(card["missing"])
        self.assertEqual(card["value"], "—")
        self.assertTrue(card["tooltip"])

    def test_conversion_counts_leads_decided_in_the_period(self):
        for status in (Lead.Status.COMPLETED, Lead.Status.CANCELLED, Lead.Status.COMPLETED):
            lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین")
            reassign_lead(actor=self.manager, lead=lead, to_user=self.agent)
            Lead.objects.filter(pk=lead.pk).update(status=status, closed_at=timezone.now())
        card = next(c for c in self.cards(self.manager, "user", self.agent.pk).data["cards"] if c["key"] == "conversion")
        self.assertEqual(card["raw"], 66.7)

    def test_a_reader_outside_the_performance_scope_gets_no_money_cards(self):
        """The Platform Admin administers the account but also reads every
        report; an administrator *without* report rights would see none —
        simulated here by switching reports off."""
        with override_active_profile(without("reports")):
            response = self.cards(self.admin, "user", self.agent.pk)
        self.assertEqual(response.data["cards"], [])

    def test_the_score_card_leaves_with_its_feature(self):
        with override_active_profile(without("person_scoring")):
            keys = [card["key"] for card in self.cards(self.manager, "user", self.agent.pk).data["cards"]]
        self.assertNotIn("score", keys)


class CustomerCardTests(Fixtures):
    def test_a_manager_sees_debt_purchases_last_interaction_and_score(self):
        keys = [card["key"] for card in self.cards(self.manager, "customer", self.customer.pk).data["cards"]]
        self.assertEqual(keys, ["debt", "purchases", "last_interaction", "score"])

    def test_a_marketer_without_money_rights_gets_no_money_cards(self):
        mine = create_customer_with_phone(
            actor=self.agent, full_name="مشتری من", phone={"raw_phone": "09150004445", "is_primary": True}
        )
        from accounts.models import UserCapabilityOverride

        for capability in ("ledger.own", "invoices.scoped", "sales.own"):
            UserCapabilityOverride.objects.create(user=self.agent, capability=capability, granted=False)
        keys = [card["key"] for card in self.cards(self.agent, "customer", mine.pk).data["cards"]]
        self.assertNotIn("debt", keys)
        self.assertNotIn("purchases", keys)
        page = self.client
        page.force_login(self.agent)
        html = page.get(f"/customers/{mine.pk}/").content.decode("utf-8")
        self.assertNotIn('data-profile-card="debt"', html)

    def test_purchases_use_confirmed_sales_when_invoices_are_off(self):
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین")
        mark_sale(actor=self.manager, lead=lead, total_amount=Decimal("120000.00"), sold_at=timezone.now())
        with override_active_profile(without("invoices", "payments", "cheques", "customer_ledger")):
            cards = {c["key"]: c for c in self.cards(self.manager, "customer", self.customer.pk).data["cards"]}
        self.assertEqual(cards["purchases"]["raw"], "120000.00")
        self.assertNotIn("debt", cards)

    def test_an_out_of_scope_customer_is_a_404(self):
        self.assertEqual(self.cards(self.agent, "customer", self.customer.pk).status_code, 404)


class PeriodTests(TestCase):
    def test_periods_are_jalali_months_with_an_equal_window_before(self):
        now = timezone.now()
        month = period_for("this_month", now=now)
        self.assertLessEqual(month.start, now)
        self.assertGreater(month.end, now)
        self.assertEqual(month.previous_end, month.start)
        self.assertEqual(period_for("nonsense", now=now).key, "this_month")
        last_90 = period_for("last_90_days", now=now)
        self.assertEqual(last_90.end - last_90.start, timedelta(days=90))


class CompletionTests(Fixtures):
    def test_a_bare_customer_is_partly_complete_and_says_what_is_missing(self):
        result = completion_for("customer", self.customer, can_edit=True)
        self.assertEqual(result["percent"], 25)  # name and phone
        missing = {item["key"]: item for item in result["missing"]}
        self.assertEqual(missing["email"]["input_id"], "edit-customer-email")

    def test_a_reader_who_cannot_edit_gets_no_links(self):
        result = completion_for("user", self.agent, can_edit=False)
        self.assertTrue(all(item["input_id"] == "" for item in result["missing"]))
        self.assertEqual(result["percent"], 15 + 20)  # first name, phone

    def test_the_bar_is_on_the_page(self):
        self.client.force_login(self.manager)
        html = self.client.get(f"/customers/{self.customer.pk}/").content.decode("utf-8")
        self.assertIn("data-profile-completion", html)
        self.assertIn('data-focus="edit-customer-email"', html)


class TaskAndNoteTabTests(Fixtures):
    def test_tabs_and_quick_actions_follow_features_and_capabilities(self):
        self.client.force_login(self.manager)
        html = self.client.get(f"/customers/{self.customer.pk}/").content.decode("utf-8")
        for marker in ('data-profile-tab="tasks"', 'data-profile-tab="notes"', 'data-quick-action="task"', 'data-quick-action="note"', 'id="profile-task-dialog"'):
            self.assertIn(marker, html)
        with override_active_profile(without("tasks", "person_notes")):
            html = self.client.get(f"/customers/{self.customer.pk}/").content.decode("utf-8")
        for marker in ('data-profile-tab="tasks"', 'data-profile-tab="notes"', 'id="profile-task-dialog"'):
            self.assertNotIn(marker, html)

    def test_only_a_tasks_company_holder_may_pick_another_assignee(self):
        self.client.force_login(self.agent)
        html = self.client.get(f"/users/{self.agent.pk}/").content.decode("utf-8")
        dialog = html.split('id="profile-task-dialog"', 1)[1].split("</dialog>", 1)[0]
        self.assertEqual(dialog.count("<option"), 1)

    def test_the_settings_page_offers_weights_to_the_platform_admin_only(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/settings/"), 'id="panel-scoring"')
        self.client.force_login(self.manager)
        self.assertNotContains(self.client.get("/settings/"), 'id="panel-scoring"')
