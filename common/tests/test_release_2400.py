"""2.40.0 — the business flow end to end, and the rules that close its gaps.

The flow test is the product owner's five steps as one marketer and one
manager would live them, through the API wherever the panel uses the API.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice, Order, Payment, PaymentAllocation
from billing.payments import allocate_payment_across, register_payment
from billing.services import (
    _number_clash_kind,
    cancel_invoice,
    create_fulfillment_request,
    create_invoice,
    issue_invoice,
    record_manual_paid_entry,
    transition_order,
)
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from common.search import search
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.campaign_analytics import campaign_analysis, campaign_rows, unattributed_row
from sales.campaigns import add_campaign_member, assign_campaign_member, create_campaign
from sales.models import Customer, Interaction, Lead, TargetAudienceMember
from sales.selectors import work_leads_for
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-937!"


class Day(TestCase):
    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(username="d.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.marketer = User.objects.create_user(username="d.marketer", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other = User.objects.create_user(username="d.other", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.product = create_product(actor=self.manager, sku="D-1", name="کالا", current_price=Decimal("5000000.00"))
        self.warehouse = create_warehouse(actor=self.manager, code="dwh", name="انبار")
        record_stock_movement(
            actor=self.manager, warehouse=self.warehouse, product=self.product,
            movement_type=StockMovement.MovementType.OPENING, quantity=100, unit_cost=Decimal("3000000.00"),
        )

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class BusinessFlowTests(Day):
    def test_the_five_steps(self):
        manager, marketer = self.api(self.manager), self.api(self.marketer)
        # 1. a campaign with two sub-campaigns and three contact ways
        summer = manager.post("/api/v1/campaigns/", {"name": "تابستان", "channels": ["phone", "sms", "social"]}, format="json")
        self.assertEqual(summer.status_code, 201, summer.content)
        parent_id = summer.json()["id"]
        children = [
            manager.post("/api/v1/campaigns/", {"name": name, "parent": parent_id, "channels": ["social"]}, format="json").json()["id"]
            for name in ("اینستاگرام", "نمایشگاه")
        ]
        # 2. twenty people, ten for the marketer
        from sales.models import Campaign

        people = []
        for number in range(20):
            campaign = Campaign.objects.get(pk=children[number % 2])
            people.append(add_campaign_member(
                actor=self.manager, campaign=campaign, full_name=f"شخص {number}", raw_phone=f"0912555{number:04d}"
            ))
        for person in people[:10]:
            assign_campaign_member(actor=self.manager, member=person, to_user=self.marketer)
        # 3. the marketer sees only their ten and logs a call through the API
        seen = marketer.get(f"/api/v1/campaigns/{children[0]}/members/").json()
        self.assertTrue(all(row["assigned_to"] == self.marketer.pk for row in seen["results"]))
        mine = people[0]
        call = marketer.post("/api/v1/interactions/", {
            "target_member": mine.pk, "phone": mine.raw_phone, "direction": "outbound",
            "outcome": "پاسخ داد", "occurred_at": timezone.now().isoformat(),
        }, format="json")
        self.assertEqual(call.status_code, 201, call.content)
        self.assertEqual(marketer.get(f"/api/v1/interactions/{call.json()['id']}/").status_code, 200)
        # 4. an invoice made by picking the campaign person: they become a customer, once
        invoices = []
        for person in people[:3]:
            created = marketer.post("/api/v1/invoices/", {
                "campaign_member": person.pk, "warehouse": self.warehouse.pk,
                "items": [{"product": self.product.pk, "quantity": 1, "unit_price": "5000000.00"}],
            }, format="json")
            self.assertEqual(created.status_code, 201, created.content)
            invoices.append(issue_invoice(actor=self.manager, invoice=Invoice.objects.get(pk=created.json()["id"])))
        self.assertEqual(Customer.objects.filter(phones__normalized_phone=mine.normalized_phone).count(), 1)
        mine.refresh_from_db()
        self.assertIsNotNone(mine.customer_id)
        self.assertEqual(invoices[0].campaign_attribution.campaign_id, children[0])
        # results close to the company's totals with «بدون کمپین» and «مانده»
        stray = create_customer_with_phone(actor=self.manager, full_name="خارج از کمپین", phone={"raw_phone": "09121119999"})
        issue_invoice(actor=self.manager, invoice=create_invoice(
            actor=self.manager, customer=stray,
            items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        ))
        results = manager.get("/api/v1/campaigns/results/").json()["results"]
        top = [row for row in results if row["parent_id"] is None]
        company = sum((invoice.total_amount for invoice in Invoice.objects.filter(status="issued")), Decimal("0"))
        self.assertEqual(sum(Decimal(row["valid_invoices_amount"]) for row in top), company)
        none_row = next(row for row in results if row.get("unattributed"))
        self.assertEqual(Decimal(none_row["remaining_amount"]), Decimal(none_row["valid_invoices_amount"]))
        # 5. the marketer files one supply document for three of their invoices
        batch = marketer.post("/api/v1/orders/from-invoices/", {
            "invoices": [invoice.pk for invoice in invoices], "warehouse": self.warehouse.pk,
        }, format="json")
        self.assertEqual(batch.status_code, 201, batch.content)
        self.assertEqual(len({row["batch_number"] for row in batch.json()["orders"]}), 1)
        # finance: 20M as 4 x 5M to one invoice; a resend makes nothing new
        target = Invoice.objects.get(pk=invoices[1].pk)
        receipt = register_payment(actor=self.manager, customer=target.customer, method=Payment.Method.CASH, amount=Decimal("5000000.00"))
        for index in range(4):
            body = {"splits": [{"invoice": target.pk, "amount": "1250000.00"}], "request_key": f"k{index}"}
            self.assertEqual(manager.post(f"/api/v1/payments/{receipt.pk}/allocate-across/", body, format="json").status_code, 201)
        again = manager.post(f"/api/v1/payments/{receipt.pk}/allocate-across/", body, format="json")
        self.assertEqual(again.status_code, 201)
        self.assertEqual(PaymentAllocation.objects.filter(payment=receipt).count(), 4)
        target.refresh_from_db()
        self.assertEqual(target.balance_due, Decimal("0.00"))
        with self.assertRaises(BusinessConflictError):
            cancel_invoice(actor=self.manager, invoice=target, reason="آزمون")


class CampaignGapTests(Day):
    def test_container_leads_never_leak_into_lead_lists_or_search(self):
        campaign = create_campaign(actor=self.manager, name="بهار")
        add_campaign_member(actor=self.manager, campaign=campaign, full_name="علی", raw_phone="09125550101")
        self.assertTrue(Lead.objects.filter(source="campaign").exists())
        self.assertFalse(work_leads_for(self.manager).filter(source="campaign").exists())
        listed = self.api(self.manager).get("/api/v1/leads/").json()["results"]
        self.assertFalse([row for row in listed if row["source"] == "campaign"])
        kinds = [group["kind"] for group in search(self.manager, "علی")["groups"]]
        self.assertIn("campaign_members", kinds)
        self.assertNotIn("leads", kinds)

    def test_a_marketer_finds_only_their_own_people(self):
        campaign = create_campaign(actor=self.manager, name="بهار")
        mine = add_campaign_member(actor=self.manager, campaign=campaign, full_name="رضا یک", raw_phone="09125550102")
        add_campaign_member(actor=self.manager, campaign=campaign, full_name="رضا دو", raw_phone="09125550103")
        assign_campaign_member(actor=self.manager, member=mine, to_user=self.marketer)
        group = next(g for g in search(self.marketer, "رضا")["groups"] if g["kind"] == "campaign_members")
        self.assertEqual([item["title"] for item in group["items"]], ["رضا یک"])

    def test_a_campaign_with_people_cannot_take_children_and_three_levels_are_refused_anywhere(self):
        parent = create_campaign(actor=self.manager, name="والد")
        add_campaign_member(actor=self.manager, campaign=parent, full_name="الف", raw_phone="09125550104")
        with self.assertRaises(BusinessConflictError):
            create_campaign(actor=self.manager, name="فرزند", parent=parent)
        empty = create_campaign(actor=self.manager, name="خالی")
        child = create_campaign(actor=self.manager, name="فرزند", parent=empty)
        from sales.models import Campaign

        third = Campaign(name="نوه", normalized_name="نوه", parent=child, created_by=self.manager, updated_by=self.manager)
        with self.assertRaises(BusinessRuleError):
            third.save()

    def test_a_parent_without_its_own_target_rolls_its_childrens_up(self):
        parent = create_campaign(actor=self.manager, name="والد")
        create_campaign(actor=self.manager, name="الف", parent=parent, target_count=10, budget=Decimal("100"))
        create_campaign(actor=self.manager, name="ب", parent=parent, target_count=30, budget=Decimal("50"))
        row = next(row for row in campaign_rows(self.manager) if row["id"] == parent.pk)
        self.assertEqual((row["target_count"], row["budget"]), (40, Decimal("150")))

    def test_the_funnel_never_grows_and_ends_in_money(self):
        campaign = create_campaign(actor=self.manager, name="قیف")
        person = add_campaign_member(actor=self.manager, campaign=campaign, full_name="ب", raw_phone="09125550105")
        TargetAudienceMember.objects.filter(pk=person.pk).update(stage="converted")  # stage without any call
        steps = [step["value"] for step in campaign_analysis(self.manager, ids=[campaign.pk])["funnel"]]
        self.assertEqual(len(steps), 6)
        self.assertEqual(steps, sorted(steps, reverse=True))
        self.assertEqual(steps[3], 0)  # converted but never contacted cannot pass «contacted»

    def test_months_without_invoices_appear_as_zero(self):
        from sales.campaign_analytics import _jalali_month_series
        from sales.models import CampaignAttribution

        series = _jalali_month_series(
            CampaignAttribution.objects.none(),
            date_from=timezone.localdate() - timedelta(days=95), date_to=timezone.localdate(),
        )
        self.assertGreaterEqual(len(series), 3)
        self.assertTrue(all(point["count"] == 0 for point in series))


class MoneyGapTests(Day):
    def customer(self):
        return create_customer_with_phone(actor=self.manager, full_name="خریدار", phone={"raw_phone": "09125550200"})

    def test_a_manual_paid_figure_needs_an_issued_invoice_and_never_blocks_real_money(self):
        customer = self.customer()
        draft = create_invoice(actor=self.manager, customer=customer, items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}])
        with self.assertRaises(BusinessConflictError):
            record_manual_paid_entry(actor=self.manager, invoice=draft, amount=Decimal("1"))
        invoice = issue_invoice(actor=self.manager, invoice=draft)
        record_manual_paid_entry(actor=self.manager, invoice=invoice, amount=invoice.canonical_balance_due)
        receipt = register_payment(actor=self.manager, customer=customer, method=Payment.Method.CASH, amount=Decimal("1000000.00"))
        allocate_payment_across(actor=self.manager, payment=receipt, splits=[{"invoice": invoice, "amount": Decimal("1000000.00")}])
        invoice.refresh_from_db()
        self.assertEqual(invoice.paid_amount, Decimal("1000000.00"))

    def test_a_reused_key_with_a_different_split_is_refused_and_the_database_keeps_keys_unique(self):
        customer = self.customer()
        invoice = issue_invoice(actor=self.manager, invoice=create_invoice(
            actor=self.manager, customer=customer, items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        ))
        receipt = register_payment(actor=self.manager, customer=customer, method=Payment.Method.CASH, amount=Decimal("5000000.00"))
        allocate_payment_across(actor=self.manager, payment=receipt, splits=[{"invoice": invoice, "amount": Decimal("100.00")}], request_key="same")
        with self.assertRaises(BusinessConflictError):
            allocate_payment_across(actor=self.manager, payment=receipt, splits=[{"invoice": invoice, "amount": Decimal("200.00")}], request_key="same")
        single = self.api(self.manager).post(
            f"/api/v1/payments/{receipt.pk}/allocate/", {"invoice": invoice.pk, "amount": "50.00", "request_key": "one"}, format="json",
        )
        self.assertEqual(single.status_code, 201)
        repeat = self.api(self.manager).post(
            f"/api/v1/payments/{receipt.pk}/allocate/", {"invoice": invoice.pk, "amount": "50.00", "request_key": "one"}, format="json",
        )
        self.assertEqual(repeat.json()["id"], single.json()["id"])
        row = PaymentAllocation.objects.get(pk=single.json()["id"])
        with self.assertRaises(IntegrityError):
            PaymentAllocation.objects.create(payment=receipt, invoice=invoice, amount=Decimal("1"), created_by=self.manager, request_key=row.request_key)

    def test_number_and_official_number_clashes_are_told_apart(self):
        class Fake(Exception):
            pass

        for text, kind in (
            ("UNIQUE constraint failed: billing_invoice.number", "number"),
            ("UNIQUE constraint failed: billing_invoice.official_number", "official_number"),
            ("CHECK constraint failed: invoice_total", None),
        ):
            self.assertEqual(_number_clash_kind(Fake(text)), kind)

    def test_only_the_warehouse_cancels_an_approved_supply_request(self):
        customer = create_customer_with_phone(actor=self.marketer, full_name="خریدار", phone={"raw_phone": "09125550201"})
        invoice = issue_invoice(actor=self.manager, invoice=create_invoice(
            actor=self.marketer, customer=customer, items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        ))
        request = create_fulfillment_request(actor=self.marketer, invoice=invoice, warehouse=self.warehouse)
        transition_order(actor=self.manager, order=request, to_status=Order.Status.CONFIRMED)
        with self.assertRaises(BusinessPermissionDenied):
            transition_order(actor=self.marketer, order=request, to_status=Order.Status.CANCELLED)

    def test_a_cancelled_invoice_refuses_bulk_writes_on_its_money_rows(self):
        from billing.models import Installment, InstallmentPlan

        customer = self.customer()
        invoice = issue_invoice(actor=self.manager, invoice=create_invoice(
            actor=self.manager, customer=customer, items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        ))
        cancel_invoice(actor=self.manager, invoice=invoice, reason="آزمون")
        receipt = register_payment(actor=self.manager, customer=customer, method=Payment.Method.CASH, amount=Decimal("10.00"))
        with self.assertRaises(BusinessConflictError):
            PaymentAllocation.objects.bulk_create([PaymentAllocation(payment=receipt, invoice=invoice, amount=Decimal("1"), created_by=self.manager)])
        self.assertEqual(InstallmentPlan.objects.filter(invoice=invoice).count(), 0)
        self.assertEqual(Installment.objects.filter(plan__invoice=invoice).update(status="cancelled"), 0)

    def test_the_integrity_check_reports_an_allocation_across_two_customers(self):
        import io

        customer = self.customer()
        other = create_customer_with_phone(actor=self.manager, full_name="دیگری", phone={"raw_phone": "09125550202"})
        invoice = issue_invoice(actor=self.manager, invoice=create_invoice(
            actor=self.manager, customer=customer, items=[{"product": self.product, "quantity": 1, "unit_price": self.product.current_price}],
        ))
        receipt = register_payment(actor=self.manager, customer=customer, method=Payment.Method.CASH, amount=Decimal("100.00"))
        allocate_payment_across(actor=self.manager, payment=receipt, splits=[{"invoice": invoice, "amount": Decimal("100.00")}])
        Payment.objects.filter(pk=receipt.pk).update(customer=other)
        out = io.StringIO()
        with self.assertRaises(SystemExit):
            call_command("check_allocation_integrity", stdout=out)
        self.assertIn("different customers", out.getvalue())


class LeadAndSaleGapTests(Day):
    def test_a_sale_on_a_campaign_person_points_to_the_invoice(self):
        from sales.campaigns import container_lead
        from sales.services import mark_sale

        campaign = create_campaign(actor=self.manager, name="بهار")
        with self.assertRaises(BusinessRuleError) as caught:
            mark_sale(actor=self.manager, lead=container_lead(campaign, self.manager), product=self.product)
        self.assertIn("فاکتور جدید", str(caught.exception.detail))

    def test_the_old_order_link_is_backfilled_on_request_only(self):
        import io

        out = io.StringIO()
        call_command("backfill_order_invoice_links", stdout=out)
        self.assertIn("to link: 0", out.getvalue())
