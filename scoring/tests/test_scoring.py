"""Person scores (2.20.0): explainable, weighted, stored only when they move."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales.models import Lead
from sales.services import create_customer_with_phone, create_lead, reassign_lead, record_interaction
from scoring.models import PersonScore
from scoring.services import (
    compute_many,
    current_score,
    level_for,
    recalculate_all,
    update_weights,
    weights_for,
)

PASSWORD = "Strong-pass-448!"


class Fixtures(TestCase):
    # Throttle counters live in the cache and are keyed by user id, which
    # test databases reuse; clearing keeps this module from being throttled
    # by — or throttling — the rest of the suite.
    def tearDown(self):
        cache.clear()
        super().tearDown()

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(username="sc.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="sc.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="sc.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری امتیاز", phone={"raw_phone": "09150003333", "is_primary": True}
        )

    def called(self, days_ago=1):
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین امتیاز")
        record_interaction(
            actor=self.manager, lead=lead, phone="09150003333", direction="outbound",
            outcome="پاسخ داد", occurred_at=timezone.now() - timedelta(days=days_ago),
        )
        return lead


class ComputationTests(Fixtures):
    def test_every_factor_explains_itself(self):
        self.called()
        result = compute_many("customer", [self.customer])[self.customer.pk]
        keys = [factor["key"] for factor in result["breakdown"]]
        self.assertEqual(keys, ["recency", "frequency", "monetary", "punctuality", "engagement"])
        for factor in result["breakdown"]:
            self.assertTrue(factor["reason"])
        recency = next(f for f in result["breakdown"] if f["key"] == "recency")
        self.assertEqual(recency["points"], 25)
        self.assertEqual(result["level"], level_for(result["score"]))

    def test_an_unmeasurable_factor_is_left_out_not_counted_as_zero(self):
        self.called()
        result = compute_many("customer", [self.customer])[self.customer.pk]
        punctuality = next(f for f in result["breakdown"] if f["key"] == "punctuality")
        self.assertFalse(punctuality["applicable"])
        # recency 25 + engagement 4 of the 75 measurable points.
        self.assertEqual(result["score"], round(100 * (25 + 4) / 75))

    def test_weights_change_the_score_and_zero_drops_a_factor(self):
        self.called()
        before = compute_many("customer", [self.customer])[self.customer.pk]["score"]
        update_weights(actor=self.admin, person_type="customer", weights={"frequency": 0, "monetary": 0})
        after = compute_many("customer", [self.customer])[self.customer.pk]["score"]
        self.assertGreater(after, before)

    def test_the_level_boundaries(self):
        self.assertEqual([level_for(value) for value in (100, 80, 79, 60, 59, 40, 39, 0)],
                         ["excellent", "excellent", "good", "good", "fair", "fair", "weak", "weak"])

    def test_a_marketers_conversion_counts_decided_leads(self):
        done = self.called()
        reassign_lead(actor=self.manager, lead=done, to_user=self.agent)
        Lead.objects.filter(pk=done.pk).update(status=Lead.Status.COMPLETED, closed_at=timezone.now())
        result = compute_many("user", [self.agent])[self.agent.pk]
        conversion = next(f for f in result["breakdown"] if f["key"] == "conversion")
        self.assertEqual(conversion["points"], 30)


class SnapshotTests(Fixtures):
    def test_a_run_that_changes_nothing_stores_nothing(self):
        self.called()
        first = recalculate_all(("customer",))
        second = recalculate_all(("customer",))
        self.assertEqual(first["customer"][1], 1)
        self.assertEqual(second["customer"][1], 0)
        self.assertEqual(PersonScore.objects.filter(person_type="customer").count(), 1)

    def test_a_stale_score_is_refreshed_when_read(self):
        self.called()
        old = timezone.now() - timedelta(days=2)
        current_score("customer", self.customer, now=old)
        fresh = current_score("customer", self.customer)
        self.assertEqual(PersonScore.objects.filter(person_type="customer").count(), 2)
        self.assertGreater(fresh.computed_at, old)

    def test_the_command_reports_and_is_a_no_op_without_the_feature(self):
        self.called()
        out = StringIO()
        call_command("recalculate_person_scores", "--type", "customer", stdout=out)
        self.assertIn("customer:", out.getvalue())
        with override_active_profile(DeploymentProfile(
            profile_id="client-1", features=frozenset(ALL_FEATURES) - {"person_scoring"}, source="signed-manifest"
        )):
            out = StringIO()
            call_command("recalculate_person_scores", stdout=out)
            self.assertIn("not enabled", out.getvalue())


class WeightSettingsTests(Fixtures):
    def test_only_the_platform_admin_sets_weights(self):
        with self.assertRaises(BusinessPermissionDenied):
            update_weights(actor=self.manager, person_type="customer", weights={"recency": 10})
        api = APIClient()
        api.force_authenticate(self.manager)
        self.assertEqual(api.get("/api/v1/scoring-settings/").status_code, 403)

    def test_weights_are_validated(self):
        for weights in ({"recency": 101}, {"recency": -1}, {"nope": 5}, {"recency": True}):
            with self.subTest(weights=weights), self.assertRaises(BusinessRuleError):
                update_weights(actor=self.admin, person_type="customer", weights=weights)
        with self.assertRaises(BusinessRuleError):
            update_weights(actor=self.admin, person_type="customer", weights={
                "recency": 0, "frequency": 0, "monetary": 0, "punctuality": 0, "engagement": 0,
            })

    def test_the_api_round_trip(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        response = api.put("/api/v1/scoring-settings/", {"person_type": "user", "weights": {"conversion": 50}}, format="json")
        self.assertEqual(response.status_code, 200)
        conversion = next(f for f in response.data["user"] if f["key"] == "conversion")
        self.assertEqual((conversion["weight"], conversion["default"]), (50, 30))
        self.assertEqual(weights_for("user")["activity"], 20)


class ScoreApiTests(Fixtures):
    def test_the_breakdown_and_history_are_served_to_those_who_see_the_card(self):
        self.called()
        api = APIClient()
        api.force_authenticate(self.manager)
        data = api.get(f"/api/v1/profiles/customer/{self.customer.pk}/score/").data
        self.assertEqual(len(data["current"]["breakdown"]), 5)
        self.assertEqual(len(data["history"]), 1)

    def test_a_colleagues_score_is_the_performance_readers_only(self):
        api = APIClient()
        api.force_authenticate(self.agent)
        # An agent opens only their own profile; there the score is theirs to see.
        self.assertIn(api.get(f"/api/v1/profiles/user/{self.agent.pk}/score/").status_code, (200,))
        self.assertEqual(api.get(f"/api/v1/profiles/user/{self.manager.pk}/score/").status_code, 404)


class MoneyFactorTests(Fixtures):
    def test_monetary_ranks_against_other_purchasers(self):
        from sales.services import mark_sale

        other = create_customer_with_phone(
            actor=self.manager, full_name="مشتری دوم", phone={"raw_phone": "09150003334", "is_primary": True}
        )
        for customer, amount in ((self.customer, "900"), (other, "100")):
            lead = create_lead(actor=self.manager, customer=customer, source="فروش")
            mark_sale(actor=self.manager, lead=lead, total_amount=Decimal(amount), sold_at=timezone.now())
        with override_active_profile(DeploymentProfile(
            profile_id="client-1", features=frozenset(ALL_FEATURES) - {"invoices", "payments", "cheques"}, source="signed-manifest"
        )):
            results = compute_many("customer", [self.customer, other])
        rank = {pk: next(f for f in r["breakdown"] if f["key"] == "monetary")["points"] for pk, r in results.items()}
        self.assertEqual(rank[self.customer.pk], 20)
        self.assertEqual(rank[other.pk], 0)
