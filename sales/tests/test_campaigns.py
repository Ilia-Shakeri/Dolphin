"""Campaigns as an entity (2.36.0): people, stages, attribution, analytics, migration."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice
from billing.services import cancel_invoice, create_invoice, issue_invoice
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.campaign_analytics import campaign_analysis, campaign_rows, campaigns_for
from sales.campaign_attribution import attribute_manually
from sales.campaign_migration import run_migration
from sales.campaigns import (
    add_campaign_member,
    assign_campaign_member,
    create_campaign,
    ensure_system_campaigns,
    set_campaign_status,
    set_member_stage,
    update_campaign,
)
from sales.models import Campaign, CampaignAttribution, CampaignAttributionLog, Lead, TargetAudienceMember
from sales.services import (
    add_target_audience_member,
    create_customer_with_phone,
    create_lead,
    create_product,
    record_interaction,
)

PASSWORD = "Strong-pass-937!"


class Fixtures(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="camp.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="camp.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other_agent = User.objects.create_user(username="camp.agent2", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.campaign = create_campaign(actor=self.manager, name="نوروز", responsibles=[self.agent])

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def member(self, phone="09121110001", name="مخاطب", campaign=None, **extra):
        return add_campaign_member(
            actor=self.manager, campaign=campaign or self.campaign, full_name=name, raw_phone=phone, **extra
        )


class CampaignServiceTests(Fixtures):
    def test_only_a_manager_manages_campaigns(self):
        with self.assertRaises(BusinessPermissionDenied):
            create_campaign(actor=self.agent, name="x")
        self.assertEqual(self.client_for(self.agent).post("/api/v1/campaigns/", {"name": "y"}, format="json").status_code, 403)

    def test_names_are_unique_across_spellings(self):
        with self.assertRaises(BusinessConflictError):
            create_campaign(actor=self.manager, name=" نوروز  ")
        with self.assertRaises(BusinessRuleError):
            create_campaign(actor=self.manager, name="   ")

    def test_dates_and_numbers_are_validated(self):
        from datetime import date

        with self.assertRaises(BusinessRuleError):
            create_campaign(actor=self.manager, name="a", starts_on=date(2026, 5, 2), ends_on=date(2026, 5, 1))
        with self.assertRaises(BusinessRuleError):
            create_campaign(actor=self.manager, name="b", budget=Decimal("-1"))

    def test_status_follows_its_transitions(self):
        set_campaign_status(actor=self.manager, campaign=self.campaign, status="active")
        with self.assertRaises(BusinessConflictError):
            set_campaign_status(actor=self.manager, campaign=self.campaign, status="draft")
        set_campaign_status(actor=self.manager, campaign=self.campaign, status="finished")
        set_campaign_status(actor=self.manager, campaign=self.campaign, status="archived")
        with self.assertRaises(BusinessConflictError):
            set_campaign_status(actor=self.manager, campaign=self.campaign, status="active")

    def test_system_campaigns_exist_once_and_keep_their_name(self):
        made = ensure_system_campaigns(self.manager)
        again = ensure_system_campaigns(self.manager)
        self.assertEqual({k: c.pk for k, c in made.items()}, {k: c.pk for k, c in again.items()})
        with self.assertRaises(BusinessRuleError):
            update_campaign(actor=self.manager, campaign=made["direct"], name="چیز دیگر")
        with self.assertRaises(BusinessConflictError):
            set_campaign_status(actor=self.manager, campaign=made["legacy"], status="archived")

    def test_one_phone_may_sit_in_two_campaigns_but_not_twice_in_one(self):
        other = create_campaign(actor=self.manager, name="یلدا")
        first = self.member("09121110001")
        second = self.member("09121110001", campaign=other)
        self.assertNotEqual(first.pk, second.pk)
        with self.assertRaises(BusinessConflictError):
            self.member("09121110001")

    def test_members_belong_to_the_campaigns_hidden_container(self):
        member = self.member()
        self.assertEqual(member.lead.campaign, self.campaign)
        self.assertEqual(member.campaign, self.campaign)
        self.assertEqual(Lead.objects.filter(campaign=self.campaign, source="campaign").count(), 1)
        self.member("09121110002", name="دوم")
        self.assertEqual(Lead.objects.filter(campaign=self.campaign, source="campaign").count(), 1)

    def test_a_marketer_cannot_add_people_and_a_manager_assigns_them(self):
        with self.assertRaises(BusinessPermissionDenied):
            add_campaign_member(actor=self.agent, campaign=self.campaign, full_name="x", raw_phone="09121110003")
        member = self.member()
        assign_campaign_member(actor=self.manager, member=member, to_user=self.agent)
        member.refresh_from_db()
        self.assertEqual(member.assigned_to, self.agent)
        with self.assertRaises(BusinessPermissionDenied):
            assign_campaign_member(actor=self.agent, member=member, to_user=self.other_agent)

    def test_stages_are_set_by_hand_only_where_a_person_may_and_converted_never(self):
        member = self.member()
        assign_campaign_member(actor=self.manager, member=member, to_user=self.agent)
        with self.assertRaises(BusinessPermissionDenied):
            set_member_stage(actor=self.other_agent, member=member, stage="engaged")
        set_member_stage(actor=self.agent, member=member, stage="engaged")
        with self.assertRaises(BusinessRuleError):
            set_member_stage(actor=self.agent, member=member, stage="converted")
        with self.assertRaises(BusinessRuleError):
            set_member_stage(actor=self.agent, member=member, stage="lost")  # no reason
        set_member_stage(actor=self.agent, member=member, stage="lost", lost_reason="جواب نداد")
        member.refresh_from_db()
        self.assertEqual((member.stage, member.lost_reason), ("lost", "جواب نداد"))

    def test_the_first_call_moves_a_new_person_to_contacted(self):
        member = self.member()
        lead = member.lead
        record_interaction(
            actor=self.manager, lead=lead, target_member=member, phone=member.raw_phone,
            direction="outbound", outcome="پاسخ داد", occurred_at=timezone.now(),
        )
        member.refresh_from_db()
        self.assertEqual(member.stage, "contacted")

    def test_a_marketer_sees_only_their_own_people_and_campaigns(self):
        mine = self.member("09121110001")
        theirs = self.member("09121110002", name="دیگری")
        assign_campaign_member(actor=self.manager, member=mine, to_user=self.agent)
        assign_campaign_member(actor=self.manager, member=theirs, to_user=self.other_agent)
        api = self.client_for(self.agent)
        listing = api.get(f"/api/v1/campaigns/{self.campaign.pk}/members/")
        self.assertEqual([row["id"] for row in listing.data["results"]], [mine.pk])
        self.assertEqual(api.post(f"/api/v1/campaign-members/{theirs.pk}/stage/", {"stage": "engaged"}, format="json").status_code, 404)
        stranger = Campaign.objects.get(pk=create_campaign(actor=self.manager, name="بی‌ربط").pk)
        self.assertNotIn(stranger, campaigns_for(self.agent))
        self.assertIn(self.campaign, campaigns_for(self.agent))

    def test_the_feature_gate_closes_the_api(self):
        features = frozenset(ALL_FEATURES) - {"campaigns"}
        with override_active_profile(DeploymentProfile(profile_id="x", features=features, source="signed-manifest")):
            self.assertEqual(self.client_for(self.manager).get("/api/v1/campaigns/").status_code, 404)

    def test_legacy_audience_api_still_rejects_a_duplicate_phone_without_a_campaign(self):
        lead = create_lead(actor=self.manager, campaign_or_batch="قدیمی")
        add_target_audience_member(actor=self.manager, lead=lead, full_name="الف", raw_phone="09121119999")
        other = create_lead(actor=self.manager, campaign_or_batch="قدیمی دو")
        with self.assertRaises(BusinessConflictError):
            add_target_audience_member(actor=self.manager, lead=other, full_name="ب", raw_phone="09121119999")


class AttributionTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.product = create_product(actor=self.manager, sku="CMP-1", name="کالا", current_price=Decimal("1000.00"))
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="خریدار", phone={"raw_phone": "09121110001", "is_primary": True}
        )

    def invoice(self, customer=None):
        return create_invoice(
            actor=self.manager, customer=customer or self.customer,
            items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        )

    def test_a_valid_invoice_converts_the_person_it_follows_and_cancelling_undoes_it(self):
        person = self.member("09121110001")
        # a person already in the book on entry is flagged, not converted
        self.assertTrue(person.was_customer_on_entry)
        invoice = issue_invoice(actor=self.manager, invoice=self.invoice())
        attribution = CampaignAttribution.objects.get(invoice=invoice)
        self.assertEqual((attribution.campaign, attribution.source), (self.campaign, "auto"))
        person.refresh_from_db()
        self.assertEqual(person.stage, "converted")
        self.assertIsNotNone(person.converted_at)

        cancel_invoice(actor=self.manager, invoice=invoice, reason="آزمون")
        person.refresh_from_db()
        self.assertNotEqual(person.stage, "converted")
        self.assertIsNone(person.converted_at)
        rows = campaign_rows(self.manager, ids=[self.campaign.pk])
        self.assertEqual(rows[0]["converted"], 0)
        self.assertEqual(rows[0]["valid_invoices_count"], 0)

    def test_a_draft_never_counts(self):
        self.member("09121110001")
        self.invoice()
        self.assertEqual(CampaignAttribution.objects.count(), 0)

    def test_last_touch_picks_the_most_recently_contacted_campaign(self):
        other = create_campaign(actor=self.manager, name="یلدا")
        first = self.member("09121110001")
        second = self.member("09121110001", campaign=other)
        record_interaction(
            actor=self.manager, lead=first.lead, target_member=first, phone=first.raw_phone,
            direction="outbound", outcome="الف", occurred_at=timezone.now() - timedelta(days=10),
        )
        record_interaction(
            actor=self.manager, lead=second.lead, target_member=second, phone=second.raw_phone,
            direction="outbound", outcome="ب", occurred_at=timezone.now() - timedelta(days=2),
        )
        invoice = issue_invoice(actor=self.manager, invoice=self.invoice())
        self.assertEqual(CampaignAttribution.objects.get(invoice=invoice).campaign, other)

    def test_an_old_touch_outside_the_window_is_not_attributed(self):
        person = self.member("09121110001")
        TargetAudienceMember.objects.filter(pk=person.pk).update(created_at=timezone.now() - timedelta(days=90))
        invoice = issue_invoice(actor=self.manager, invoice=self.invoice())
        self.assertFalse(CampaignAttribution.objects.filter(invoice=invoice).exists())

    def test_manual_attribution_needs_the_capability_a_reason_and_an_issued_invoice(self):
        draft = self.invoice()
        with self.assertRaises(BusinessPermissionDenied):
            attribute_manually(actor=self.agent, invoice=draft, campaign=self.campaign, reason="ر")
        with self.assertRaises(BusinessRuleError):
            attribute_manually(actor=self.manager, invoice=draft, campaign=self.campaign, reason=" ")
        with self.assertRaises(BusinessConflictError):
            attribute_manually(actor=self.manager, invoice=draft, campaign=self.campaign, reason="ر")
        issued = issue_invoice(actor=self.manager, invoice=draft)
        done = attribute_manually(actor=self.manager, invoice=issued, campaign=self.campaign, reason="ثبت دستی")
        self.assertEqual((done.campaign, done.source, done.attributed_by), (self.campaign, "manual", self.manager))
        other = create_campaign(actor=self.manager, name="دیگر")
        attribute_manually(actor=self.manager, invoice=issued, campaign=other, reason="اصلاح")
        self.assertEqual(CampaignAttributionLog.objects.filter(invoice=issued).count(), 2)
        issued.refresh_from_db()
        self.assertEqual(issued.status, Invoice.Status.ISSUED)  # the invoice itself is never touched

    def test_a_failure_in_attribution_never_blocks_issuing(self):
        from unittest import mock

        self.member("09121110001")
        with mock.patch("sales.campaign_attribution._candidates", side_effect=RuntimeError("boom")):
            with self.assertLogs("dolphin.campaigns", level="ERROR"):
                invoice = issue_invoice(actor=self.manager, invoice=self.invoice())
        self.assertEqual(invoice.status, Invoice.Status.ISSUED)

    def test_the_three_money_figures_stay_apart_and_unknowns_are_not_zero(self):
        person = self.member("09121110001")
        invoice = issue_invoice(actor=self.manager, invoice=self.invoice())
        row = campaign_rows(self.manager, ids=[self.campaign.pk])[0]
        self.assertEqual(row["valid_invoices_count"], 1)
        self.assertEqual(row["valid_invoices_amount"], invoice.total_amount)
        self.assertEqual(row["collected_amount"], Decimal("0.00"))
        self.assertEqual(row["registered_sales_count"], 0)
        empty = campaign_rows(self.manager, ids=[create_campaign(actor=self.manager, name="خالی").pk])[0]
        self.assertIsNone(empty["conversion_rate"])
        marketer_row = campaign_rows(self.agent, ids=[self.campaign.pk], with_money=False)
        self.assertNotIn("valid_invoices_amount", marketer_row[0])
        analysis = campaign_analysis(self.manager, ids=[self.campaign.pk])
        self.assertEqual([step["label"] for step in analysis["funnel"]][0], "اعضای کمپین")

    def test_api_analytics_export_and_attribution_are_manager_only(self):
        person = self.member("09121110001")
        invoice = issue_invoice(actor=self.manager, invoice=self.invoice())
        agent, manager = self.client_for(self.agent), self.client_for(self.manager)
        self.assertEqual(agent.get("/api/v1/campaigns/analytics/").status_code, 403)
        self.assertEqual(agent.get("/api/v1/campaigns/export/").status_code, 403)
        self.assertEqual(manager.get("/api/v1/campaigns/analytics/").status_code, 200)
        self.assertEqual(manager.get("/api/v1/campaigns/export/").status_code, 200)
        denied = agent.post("/api/v1/campaigns/attribute-invoice/", {"invoice": invoice.pk, "campaign": self.campaign.pk, "reason": "x"}, format="json")
        self.assertEqual(denied.status_code, 403)
        results = agent.get("/api/v1/campaigns/results/")
        self.assertEqual(results.status_code, 200)
        self.assertFalse(results.data["with_money"])


class MigrationTests(Fixtures):
    def test_dry_run_writes_nothing_and_apply_is_idempotent_and_keeps_near_misses_apart(self):
        a = create_lead(actor=self.manager, campaign_or_batch="بهار ۱۴۰۵")
        b = create_lead(actor=self.manager, campaign_or_batch="بهار 1405 ")
        c = create_lead(actor=self.manager, campaign_or_batch="پخش کننده")
        d = create_lead(actor=self.manager, campaign_or_batch="پخش‌کننده")
        blank = create_lead(actor=self.manager)
        for lead, phone in ((a, "09125550001"), (c, "09125550002"), (blank, "09125550003")):
            add_target_audience_member(actor=self.manager, lead=lead, full_name="م", raw_phone=phone)
        Lead.objects.update(assigned_to=None)
        before = Campaign.objects.count()
        out = StringIO()
        call_command("migrate_campaigns", "--dry-run", stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertEqual(Campaign.objects.count(), before)
        self.assertEqual(Lead.objects.filter(campaign__isnull=True).count(), 5)

        call_command("migrate_campaigns", stdout=StringIO())
        self.assertFalse(Lead.objects.filter(campaign__isnull=True).exists())
        self.assertFalse(TargetAudienceMember.objects.filter(campaign__isnull=True).exists())
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db(); d.refresh_from_db(); blank.refresh_from_db()
        self.assertEqual(a.campaign, b.campaign)
        self.assertNotEqual(c.campaign, d.campaign)
        self.assertEqual(blank.campaign.system_key, "legacy")
        self.assertEqual(a.campaign_or_batch, "بهار ۱۴۰۵")  # the old text is untouched
        again = run_migration(apply=True)
        self.assertEqual((again.campaigns_to_create, again.leads_to_link, again.members_to_migrate), (0, 0, 0))


class CampaignChannelsTests(Fixtures):
    def test_a_campaign_keeps_several_contact_channels_and_the_first_mirrors_the_legacy_column(self):
        campaign = create_campaign(actor=self.manager, name="چندراهه", channels=["sms", "exhibition", "sms"])
        self.assertEqual(campaign.channels, ["sms", "exhibition"])
        self.assertEqual(campaign.channel, "sms")
        update_campaign(actor=self.manager, campaign=campaign, channels=["website"])
        campaign.refresh_from_db()
        self.assertEqual((campaign.channels, campaign.channel), (["website"], "website"))

    def test_invalid_or_empty_channels_are_refused(self):
        for bad in ([], ["telegram"], "sms"):
            with self.assertRaises(BusinessRuleError):
                create_campaign(actor=self.manager, name="بد", channels=bad)

    def test_the_list_filters_by_any_of_a_campaigns_channels(self):
        create_campaign(actor=self.manager, name="الف", channels=["sms", "referral"])
        body = self.client_for(self.manager).get("/api/v1/campaigns/?channel=sms").json()
        self.assertEqual([row["name"] for row in body["results"]], ["الف"])


class AssignedMemberCallTests(Fixtures):
    def test_an_agent_can_log_a_call_on_a_person_assigned_to_them_and_the_follow_up_lands_on_that_person(self):
        from sales.campaigns import container_lead

        mine = self.member("09121110010", "من")
        other = self.member("09121110011", "دیگری")
        assign_campaign_member(actor=self.manager, member=mine, to_user=self.agent)
        mine.refresh_from_db()
        lead = container_lead(self.campaign, self.manager)
        when = timezone.now() + timedelta(days=2)
        record_interaction(
            actor=self.agent, lead=lead, target_member=mine, phone=mine.raw_phone, direction="outbound",
            outcome="پاسخ داد", occurred_at=timezone.now(), next_follow_up_at=when,
        )
        mine.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(mine.next_follow_up_at, when)
        self.assertIsNone(other.next_follow_up_at)
        with self.assertRaises(BusinessPermissionDenied):
            record_interaction(
                actor=self.agent, lead=lead, target_member=other, phone=other.raw_phone, direction="outbound",
                outcome="x", occurred_at=timezone.now(),
            )


class SubCampaignTests(Fixtures):
    def test_two_levels_only_and_names_are_unique_per_parent(self):
        child = create_campaign(actor=self.manager, name="اینستاگرام", parent=self.campaign)
        other = create_campaign(actor=self.manager, name="دیگر")
        create_campaign(actor=self.manager, name="اینستاگرام", parent=other)  # same name under another parent
        with self.assertRaises(BusinessConflictError):
            create_campaign(actor=self.manager, name="اینستاگرام", parent=self.campaign)
        with self.assertRaises(BusinessRuleError):
            create_campaign(actor=self.manager, name="سطح سوم", parent=child)

    def test_people_go_to_a_sub_campaign_and_the_parent_rolls_them_up_once(self):
        child = create_campaign(actor=self.manager, name="نمایشگاه", parent=self.campaign)
        add_campaign_member(actor=self.manager, campaign=child, full_name="الف", raw_phone="09121110021")
        with self.assertRaises(BusinessConflictError):
            add_campaign_member(actor=self.manager, campaign=self.campaign, full_name="ب", raw_phone="09121110022")
        rows = {row["id"]: row for row in campaign_rows(self.manager, ids=[self.campaign.pk])}
        self.assertEqual(rows[child.pk]["members"], 1)
        self.assertEqual(rows[self.campaign.pk]["members"], 1)
        self.assertEqual(rows[self.campaign.pk]["children_count"], 1)
        analysis = campaign_analysis(self.manager, ids=[self.campaign.pk])
        self.assertEqual(analysis["funnel"][0]["value"], 1)

    def test_a_parent_with_live_sub_campaigns_cannot_be_archived_and_budget_overshoot_only_warns(self):
        self.campaign.budget = Decimal("100")
        self.campaign.save()
        child = create_campaign(actor=self.manager, name="بزرگ", parent=self.campaign, budget=Decimal("500"))
        self.assertTrue(child.budget_warning)
        with self.assertRaises(BusinessConflictError):
            set_campaign_status(actor=self.manager, campaign=self.campaign, status="archived")


class EnsureCustomerTests(Fixtures):
    def test_a_person_becomes_a_customer_once_and_the_marketer_owns_the_record(self):
        from sales.campaigns import ensure_customer_for_member
        from sales.models import Customer

        person = self.member("09121110031", "خریدار")
        assign_campaign_member(actor=self.manager, member=person, to_user=self.agent)
        person.refresh_from_db()
        first = ensure_customer_for_member(actor=self.agent, member=person)
        again = ensure_customer_for_member(actor=self.agent, member=person)
        self.assertIsNotNone(first.customer_id)
        self.assertEqual(first.customer_id, again.customer_id)
        self.assertEqual(first.status, "customer")
        self.assertEqual(Customer.objects.filter(full_name="خریدار").count(), 1)
        self.assertEqual(Customer.objects.get(pk=first.customer_id).owner_id, self.agent.pk)

    def test_an_agent_cannot_convert_someone_elses_person(self):
        from sales.campaigns import ensure_customer_for_member

        person = self.member("09121110032", "دیگری")
        with self.assertRaises(BusinessPermissionDenied):
            ensure_customer_for_member(actor=self.agent, member=person)


class MemberReminderTests(Fixtures):
    def test_a_due_follow_up_on_an_assigned_person_reaches_that_marketers_bell_only(self):
        from common.reminders import _lead_reminders

        mine = self.member("09121110041", "پیگیری")
        assign_campaign_member(actor=self.manager, member=mine, to_user=self.agent)
        TargetAudienceMember.objects.filter(pk=mine.pk).update(next_follow_up_at=timezone.now() - timedelta(hours=1))
        group = _lead_reminders(self.agent, now=timezone.now())
        self.assertEqual(group["count"], 1)
        self.assertEqual(group["items"][0]["title"], "پیگیری")
        self.assertEqual(_lead_reminders(self.other_agent, now=timezone.now())["count"], 0)
