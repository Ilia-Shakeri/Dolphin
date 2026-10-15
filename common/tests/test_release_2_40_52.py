"""2.40.52 — advanced instalments, part two: interest and late fees (Q15).

Owner decisions 2026-10-14: «سود ساده یا کاهنده، با نرخ پیش‌فرض قابل تنظیم»;
«جریمهٔ دیرکرد: مهلت، درصد یا مبلغ، و سقف»; and the confirmed defaults — a
charge is a debit of its own in the customer ledger, never added to the
invoice or the instalment, and every amount is whole rials.
"""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing import installment_settings
from billing.installment_charges import (
    interest_shares,
    post_late_fees,
    release_settlement,
    settle_charges,
    waive_charge,
)
from billing.installments import invoice_summary, reschedule_plan, set_invoice_installments
from billing.ledger import current_balance
from billing.models import (
    ChargeSettlement,
    CustomerLedgerEntry,
    InstallmentCharge,
    InstallmentSettings,
    Invoice,
    Payment,
)
from billing.payments import cancel_payment, customer_outstanding, register_payment
from billing.services import cancel_invoice, create_invoice, issue_invoice
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES, DEFAULT_OFF_FEATURES, FEATURE_DEPENDENCIES
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-952!"


def without(*features):
    return DeploymentProfile(profile_id="client-1", features=frozenset(ALL_FEATURES) - set(features), source="signed-manifest")


class FormulaTests(TestCase):
    def test_the_published_example_is_the_reducing_total(self):
        # 1,000,000 rial at 15% over 12 monthly rows: 81,250 interest — the
        # figure the older plan API was checked against — is the reducing
        # method's total; simple interest charges the whole principal for the
        # whole term.
        principals = [Decimal("1000000") / 12] * 12
        reducing = interest_shares(method="reducing", annual_rate=Decimal("15"), principals=principals, interval_days=30)
        self.assertEqual(sum(reducing), Decimal("81250"))
        self.assertGreater(reducing[0], reducing[-1])
        simple = interest_shares(method="simple", annual_rate=Decimal("15"), principals=principals, interval_days=30)
        self.assertEqual(sum(simple), Decimal("150000"))
        self.assertEqual(len(set(simple[1:])), 1)
        self.assertTrue(all(share == share.to_integral_value() for share in simple + reducing))

    def test_no_rate_no_interest(self):
        self.assertEqual(interest_shares(method="simple", annual_rate=0, principals=[Decimal("10")], interval_days=30), [0])


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="c.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="c.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="c.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری سود", phone={"raw_phone": "09129990061", "is_primary": True}
        )
        self.product = create_product(actor=self.manager, sku="C52", name="کالا", current_price=Decimal("1200000"))
        self.today = timezone.localdate()

    def configure(self, **values):
        return installment_settings.update_settings(actor=self.admin, **values)

    def draft(self, *, first_due=None, count=3, down=Decimal("0")):
        return create_invoice(
            actor=self.manager, customer=self.customer, items=[{"product": self.product, "quantity": 1}],
            payment_type=Invoice.PaymentType.INSTALLMENT, installment_down_payment=down, installment_count=count,
            installment_first_due=first_due or self.today + timedelta(days=30), installment_interval_days=30,
        )

    def issued(self, **terms):
        return issue_invoice(actor=self.manager, invoice=self.draft(**terms))

    def receipt(self, amount):
        return register_payment(actor=self.manager, customer=self.customer, method=Payment.Method.CASH, amount=Decimal(amount))


class InterestTests(Base):
    def test_issue_posts_interest_apart_from_the_invoice(self):
        self.configure(interest_method="reducing", interest_default_rate=Decimal("24"))
        invoice = self.issued()  # 1,200,000 in three monthly rows of 400,000
        charges = list(InstallmentCharge.objects.filter(plan__invoice=invoice).order_by("installment__sequence"))
        # 2% a month on 1.2M, then 0.8M, then 0.4M.
        self.assertEqual([charge.amount for charge in charges], [Decimal("24000"), Decimal("16000"), Decimal("8000")])
        self.assertEqual(invoice.total_amount, Decimal("1200000.00"))
        entry = CustomerLedgerEntry.objects.get(customer=self.customer, entry_type="installment_interest")
        self.assertEqual(entry.debit, Decimal("48000.00"))
        self.assertEqual(current_balance(self.customer), Decimal("1248000.00"))
        self.assertEqual(customer_outstanding(self.customer), Decimal("1248000.00"))
        # Rows keep their principal; the plan cannot be rewritten from the terms.
        self.assertFalse(invoice_summary(invoice)["editable"])
        with self.assertRaises(BusinessConflictError):
            set_invoice_installments(actor=self.manager, invoice=invoice, installment_count=4)

    def test_a_drafts_own_rate_and_its_preview(self):
        self.configure(interest_method="simple", interest_default_rate=Decimal("12"))
        draft = self.draft()
        preview = invoice_summary(draft)["interest_preview"]
        self.assertEqual(preview["total"], Decimal("36000"))  # 1.2M × 12% × 3 months
        set_invoice_installments(actor=self.manager, invoice=draft, profit_rate=Decimal("0"))
        draft.refresh_from_db()
        self.assertEqual(invoice_summary(draft)["interest_preview"]["total"], Decimal("0"))
        issued = issue_invoice(actor=self.manager, invoice=draft)
        self.assertFalse(InstallmentCharge.objects.filter(plan__invoice=issued).exists())
        with self.assertRaises(BusinessConflictError):
            set_invoice_installments(actor=self.manager, invoice=issued, profit_rate=Decimal("5"))

    def test_without_the_feature_nothing_is_charged(self):
        self.configure(interest_default_rate=Decimal("24"))
        with override_active_profile(without("installment_interest")):
            invoice = self.issued()
        self.assertFalse(InstallmentCharge.objects.filter(plan__invoice=invoice).exists())
        self.assertFalse(CustomerLedgerEntry.objects.filter(entry_type="installment_interest").exists())

    def test_rescheduling_moves_the_open_interest_and_adds_none(self):
        self.configure(interest_method="simple", interest_default_rate=Decimal("12"))
        invoice = self.issued()
        open_before = sum(charge.open_amount for charge in InstallmentCharge.objects.filter(plan__invoice=invoice))
        reschedule_plan(actor=self.manager, invoice=invoice, installment_count=4, first_due=self.today, interval_days=30, reason="تمدید")
        charges = InstallmentCharge.objects.filter(plan__invoice=invoice)
        self.assertEqual(charges.filter(status="moved").count(), 3)
        moved_to = charges.filter(status="open")
        self.assertEqual(moved_to.count(), 4)
        self.assertEqual(sum(charge.open_amount for charge in moved_to), open_before)
        self.assertEqual(CustomerLedgerEntry.objects.filter(entry_type="installment_interest").count(), 1)

    def test_cancelling_the_invoice_cancels_open_interest_with_one_credit(self):
        self.configure(interest_default_rate=Decimal("12"))
        invoice = self.issued()
        cancel_invoice(actor=self.manager, invoice=invoice, reason="اشتباه")
        self.assertEqual(set(InstallmentCharge.objects.values_list("status", flat=True)), {"cancelled"})
        self.assertEqual(current_balance(self.customer), Decimal("0.00"))
        self.assertTrue(CustomerLedgerEntry.objects.filter(entry_type="charge_cancelled").exists())


class LateFeeTests(Base):
    def test_one_fee_after_the_grace_capped_and_never_reaching_back(self):
        self.configure(late_fee_grace_days=5, late_fee_mode="percent", late_fee_value=Decimal("10"), late_fee_cap=Decimal("30000"))
        settings_row = InstallmentSettings.objects.get()
        self.assertEqual(settings_row.late_fee_since, self.today)
        overdue = self.issued(first_due=self.today - timedelta(days=6))      # past its grace
        recent = self.issued(first_due=self.today - timedelta(days=3))       # within its grace
        InstallmentSettings.objects.update(late_fee_since=self.today - timedelta(days=30))
        self.assertEqual(post_late_fees(), 1)
        fee = InstallmentCharge.objects.get(kind="late_fee")
        self.assertEqual(fee.installment.plan.invoice_id, overdue.pk)
        self.assertEqual(fee.amount, Decimal("30000"))  # 10% of 400,000 is 40,000, capped
        entry = CustomerLedgerEntry.objects.get(entry_type="late_fee")
        self.assertIsNone(entry.created_by)
        self.assertEqual(post_late_fees(), 0)  # once per row
        self.assertFalse(InstallmentCharge.objects.filter(installment__plan__invoice=recent).exists())
        # A row due before the fee was first set is never charged.
        InstallmentSettings.objects.update(late_fee_since=self.today)
        older = self.issued(first_due=self.today - timedelta(days=20))
        self.assertEqual(post_late_fees(), 0)
        self.assertFalse(InstallmentCharge.objects.filter(installment__plan__invoice=older).exists())

    def test_the_command_and_the_feature_gate(self):
        self.configure(late_fee_mode="fixed", late_fee_value=Decimal("50000"), late_fee_grace_days=0)
        InstallmentSettings.objects.update(late_fee_since=self.today - timedelta(days=30))
        self.issued(first_due=self.today - timedelta(days=2))
        with override_active_profile(without("installment_late_fees")):
            self.assertEqual(post_late_fees(), 0)
        out = StringIO()
        call_command("post_installment_late_fees", stdout=out)
        self.assertIn("charged=1", out.getvalue())
        self.assertEqual(InstallmentCharge.objects.get(kind="late_fee").amount, Decimal("50000"))

    def test_waiving_needs_a_manager_and_a_reason_and_credits_what_is_left(self):
        self.configure(late_fee_mode="fixed", late_fee_value=Decimal("50000"), late_fee_grace_days=0)
        InstallmentSettings.objects.update(late_fee_since=self.today - timedelta(days=30))
        self.issued(first_due=self.today - timedelta(days=2))
        post_late_fees()
        fee = InstallmentCharge.objects.get(kind="late_fee")
        with self.assertRaises(BusinessPermissionDenied):
            waive_charge(actor=self.agent, charge=fee, reason="x")
        with self.assertRaises(BusinessRuleError):
            waive_charge(actor=self.manager, charge=fee, reason=" ")
        waive_charge(actor=self.manager, charge=fee, reason="مشتری قدیمی")
        fee.refresh_from_db()
        self.assertEqual((fee.status, fee.released_amount), ("waived", Decimal("50000.00")))
        self.assertEqual(CustomerLedgerEntry.objects.get(entry_type="charge_waived").credit, Decimal("50000.00"))


class SettlementTests(Base):
    def setUp(self):
        super().setUp()
        self.configure(interest_method="reducing", interest_default_rate=Decimal("24"))
        self.invoice = self.issued()  # interest 24,000 + 16,000 + 8,000

    def test_a_receipt_settles_charges_earliest_first_and_releases_them(self):
        receipt = self.receipt("30000")
        made = settle_charges(actor=self.manager, payment=receipt)
        self.assertEqual([item.amount for item in made], [Decimal("24000.00"), Decimal("6000.00")])
        receipt.refresh_from_db()
        self.assertEqual(receipt.allocated_amount, Decimal("30000.00"))
        first, second, _ = InstallmentCharge.objects.order_by("installment__sequence")
        self.assertEqual(first.status, "paid")
        self.assertEqual(second.open_amount, Decimal("10000.00"))
        with self.assertRaises(BusinessConflictError):
            settle_charges(actor=self.manager, payment=receipt)
        release_settlement(actor=self.manager, settlement=made[0], reason="اشتباه")
        first.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual((first.status, first.paid_amount, receipt.allocated_amount), ("open", Decimal("0.00"), Decimal("6000.00")))
        # Cancelling the receipt releases the rest.
        cancel_payment(actor=self.manager, payment=receipt, reason="برگشت")
        self.assertFalse(ChargeSettlement.objects.filter(is_reversed=False).exists())
        self.assertEqual(sum(charge.paid_amount for charge in InstallmentCharge.objects.all()), Decimal("0.00"))

    def test_a_settled_charge_blocks_cancelling_the_invoice(self):
        receipt = self.receipt("1000")
        settle_charges(actor=self.manager, payment=receipt)
        with self.assertRaises(BusinessConflictError):
            cancel_invoice(actor=self.manager, invoice=self.invoice, reason="x")

    def test_the_api_and_the_integrity_check(self):
        receipt = self.receipt("50000")
        client = APIClient()
        client.force_authenticate(self.manager)
        listed = client.get(f"/api/v1/payments/{receipt.pk}/charges/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(len(listed.json()["open"]), 3)
        first = listed.json()["open"][0]["id"]
        settled = client.post(f"/api/v1/payments/{receipt.pk}/settle-charges/", {"charges": [{"charge": first, "amount": "5000"}]}, format="json")
        self.assertEqual(settled.status_code, 201, settled.content)
        self.assertEqual(len(settled.json()["settlements"]), 1)
        out = StringIO()
        call_command("check_allocation_integrity", stdout=out)
        self.assertIn("agree", out.getvalue())
        page = self.client
        page.force_login(self.manager)
        self.assertContains(page.get(f"/payments/{receipt.pk}/"), 'id="payment-charges-section"')
        self.assertContains(page.get(f"/invoices/{self.invoice.pk}/"), 'id="invoice-installment-charges"')

    def test_settings_api_takes_the_new_rules(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.patch("/api/v1/installment-settings/", {
            "interest_method": "simple", "interest_default_rate": "18.5", "late_fee_mode": "percent",
            "late_fee_value": "2", "late_fee_cap": "500000", "late_fee_grace_days": 7,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual((data["interest_method"], data["late_fee_grace_days"]), ("simple", 7))
        self.assertEqual(Decimal(data["interest_default_rate"]), Decimal("18.50"))
        bad = client.patch("/api/v1/installment-settings/", {"late_fee_value": "150"}, format="json")
        self.assertEqual(bad.status_code, 400)
        bad = client.patch("/api/v1/installment-settings/", {"interest_method": "compound"}, format="json")
        self.assertEqual(bad.status_code, 400)


class RegistryTests(TestCase):
    def test_both_are_opt_in_and_need_the_ledger(self):
        for feature in ("installment_interest", "installment_late_fees"):
            self.assertIn(feature, DEFAULT_OFF_FEATURES)
            self.assertEqual(FEATURE_DEPENDENCIES[feature], frozenset({"payments", "customer_ledger"}))
