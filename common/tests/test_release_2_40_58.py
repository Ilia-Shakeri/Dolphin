"""2.40.58 — call outcomes, the qualified option and the do-not-contact list (BIZ-003).

Product owner, 2026-10-17: an outcome is chosen from a list, for every call,
with free text beside it; twelve standard outcomes; a successful call is a
real contact; «واجد شرایط» is its own option on three outcomes; «نیازمند
پیگیری» needs the next follow-up; «عدم تماس مجدد» takes the number out of
marketing calls and new campaigns, keeping its history; calls, successful
calls, qualified calls and sales are counted apart; older calls keep their
words and are matched by hand or only when certain; a company adds its own
outcomes while the standard ones stay for reporting.
"""

import importlib
from datetime import timedelta

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from integrations.models import Integration
from reports.marketers import build_marketer_ranking
from sales import call_outcomes
from sales.campaigns import add_campaign_member, assign_campaign_member, create_campaign
from sales.models import CallOutcome, DoNotContact, Interaction
from sales.services import add_target_audience_member, create_lead, record_interaction
from telephony.tests.test_telephony import Fixtures as TelephonyFixtures

PASSWORD = "Strong-pass-958!"


def without(feature):
    return DeploymentProfile(profile_id="client-1", features=frozenset(ALL_FEATURES) - {feature}, source="signed-manifest")


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="o.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="o.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="o.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.campaign = create_campaign(actor=self.manager, name="تابستان", responsibles=[self.agent])
        member = add_campaign_member(actor=self.manager, campaign=self.campaign, full_name="شخص", raw_phone="09121110581")
        self.member = assign_campaign_member(actor=self.manager, member=member, to_user=self.agent)

    def call(self, **extra):
        data = {"phone": "09121110581", "direction": "outbound", "occurred_at": timezone.now(), **extra}
        return record_interaction(actor=self.agent, lead=self.member.lead, target_member=self.member, **data)

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class StandardTests(Base):
    def test_the_twelve_standard_outcomes_and_what_each_means(self):
        self.assertEqual([outcome.label for outcome in call_outcomes.outcomes()], [
            "پاسخ نداد", "خط اشغال بود", "شماره اشتباه یا نامعتبر", "تماس برقرار شد", "علاقه‌مند", "نیازمند پیگیری",
            "درخواست پیش‌فاکتور", "خرید انجام شد", "عدم تمایل به خرید", "تماس در زمان دیگری", "عدم تماس مجدد", "سایر",
        ])
        self.assertEqual(set(call_outcomes.STANDARD) - call_outcomes.SUCCESSFUL, {"no_answer", "busy", "wrong_number"})
        self.assertEqual(call_outcomes.MAY_QUALIFY, {"interested", "needs_follow_up", "quote_requested"})

    def test_an_emptied_table_is_seeded_again(self):
        CallOutcome.objects.all().delete()
        self.assertEqual(len(call_outcomes.outcomes()), 12)


class RecordingTests(Base):
    def test_every_call_needs_an_outcome_from_the_list(self):
        with self.assertRaises(BusinessRuleError):
            self.call(outcome="یک متن آزاد")
        with self.assertRaises(BusinessRuleError):
            self.call(result="made_up")
        call = self.call(result="connected", notes="مشتری راضی بود")
        self.assertEqual((call.result, call.result_standard, call.outcome, call.notes),
                         ("connected", "connected", "تماس برقرار شد", "مشتری راضی بود"))

    def test_qualified_is_its_own_option_on_three_outcomes_only(self):
        with self.assertRaises(BusinessRuleError):
            self.call(result="connected", qualified=True)
        call = self.call(result="interested", qualified=True)
        self.assertTrue(call.qualified)

    def test_needs_follow_up_needs_the_next_date(self):
        with self.assertRaises(BusinessRuleError):
            self.call(result="needs_follow_up")
        when = timezone.now() + timedelta(days=2)
        self.call(result="needs_follow_up", next_follow_up_at=when)
        self.member.refresh_from_db()
        self.assertEqual(self.member.next_follow_up_at, when)

    def test_do_not_call_takes_the_number_out_of_marketing_and_keeps_history(self):
        call = self.call(result="do_not_call", notes="گفت دیگر زنگ نزنید")
        row = DoNotContact.objects.get(normalized_phone="+989121110581")
        self.assertEqual((row.interaction_id, row.lifted_at), (call.pk, None))
        other = create_campaign(actor=self.manager, name="پاییز")
        with self.assertRaises(BusinessRuleError):
            add_campaign_member(actor=self.manager, campaign=other, full_name="شخص", raw_phone="09121110581")
        lead = create_lead(actor=self.manager, campaign=other, assignee=None, source="x")
        with self.assertRaises(BusinessRuleError):
            add_target_audience_member(actor=self.manager, lead=lead, full_name="شخص", raw_phone="۰۹۱۲۱۱۱۰۵۸۱")
        # Recording it twice keeps one row; the person and the call stay.
        self.call(result="do_not_call")
        self.assertEqual(DoNotContact.objects.filter(normalized_phone="+989121110581").count(), 1)
        self.assertTrue(Interaction.objects.filter(target_member=self.member).exists())

    def test_a_manager_lifts_it_with_a_reason_and_the_row_stays(self):
        self.call(result="do_not_call")
        row = DoNotContact.objects.get()
        with self.assertRaises(BusinessPermissionDenied):
            call_outcomes.lift_block(actor=self.agent, row=row, reason="x")
        with self.assertRaises(BusinessRuleError):
            call_outcomes.lift_block(actor=self.manager, row=row, reason=" ")
        call_outcomes.lift_block(actor=self.manager, row=row, reason="خودش دوباره درخواست داد")
        with self.assertRaises(BusinessConflictError):
            call_outcomes.lift_block(actor=self.manager, row=row, reason="دوباره")
        self.assertFalse(call_outcomes.is_blocked("+989121110581"))
        self.assertEqual(DoNotContact.objects.count(), 1)

    def test_a_group_text_leaves_the_listed_numbers_out(self):
        from communications.services import create_sms_campaign

        self.call(result="do_not_call")
        campaign = create_sms_campaign(actor=self.manager, body="سلام", phones=["09121110581", "09121110582"])
        self.assertEqual(list(campaign.recipients.values_list("recipient_normalized", flat=True)), ["+989121110582"])
        with self.assertRaises(BusinessRuleError):
            create_sms_campaign(actor=self.manager, body="سلام", phones=["09121110581"])

    def test_the_api_requires_the_outcome_and_answers_its_name(self):
        client = self.api(self.agent)
        body = {"lead": self.member.lead_id, "target_member": self.member.pk, "phone": "09121110581",
                "direction": "outbound", "occurred_at": timezone.now().isoformat()}
        self.assertEqual(client.post("/api/v1/interactions/", body, format="json").status_code, 400)
        made = client.post("/api/v1/interactions/", {**body, "result": "quote_requested", "qualified": True}, format="json")
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual((made.json()["result_label"], made.json()["qualified"], made.json()["successful"]),
                         ("درخواست پیش‌فاکتور", True, True))
        listed = client.get("/api/v1/interactions/?result=quote_requested&qualified=true").json()
        self.assertEqual([row["id"] for row in listed["results"]], [made.json()["id"]])
        self.assertEqual(client.get("/api/v1/interactions/?result=nonsense").status_code, 400)


class ReportTests(Base):
    def test_calls_successful_and_qualified_are_counted_apart(self):
        self.call(result="no_answer")
        self.call(result="busy")
        self.call(result="connected")
        self.call(result="interested", qualified=True)
        now = timezone.now()
        report = build_marketer_ranking(actor=self.admin, period_start=now - timedelta(days=1), period_end=now + timedelta(minutes=1))
        row = next(item for item in report["results"] if item.user_id == self.agent.pk)
        self.assertEqual((row.calls_count, row.successful_calls, row.qualified_calls), (4, 2, 1))
        self.assertEqual((report["totals"]["successful_calls"], report["totals"]["qualified_calls"]), (2, 1))


class LegacyTests(Base):
    def old_call(self, text):
        return Interaction.objects.create(
            lead=self.member.lead, target_member=self.member, agent=self.agent, phone="09121110581",
            direction="outbound", outcome=text, occurred_at=timezone.now(),
        )

    def test_the_migration_matches_only_certain_words(self):
        migration = importlib.import_module("sales.migrations.0040_seed_call_outcomes")
        exact = self.old_call("پاسخ نداد")
        spaced = self.old_call("علاقه مند")
        refused = self.old_call("عدم تماس مجدد")
        loose = self.old_call("پاسخ داد")
        migration.forward(django_apps, None)
        for call in (exact, spaced, refused, loose):
            call.refresh_from_db()
        self.assertEqual([exact.result, spaced.result, refused.result, loose.result],
                         ["no_answer", "interested", "do_not_call", ""])
        self.assertEqual(exact.outcome, "پاسخ نداد")
        self.assertTrue(call_outcomes.is_blocked("+989121110581"))

    def test_a_manager_matches_the_rest_by_hand(self):
        self.old_call("پاسخ داد")
        self.old_call("پاسخ داد")
        self.assertEqual(call_outcomes.legacy_texts(), [{"text": "پاسخ داد", "count": 2}])
        with self.assertRaises(BusinessPermissionDenied):
            call_outcomes.map_legacy(actor=self.manager, text="پاسخ داد", result="connected")
        self.assertEqual(call_outcomes.map_legacy(actor=self.admin, text="پاسخ داد", result="connected"), 2)
        self.assertEqual(Interaction.objects.filter(result="connected", outcome="پاسخ داد").count(), 2)
        with self.assertRaises(BusinessConflictError):
            call_outcomes.map_legacy(actor=self.admin, text="پاسخ داد", result="connected")
        answer = self.api(self.admin).get("/api/v1/call-outcomes/legacy/").json()
        self.assertEqual(answer["texts"], [])


class CompanyOutcomeTests(Base):
    def test_a_company_outcome_counts_as_its_standard_one(self):
        with self.assertRaises(BusinessPermissionDenied):
            call_outcomes.create_outcome(actor=self.manager, label="ارسال کاتالوگ", standard_key="interested")
        with override_active_profile(without("customization")):
            with self.assertRaises(BusinessPermissionDenied):
                call_outcomes.create_outcome(actor=self.admin, label="ارسال کاتالوگ", standard_key="interested")
        outcome = call_outcomes.create_outcome(actor=self.admin, label="ارسال کاتالوگ", standard_key="interested")
        self.assertEqual(outcome.key, "c1")
        call = self.call(result=outcome.key, qualified=True)
        self.assertEqual((call.result, call.result_standard, call.outcome), ("c1", "interested", "ارسال کاتالوگ"))
        with self.assertRaises(BusinessRuleError):
            call_outcomes.update_outcome(actor=self.admin, outcome=CallOutcome.objects.get(key="other"), is_active=False)
        call_outcomes.update_outcome(actor=self.admin, outcome=outcome, is_active=False)
        with self.assertRaises(BusinessRuleError):
            self.call(result=outcome.key)
        client = self.api(self.admin)
        refused = client.patch(f"/api/v1/call-outcomes/{outcome.pk}/", {"standard_key": "busy"}, format="json")
        self.assertEqual(refused.status_code, 400)

    def test_the_settings_tab(self):
        self.client.force_login(self.admin)
        page = self.client.get("/settings/?tab=calls").content.decode()
        self.assertIn('id="call-outcomes-body"', page)
        self.assertIn('id="legacy-outcomes-body"', page)
        self.assertIn('id="do-not-contact-body"', page)
        self.client.force_login(self.manager)
        self.assertNotIn('id="settings-pane-calls"', self.client.get("/settings/").content.decode())
        self.assertEqual(self.api(self.manager).get("/api/v1/call-outcomes/").status_code, 403)

    def test_the_call_form_offers_the_list(self):
        self.client.force_login(self.agent)
        page = self.client.get("/interactions/").content.decode()
        self.assertIn('id="create-interaction-result"', page)
        self.assertIn('id="create-interaction-qualified"', page)
        self.assertNotIn('id="create-interaction-outcome"', page)


class OriginateTests(TelephonyFixtures):
    def test_click_to_call_refuses_a_listed_number_except_for_after_sales(self):
        Integration.objects.filter(pk=self.pbx.pk).update(status=Integration.Status.OK)
        DoNotContact.objects.create(normalized_phone="+989151234567", created_by=self.manager)
        client = APIClient()
        client.force_authenticate(self.agent)
        refused = client.post("/api/v1/telephony/originate/", {"number": "09151234567"}, format="json")
        self.assertEqual(refused.status_code, 400)
        self.agent.workstream = User.Workstream.AFTER_SALES
        self.agent.save(update_fields=["workstream"])
        allowed = client.post("/api/v1/telephony/originate/", {"number": "09151234567"}, format="json")
        self.assertEqual(allowed.status_code, 202, allowed.content)
