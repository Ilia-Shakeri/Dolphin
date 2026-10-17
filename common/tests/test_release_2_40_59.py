"""2.40.59 — one set of conversion definitions across Dolphin (BIZ-004).

Product owner, 2026-10-17: lead-to-sale = qualified leads that reached a valid
purchase ÷ the qualified leads of the group; resolution = leads closed won ÷
all leads closed in the period — a different measure; campaign sales = new
customers won through the campaign ÷ the campaign's qualified leads. The
denominator is qualified leads; groups are by entry date; the window is 30
days from the last relevant call and is set in Settings; repeat purchases are
apart; cancelling an invoice corrects the figures; every rate is shown with
its definition, numerator and denominator.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice
from billing.services import cancel_invoice, create_invoice, issue_invoice
from common import dashboard
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from reports.marketers import build_marketer_ranking
from sales import conversion
from sales.campaign_analytics import campaign_analysis, campaign_rows
from sales.campaigns import add_campaign_member, assign_campaign_member, create_campaign
from sales.models import Lead
from sales.pipeline import set_lead_stage
from sales.services import create_customer_with_phone, create_lead, create_product, record_interaction

PASSWORD = "Strong-pass-959!"


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="c.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="c.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="c.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.campaign = create_campaign(actor=self.manager, name="زمستان", responsibles=[self.agent])
        self.product = create_product(actor=self.manager, sku="CNV-1", name="کالا", current_price=Decimal("1000.00"))

    def customer(self, phone, name="خریدار"):
        return create_customer_with_phone(actor=self.manager, full_name=name, phone={"raw_phone": phone, "is_primary": True})

    def issued(self, customer):
        invoice = create_invoice(
            actor=self.manager, customer=customer,
            items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        )
        return issue_invoice(actor=self.manager, invoice=invoice)

    def lead_for(self, customer):
        return create_lead(actor=self.manager, customer=customer, campaign=self.campaign, assignee=self.agent, source="آزمون")

    def call(self, lead, *, qualified=False, days_ago=0, phone="09121110590"):
        return record_interaction(
            actor=self.manager, lead=lead, phone=phone, direction="outbound",
            result="interested" if qualified else "connected", qualified=qualified,
            occurred_at=timezone.now() - timedelta(days=days_ago),
        )


class DefinitionTests(Base):
    def test_four_figures_each_with_its_meaning_numerator_and_denominator(self):
        keys = [item["key"] for item in conversion.definitions()]
        self.assertEqual(keys, ["lead_to_sale", "resolution", "campaign_sales", "repeat"])
        figure = conversion.figure("lead_to_sale", 2, 5)
        self.assertEqual((figure["numerator"], figure["denominator"], figure["rate"]), (2, 5, Decimal("40.0")))
        self.assertIn("واجد شرایط", figure["definition"])
        self.assertIsNone(conversion.figure("resolution", 0, 0)["rate"])

    def test_the_window_is_the_companys_setting(self):
        from sales.campaign_attribution import window_days

        self.assertEqual(conversion.window_days(), 30)
        with self.assertRaises(BusinessPermissionDenied):
            conversion.update_settings(actor=self.manager, attribution_window_days=10)
        with self.assertRaises(BusinessRuleError):
            conversion.update_settings(actor=self.admin, attribution_window_days=0)
        with self.assertRaises(BusinessRuleError):
            conversion.update_settings(actor=self.admin, attribution_window_days=400)
        payload = conversion.update_settings(actor=self.admin, attribution_window_days=45)
        self.assertEqual((payload["attribution_window_days"], payload["is_default"]), (45, False))
        self.assertEqual(window_days(), 45)
        client = APIClient()
        client.force_authenticate(self.admin)
        self.assertEqual(client.patch("/api/v1/sales-settings/", {"attribution_window_days": 20}, format="json").json()["attribution_window_days"], 20)


class QualifiedTests(Base):
    def test_qualified_by_a_call_or_by_a_stage_reached(self):
        by_call = self.lead_for(self.customer("09121110591"))
        by_stage = self.lead_for(self.customer("09121110592"))
        left = self.lead_for(self.customer("09121110593"))
        plain = self.lead_for(self.customer("09121110594"))
        self.call(by_call, qualified=True, phone="09121110591")
        set_lead_stage(actor=self.manager, lead=by_stage, stage="quote_sent")
        set_lead_stage(actor=self.manager, lead=left, stage="qualified")
        set_lead_stage(actor=self.manager, lead=left, stage="needs_analysis")
        set_lead_stage(actor=self.manager, lead=plain, stage="first_contact")
        qualified = set(conversion.qualified_leads(Lead.objects.all()).values_list("pk", flat=True))
        self.assertEqual(qualified, {by_call.pk, by_stage.pk, left.pk})


class LeadToSaleTests(Base):
    def test_won_repeat_window_and_cancellation(self):
        new = self.customer("09121110595", "تازه")
        old = self.customer("09121110596", "قدیمی")
        late = self.customer("09121110597", "دیر")
        self.issued(old)  # a customer before the lead entered
        leads = [self.lead_for(customer) for customer in (new, old, late)]
        for lead, phone in zip(leads, ("09121110595", "09121110596", "09121110597")):
            self.call(lead, qualified=True, phone=phone)
        won_invoice = self.issued(new)
        self.issued(old)
        # The last call before the purchase is outside a 1-day window.
        Lead.objects.filter(pk=leads[2].pk).update(created_at=timezone.now() - timedelta(days=10))
        late_call = leads[2].interactions.get()
        type(late_call).objects.filter(pk=late_call.pk).update(occurred_at=timezone.now() - timedelta(days=5))
        conversion.update_settings(actor=self.admin, attribution_window_days=1)
        self.issued(late)

        figure, repeat = conversion.lead_to_sale(Lead.objects.filter(pk__in=[lead.pk for lead in leads]))
        self.assertEqual((figure["numerator"], figure["denominator"], repeat), (1, 3, 1))

        cancel_invoice(actor=self.manager, invoice=won_invoice, reason="اشتباه")
        figure, _ = conversion.lead_to_sale(Lead.objects.filter(pk__in=[lead.pk for lead in leads]))
        self.assertEqual((figure["numerator"], figure["denominator"]), (0, 3))

    def test_resolution_is_won_over_closed(self):
        leads = [self.lead_for(self.customer(f"0912111061{index}")) for index in range(3)]
        set_lead_stage(actor=self.manager, lead=leads[0], stage="won")
        set_lead_stage(actor=self.manager, lead=leads[1], stage="lost", lost_reason="price")
        figure = conversion.resolution(Lead.objects.all())
        self.assertEqual((figure["numerator"], figure["denominator"], figure["rate"]), (1, 2, Decimal("50.0")))


class CampaignTests(Base):
    def test_the_campaign_rate_is_over_qualified_people_with_repeats_apart(self):
        add_campaign_member(actor=self.manager, campaign=self.campaign, full_name="بی‌علاقه", raw_phone="09121110621")
        member = add_campaign_member(actor=self.manager, campaign=self.campaign, full_name="خریدار تازه", raw_phone="09121110620")
        member = assign_campaign_member(actor=self.manager, member=member, to_user=self.agent)
        record_interaction(
            actor=self.agent, lead=member.lead, target_member=member, phone="09121110620", direction="outbound",
            result="quote_requested", qualified=True, occurred_at=timezone.now(),
        )
        # Becomes a customer only now, after entering the campaign: a new customer.
        self.issued(self.customer("09121110620", "خریدار تازه"))
        member.refresh_from_db()
        self.assertEqual(member.stage, "converted")
        row = next(item for item in campaign_rows(self.manager) if item["id"] == self.campaign.pk)
        self.assertEqual((row["members"], row["qualified"], row["converted"]), (2, 1, 1))
        self.assertEqual((row["conversion"]["numerator"], row["conversion"]["denominator"]), (1, 1))
        self.assertEqual(row["conversion_rate"], 100.0)
        analysis = campaign_analysis(self.manager, ids=[self.campaign.pk])
        self.assertEqual(analysis["sales_rate"]["denominator"], 1)
        self.assertEqual(analysis["repeat_purchases"], 0)
        self.assertIsNotNone(analysis["days_to_convert"])


class ReportTests(Base):
    def test_the_dashboard_shows_both_rates_by_their_own_names(self):
        lead = self.lead_for(self.customer("09121110630"))
        set_lead_stage(actor=self.manager, lead=lead, stage="won")
        gauges = {gauge["key"]: gauge for gauge in dashboard.dashboard_for(self.manager)["gauges"]}
        self.assertEqual(gauges["lead_conversion_rate"]["label"], "نرخ تعیین تکلیف")
        self.assertIn("بسته", gauges["lead_conversion_rate"]["definition"])
        self.assertEqual(gauges["lead_to_sale_rate"]["label"], "نرخ تبدیل سرنخ به فروش")
        self.assertIn("از ۱ سرنخ واجد شرایط", gauges["lead_to_sale_rate"]["hint"])

    def test_the_marketers_report_carries_the_figures_and_their_meanings(self):
        customer = self.customer("09121110640")
        lead = self.lead_for(customer)
        self.call(lead, qualified=True, phone="09121110640")
        self.issued(customer)
        set_lead_stage(actor=self.manager, lead=lead, stage="won")
        now = timezone.now()
        report = build_marketer_ranking(actor=self.admin, period_start=now - timedelta(days=1), period_end=now + timedelta(minutes=1))
        row = next(item for item in report["results"] if item.user_id == self.agent.pk)
        self.assertEqual((row.won_leads, row.qualified_leads, row.conversion_rate), (1, 1, Decimal("100.0")))
        self.assertEqual((row.closed_won, row.closed_leads, row.resolution_rate), (1, 1, Decimal("100.0")))
        self.assertEqual(report["totals"]["lead_to_sale"]["denominator"], 1)
        self.assertEqual({item["key"] for item in report["definitions"]}, {"lead_to_sale", "resolution", "campaign_sales", "repeat"})
        client = APIClient()
        client.force_authenticate(self.admin)
        answer = client.get("/api/v1/reports/marketers/", {"period_start": (now - timedelta(days=1)).isoformat(), "period_end": (now + timedelta(minutes=1)).isoformat()})
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertIn("lead_to_sale", answer.json()["totals"])

    def test_the_profile_card_and_the_settings_name_the_resolution_rate(self):
        from profiles.cards import CARDS

        card = next(item for item in CARDS if item.key == "conversion" and item.person_type == "user")
        self.assertEqual(card.label, "نرخ تعیین تکلیف")
        self.client.force_login(self.admin)
        page = self.client.get("/settings/?tab=calls").content.decode()
        self.assertIn('id="sales-settings-form"', page)
        self.assertIn("تماس و تبدیل", page)

    def test_an_issued_invoice_is_the_only_purchase(self):
        customer = self.customer("09121110650")
        lead = self.lead_for(customer)
        self.call(lead, qualified=True, phone="09121110650")
        invoice = create_invoice(
            actor=self.manager, customer=customer,
            items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        )
        self.assertEqual(invoice.status, Invoice.Status.DRAFT)
        figure, _ = conversion.lead_to_sale(Lead.objects.filter(pk=lead.pk))
        self.assertEqual(figure["numerator"], 0)
