"""2.40.57 — lead and campaign-person stages (BIZ-002).

Product owner, 2026-10-17: default lead stages «جدید، تماس اولیه، نیازسنجی،
واجد شرایط، ارسال پیش‌فاکتور، مذاکره، برنده، بازنده», shaped per company; the
final two are final and leaving them needs a reason; skipping is allowed; a
lost stage needs a reason from a list («سایر» with a note); an agent moves
their own leads and a manager any; every move is in the history; one data
structure for leads and campaign people, a workflow each; a sale is a valid
invoice, never a stage set by hand.
"""

import importlib
from pathlib import Path

from django.apps import apps as django_apps
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales import pipeline
from sales.campaigns import add_campaign_member, assign_campaign_member, create_campaign
from sales.models import Lead, LostReason, PipelineStage, StageChange, TargetAudienceMember
from sales.services import create_customer_with_phone, create_lead, record_interaction, update_lead

PASSWORD = "Strong-pass-957!"
ROOT = Path(__file__).resolve().parents[2]


def without(feature):
    return DeploymentProfile(profile_id="client-1", features=frozenset(ALL_FEATURES) - {feature}, source="signed-manifest")


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="p.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="p.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="p.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other_agent = User.objects.create_user(username="p.agent2", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.campaign = create_campaign(actor=self.manager, name="بهار", responsibles=[self.agent])

    def lead(self, **extra):
        return create_lead(actor=self.manager, campaign=self.campaign, assignee=self.agent, source="آزمون", **extra)

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class DefaultsTests(Base):
    def test_the_owners_default_stages_and_reasons_are_seeded(self):
        lead = [(stage.key, stage.label, stage.kind) for stage in pipeline.stages("lead")]
        self.assertEqual([label for _, label, _ in lead], [
            "جدید", "تماس اولیه", "نیازسنجی", "واجد شرایط", "ارسال پیش‌فاکتور", "مذاکره", "برنده", "بازنده",
        ])
        self.assertEqual([kind for _, _, kind in lead][-2:], ["won", "lost"])
        campaign = [stage.key for stage in pipeline.stages("campaign")]
        self.assertEqual(campaign, ["new", "contacted", "engaged", "converted", "lost"])
        self.assertFalse(pipeline.stage_by_key("campaign")["converted"].manual)
        reasons = [(reason.label, reason.needs_note) for reason in pipeline.lost_reasons()]
        self.assertEqual([label for label, _ in reasons], [
            "قیمت نامناسب", "خرید از رقیب", "عدم نیاز", "عدم پاسخ‌گویی پس از پیگیری‌های لازم",
            "نامعتبر بودن اطلاعات", "لغو خرید", "سایر",
        ])
        self.assertEqual(reasons[-1], ("سایر", True))
        self.assertEqual(pipeline.qualifying_keys("lead"), {"qualified", "quote_sent", "negotiation", "won"})

    def test_an_emptied_table_is_seeded_again(self):
        StageChange.objects.all().delete()
        PipelineStage.objects.all().delete()
        LostReason.objects.all().delete()
        self.assertEqual(len(pipeline.stages("lead")), 8)
        self.assertEqual(len(pipeline.lost_reasons()), 7)


class LeadStageTests(Base):
    def test_a_new_lead_starts_at_the_first_open_stage_or_a_chosen_open_one(self):
        lead = self.lead()
        self.assertEqual((lead.stage, lead.status), ("new", Lead.Status.PENDING))
        started = self.lead(stage="quote_sent")
        self.assertEqual(started.stage, "quote_sent")
        with self.assertRaises(BusinessRuleError):
            self.lead(stage="won")
        # Starting is not a move, so a lead made by mistake can still be deleted.
        self.assertFalse(StageChange.objects.filter(lead=lead).exists())

    def test_skipping_is_allowed_and_status_follows_the_kind(self):
        lead = self.lead()
        moved = pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="negotiation")
        self.assertEqual((moved.stage, moved.status, moved.closed_at), ("negotiation", "pending", None))
        won = pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="won")
        self.assertEqual(won.status, Lead.Status.COMPLETED)
        self.assertIsNotNone(won.closed_at)

    def test_lost_needs_a_reason_from_the_list_and_other_a_note(self):
        lead = self.lead()
        with self.assertRaises(BusinessRuleError):
            pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="lost")
        with self.assertRaises(BusinessRuleError):
            pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="lost", lost_reason="free text")
        with self.assertRaises(BusinessRuleError):
            pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="lost", lost_reason="other")
        lost = pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="lost", lost_reason="other", note="بودجه ندارد")
        self.assertEqual((lost.status, lost.lost_reason_key, lost.lost_reason), ("cancelled", "other", "بودجه ندارد"))

    def test_leaving_a_final_stage_needs_a_reason_and_is_marked_reopened(self):
        lead = self.lead()
        pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="lost", lost_reason="price")
        with self.assertRaises(BusinessRuleError):
            pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="first_contact")
        back = pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="first_contact", reason="مشتری دوباره تماس گرفت")
        self.assertEqual((back.stage, back.status, back.lost_reason_key, back.closed_at), ("first_contact", "pending", "", None))
        last = StageChange.objects.filter(lead=lead).first()
        self.assertTrue(last.reopened)
        self.assertEqual((last.from_label, last.to_label, last.reason), ("بازنده", "تماس اولیه", "مشتری دوباره تماس گرفت"))
        with self.assertRaises(BusinessConflictError):
            pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="first_contact")

    def test_every_move_is_in_the_history_and_the_audit_log(self):
        lead = self.lead()
        pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="first_contact")
        pipeline.set_lead_stage(actor=self.manager, lead=lead, stage="lost", lost_reason="competitor")
        rows = list(pipeline.history_for_lead(lead))
        self.assertEqual([(row.to_stage, row.actor_id) for row in rows], [("lost", self.manager.pk), ("first_contact", self.agent.pk)])
        self.assertEqual(rows[0].lost_reason_label, "خرید از رقیب")
        self.assertEqual(ActivityLog.objects.filter(operation="lead.stage_changed", object_id=str(lead.pk)).count(), 2)

    def test_an_agent_moves_only_their_own_leads_and_a_manager_any(self):
        lead = self.lead()
        with self.assertRaises(BusinessPermissionDenied):
            pipeline.set_lead_stage(actor=self.other_agent, lead=lead, stage="first_contact")
        pipeline.set_lead_stage(actor=self.manager, lead=lead, stage="first_contact")
        mine = create_lead(actor=self.other_agent, campaign=None, assignee=None, source="خودم")
        pipeline.set_lead_stage(actor=self.other_agent, lead=mine, stage="first_contact")

    def test_a_stage_turned_off_takes_no_new_moves_but_keeps_its_leads(self):
        lead = self.lead()
        pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="needs_analysis")
        stage = PipelineStage.objects.get(pipeline="lead", key="needs_analysis")
        pipeline.update_stage(actor=self.admin, stage=stage, is_active=False)
        lead.refresh_from_db()
        self.assertEqual(lead.stage, "needs_analysis")
        other = self.lead()
        with self.assertRaises(BusinessRuleError):
            pipeline.set_lead_stage(actor=self.agent, lead=other, stage="needs_analysis")

    def test_the_old_status_field_is_not_written_any_more(self):
        lead = self.lead()
        with self.assertRaises(BusinessRuleError):
            update_lead(actor=self.manager, lead=lead, status=Lead.Status.COMPLETED)


class LeadApiTests(Base):
    def test_the_stage_action_history_and_filter(self):
        lead = self.lead()
        client = self.api(self.agent)
        moved = client.post(f"/api/v1/leads/{lead.pk}/stage/", {"stage": "qualified"}, format="json")
        self.assertEqual(moved.status_code, 200, moved.content)
        body = moved.json()
        self.assertEqual((body["stage"], body["stage_display"], body["stage_kind"], body["status"]),
                         ("qualified", "واجد شرایط", "open", "pending"))
        refused = client.post(f"/api/v1/leads/{lead.pk}/stage/", {"stage": "lost", "lost_reason": "other"}, format="json")
        self.assertEqual(refused.status_code, 400)
        self.assertIn("note", refused.json()["errors"] if "errors" in refused.json() else refused.json())
        history = client.get(f"/api/v1/leads/{lead.pk}/stage-history/").json()
        self.assertEqual(history["results"][0]["to_label"], "واجد شرایط")
        listed = client.get("/api/v1/leads/?stage=qualified").json()
        self.assertEqual([row["id"] for row in listed["results"]], [lead.pk])
        self.assertEqual(client.get("/api/v1/leads/?stage=nonsense").status_code, 400)
        self.assertEqual(client.patch(f"/api/v1/leads/{lead.pk}/", {"stage": "won"}, format="json").status_code, 400)
        self.assertEqual(client.patch(f"/api/v1/leads/{lead.pk}/", {"status": "completed"}, format="json").status_code, 400)
        self.assertEqual(self.api(self.other_agent).post(f"/api/v1/leads/{lead.pk}/stage/", {"stage": "won"}, format="json").status_code, 404)


class CampaignMemberTests(Base):
    def member(self):
        member = add_campaign_member(actor=self.manager, campaign=self.campaign, full_name="مخاطب", raw_phone="09121110057")
        return assign_campaign_member(actor=self.manager, member=member, to_user=self.agent)

    def test_the_campaign_workflow_uses_the_same_rules(self):
        member = self.member()
        with self.assertRaises(BusinessRuleError):
            pipeline.set_member_stage(actor=self.agent, member=member, stage="converted")
        pipeline.set_member_stage(actor=self.agent, member=member, stage="lost", lost_reason="no_need")
        with self.assertRaises(BusinessRuleError):
            pipeline.set_member_stage(actor=self.agent, member=member, stage="engaged")
        back = pipeline.set_member_stage(actor=self.agent, member=member, stage="engaged", reason="اشتباه ثبت شده بود")
        self.assertEqual(back.stage, "engaged")
        self.assertEqual([row.to_stage for row in pipeline.history_for_member(member)], ["engaged", "lost"])

    def test_the_first_call_writes_its_move_into_the_history(self):
        member = self.member()
        record_interaction(
            actor=self.agent, lead=member.lead, target_member=member, phone="09121110057", direction="outbound",
            result="connected", outcome="پاسخ داد", occurred_at=member.created_at,
        )
        member.refresh_from_db()
        self.assertEqual(member.stage, "contacted")
        change = StageChange.objects.get(member=member)
        self.assertEqual((change.source, change.actor_id, change.to_label), ("contact", None, "تماس گرفته‌شده"))

    def test_a_company_stage_shows_in_the_list_and_its_filter(self):
        stage = pipeline.create_stage(actor=self.admin, pipeline="campaign", label="پیش‌فاکتور خواست")
        member = self.member()
        pipeline.set_member_stage(actor=self.agent, member=member, stage=stage.key)
        client = self.api(self.manager)
        rows = client.get(f"/api/v1/campaigns/{self.campaign.pk}/members/?stage={stage.key}").json()["results"]
        self.assertEqual([(row["stage"], row["stage_display"]) for row in rows], [(stage.key, "پیش‌فاکتور خواست")])


class ConfigurationTests(Base):
    def test_shaping_the_lists_needs_the_feature_and_the_capability(self):
        with self.assertRaises(BusinessPermissionDenied):
            pipeline.create_stage(actor=self.manager, pipeline="lead", label="x")
        with override_active_profile(without("customization")):
            with self.assertRaises(BusinessPermissionDenied):
                pipeline.create_stage(actor=self.admin, pipeline="lead", label="x")
            self.assertEqual(self.api(self.admin).get("/api/v1/pipeline/").status_code, 404)
        self.assertEqual(self.api(self.manager).get("/api/v1/pipeline/").status_code, 403)
        self.assertEqual(self.api(self.admin).get("/api/v1/pipeline/").status_code, 200)

    def test_a_new_stage_lands_after_the_last_open_one_and_the_finals_stay_last(self):
        created = pipeline.create_stage(actor=self.admin, pipeline="lead", label="ارسال نمونه", qualifies=True)
        self.assertEqual(created.key, "c1")
        keys = [stage.key for stage in pipeline.stages("lead")]
        self.assertEqual(keys[-3:], ["c1", "won", "lost"])
        pipeline.move_stage(actor=self.admin, stage=created, direction="down")
        self.assertEqual([stage.key for stage in pipeline.stages("lead")][-3:], ["c1", "won", "lost"])
        pipeline.move_stage(actor=self.admin, stage=created, direction="up")
        self.assertEqual([stage.key for stage in pipeline.stages("lead")][-4:], ["c1", "negotiation", "won", "lost"])
        with self.assertRaises(BusinessRuleError):
            pipeline.move_stage(actor=self.admin, stage=PipelineStage.objects.get(pipeline="lead", key="won"), direction="up")
        with self.assertRaises(BusinessRuleError):
            pipeline.create_stage(actor=self.admin, pipeline="lead", label=" ارسال  نمونه ")

    def test_the_finals_and_the_last_open_stage_stay_on(self):
        won = PipelineStage.objects.get(pipeline="lead", key="won")
        with self.assertRaises(BusinessRuleError):
            pipeline.update_stage(actor=self.admin, stage=won, is_active=False)
        pipeline.update_stage(actor=self.admin, stage=won, label="فروخته شد")
        open_stages = [stage for stage in pipeline.stages("lead") if stage.kind == "open"]
        for stage in open_stages[:-1]:
            pipeline.update_stage(actor=self.admin, stage=stage, is_active=False)
        with self.assertRaises(BusinessRuleError):
            pipeline.update_stage(actor=self.admin, stage=open_stages[-1], is_active=False)
        # A new lead starts at the one open stage still on.
        self.assertEqual(self.lead().stage, open_stages[-1].key)

    def test_reasons_are_added_before_other_which_stays_on(self):
        added = pipeline.create_lost_reason(actor=self.admin, label="زمان نامناسب")
        self.assertEqual([reason.key for reason in pipeline.lost_reasons()][-2:], [added.key, "other"])
        other = LostReason.objects.get(key="other")
        with self.assertRaises(BusinessRuleError):
            pipeline.update_lost_reason(actor=self.admin, reason=other, is_active=False)
        with self.assertRaises(BusinessRuleError):
            pipeline.update_lost_reason(actor=self.admin, reason=other, needs_note=False)
        pipeline.update_lost_reason(actor=self.admin, reason=added, is_active=False)
        lead = self.lead()
        with self.assertRaises(BusinessRuleError):
            pipeline.set_lead_stage(actor=self.agent, lead=lead, stage="lost", lost_reason=added.key)

    def test_the_api_and_the_settings_tab(self):
        client = self.api(self.admin)
        created = client.post("/api/v1/pipeline/stages/", {"pipeline": "lead", "label": "دمو"}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        stage = next(item for item in created.json()["stages"]["lead"] if item["label"] == "دمو")
        changed = client.patch(f"/api/v1/pipeline/stages/{stage['id']}/", {"qualifies": True}, format="json")
        self.assertTrue(next(item for item in changed.json()["stages"]["lead"] if item["id"] == stage["id"])["qualifies"])
        self.assertEqual(client.post(f"/api/v1/pipeline/stages/{stage['id']}/move/", {"direction": "sideways"}, format="json").status_code, 400)
        reason = client.post("/api/v1/pipeline/lost-reasons/", {"label": "بدقولی"}, format="json")
        self.assertEqual(reason.status_code, 201)
        self.client.force_login(self.admin)
        page = self.client.get("/settings/?tab=customization").content.decode()
        self.assertIn('id="pipeline-stages-body"', page)
        self.assertIn('id="lost-reasons-body"', page)


class MigrationTests(Base):
    def test_existing_leads_are_moved_by_what_their_status_meant(self):
        migration = importlib.import_module("sales.migrations.0038_seed_pipeline_stages")
        customer = create_customer_with_phone(
            actor=self.manager, full_name="قدیمی", phone={"raw_phone": "09121110058", "is_primary": True},
        )
        pending = self.lead()
        called = create_lead(actor=self.manager, customer=customer, campaign=self.campaign, assignee=self.agent, source="آزمون")
        record_interaction(
            actor=self.manager, lead=called, phone="09121110058", direction="outbound",
            result="connected", outcome="پاسخ داد", occurred_at=called.created_at,
        )
        done = self.lead()
        cancelled = self.lead()
        Lead.objects.filter(pk__in=[pending.pk, called.pk, done.pk, cancelled.pk]).update(stage="new")
        Lead.objects.filter(pk=done.pk).update(status="completed")
        Lead.objects.filter(pk=cancelled.pk).update(status="cancelled")
        migration.forward(django_apps, None)
        stages = dict(Lead.objects.filter(pk__in=[pending.pk, called.pk, done.pk, cancelled.pk]).values_list("pk", "stage"))
        self.assertEqual(
            [stages[pending.pk], stages[called.pk], stages[done.pk], stages[cancelled.pk]],
            ["new", "first_contact", "won", "lost"],
        )
        cancelled.refresh_from_db()
        self.assertEqual((cancelled.lost_reason_key, cancelled.lost_reason), ("other", migration.CANCELLED_NOTE))
        # Its own seeding is idempotent.
        self.assertEqual(PipelineStage.objects.filter(pipeline="lead").count(), 8)


class PageTests(Base):
    def test_the_pages_carry_the_workflows_and_the_dialog(self):
        self.client.force_login(self.manager)
        lead = self.lead()
        # Where a stage is moved; the list only filters by it, from the same table.
        for path in (f"/leads/{lead.pk}/", f"/campaigns/{self.campaign.pk}/"):
            page = self.client.get(path).content.decode()
            self.assertIn('id="pipeline-config"', page, path)
        detail = self.client.get(f"/leads/{lead.pk}/").content.decode()
        self.assertIn('id="stage-change-dialog"', detail)
        self.assertIn('id="lead-stage-card"', detail)
        listing = self.client.get("/leads/").content.decode()
        self.assertIn('id="lead-stage-filter"', listing)
        self.assertNotIn('name="status"', listing)

    def test_the_script_asks_for_what_a_move_needs(self):
        script = (ROOT / "common" / "static" / "common" / "js" / "ui" / "pipeline.js").read_text(encoding="utf-8")
        self.assertIn('target?.kind === "lost"', script)
        self.assertIn('current.kind !== "open"', script)
        self.assertIn("lost_reason", script)
