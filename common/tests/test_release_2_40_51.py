"""2.40.51 — advanced instalments, part one (owner decision 2026-10-14, Q15).

«همه را نیاز داریم و همگی فیچرهای اضافه هستند که اگر مشتری بخواهد باید فعال
شود. قابلیت شخصی‌سازی هم داشته باشند.»

* `installment_reschedule`: change or extend what is left of an active plan —
  paid rows untouched, no row deleted, every change kept with its reason;
* `installment_reminders`: SMS before, on and after the due date, with the
  company's own days, hour and texts;
* both off by default, configured per company (`installments.configure`).
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from billing import installment_settings
from billing.installment_reminders import dispatch_installment_reminders, render
from billing.installments import invoice_summary, reschedule_plan, set_invoice_installments, visible_installments
from billing.models import Installment, InstallmentPlan, InstallmentReminder, InstallmentReschedule, Invoice, Payment
from billing.payments import allocate_payment, register_payment
from billing.services import create_invoice, issue_invoice
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES, DEFAULT_OFF_FEATURES, FEATURE_DEPENDENCIES
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from communications import sms
from communications.models import OutboundSMS
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-951!"


def without(*features):
    return DeploymentProfile(profile_id="client-1", features=frozenset(ALL_FEATURES) - set(features), source="signed-manifest")


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="i.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="i.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="i.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری اقساطی", phone={"raw_phone": "09129990051", "is_primary": True}
        )
        self.product = create_product(actor=self.manager, sku="I51", name="کالا", current_price=Decimal("1000.00"))
        self.today = timezone.localdate()

    def issued(self, *, first_due=None, count=3, down=Decimal("600.00"), customer=None):
        invoice = create_invoice(
            actor=self.manager, customer=customer or self.customer, items=[{"product": self.product, "quantity": 3}],
            payment_type=Invoice.PaymentType.INSTALLMENT, installment_down_payment=down, installment_count=count,
            installment_first_due=first_due or self.today + timedelta(days=30), installment_interval_days=30,
        )
        return issue_invoice(actor=self.manager, invoice=invoice)

    def pay(self, invoice, amount):
        payment = register_payment(actor=self.manager, customer=invoice.customer, method=Payment.Method.CASH, amount=Decimal(amount))
        allocate_payment(actor=self.manager, payment=payment, invoice=invoice)

    def rows(self, invoice):
        plan = InstallmentPlan.objects.get(invoice=invoice)
        return list(
            visible_installments(plan.installments.all()).order_by("sequence")
            .values_list("sequence", "amount", "paid_amount", "status")
        )


class FeatureTests(TestCase):
    def test_both_are_opt_in(self):
        for feature in ("installment_reschedule", "installment_reminders"):
            self.assertIn(feature, DEFAULT_OFF_FEATURES)
            self.assertEqual(FEATURE_DEPENDENCIES[feature], frozenset({"payments"}))


class RescheduleTests(Base):
    def test_paid_rows_stay_and_the_rest_is_spread_over_new_rows(self):
        invoice = self.issued()  # 3000: down 600, then 3 × 800
        self.pay(invoice, "1000.00")  # down payment, and 400 of the first instalment
        first_due = self.today + timedelta(days=10)
        reschedule_plan(
            actor=self.manager, invoice=invoice, installment_count=4, first_due=first_due, interval_days=15,
            reason="درخواست مشتری برای اقساط کوچک‌تر",
        )
        rows = self.rows(invoice)
        self.assertEqual(rows[:2], [
            (0, Decimal("600.00"), Decimal("600.00"), "paid"),
            (1, Decimal("400.00"), Decimal("400.00"), "paid"),
        ])
        self.assertEqual([row[0] for row in rows[2:]], [4, 5, 6, 7])
        self.assertEqual([row[1] for row in rows[2:]], [Decimal("500.00")] * 4)
        self.assertEqual(sum(row[1] for row in rows), invoice.total_amount)
        # Nothing was deleted: the closed rows are still there, cancelled.
        plan = InstallmentPlan.objects.get(invoice=invoice)
        self.assertEqual(plan.installments.count(), 8)
        self.assertEqual(sorted(plan.installments.filter(status="cancelled").values_list("sequence", flat=True)), [2, 3])
        dues = list(plan.installments.filter(sequence__gte=4).order_by("sequence").values_list("due_date", flat=True))
        self.assertEqual(dues, [first_due + timedelta(days=15 * index) for index in range(4)])
        history = InstallmentReschedule.objects.get(plan=plan)
        self.assertEqual(history.remaining_amount, Decimal("2000.00"))
        self.assertEqual(len(history.before), 4)
        self.assertEqual(len(history.after), 6)
        self.assertTrue(ActivityLog.objects.filter(operation="installment_plan.rescheduled", object_id=str(plan.pk)).exists())
        # The next receipt fills the new rows in order.
        self.pay(invoice, "700.00")
        self.assertEqual(self.rows(invoice)[2][2:], (Decimal("500.00"), "paid"))
        self.assertEqual(self.rows(invoice)[3][2:], (Decimal("200.00"), "partially_paid"))

    def test_the_invoice_terms_no_longer_rewrite_a_rescheduled_plan(self):
        invoice = self.issued()
        reschedule_plan(actor=self.manager, invoice=invoice, installment_count=2, first_due=self.today, interval_days=30, reason="تمدید")
        self.assertFalse(invoice_summary(invoice)["editable"])
        with self.assertRaises(BusinessConflictError):
            set_invoice_installments(actor=self.manager, invoice=invoice, installment_count=5)

    def test_preview_writes_nothing(self):
        invoice = self.issued()
        result = reschedule_plan(actor=self.manager, invoice=invoice, installment_count=6, first_due=self.today, interval_days=7, preview=True)
        self.assertEqual(result["remaining_amount"], Decimal("3000.00"))
        self.assertEqual(len(result["rows"]), 6)
        self.assertFalse(InstallmentReschedule.objects.exists())
        self.assertEqual(len(self.rows(invoice)), 4)
        # Whole rials, the remainder on the first row.
        odd = reschedule_plan(actor=self.manager, invoice=invoice, installment_count=7, first_due=self.today, interval_days=7, preview=True)
        amounts = [row[2] for row in odd["rows"]]
        self.assertEqual(amounts, [Decimal("432.00")] + [Decimal("428")] * 6)
        self.assertEqual(sum(amounts), Decimal("3000.00"))

    def test_what_is_refused(self):
        invoice = self.issued()
        with self.assertRaises(BusinessPermissionDenied):
            reschedule_plan(actor=self.agent, invoice=invoice, installment_count=2, first_due=self.today, interval_days=30, reason="x")
        with self.assertRaises(BusinessRuleError):
            reschedule_plan(actor=self.manager, invoice=invoice, installment_count=2, first_due=self.today, interval_days=30, reason="  ")
        with self.assertRaises(BusinessRuleError):
            reschedule_plan(
                actor=self.manager, invoice=invoice, installment_count=2, first_due=self.today - timedelta(days=1),
                interval_days=30, reason="دیروز",
            )
        with override_active_profile(without("installment_reschedule")), self.assertRaises(BusinessConflictError):
            reschedule_plan(actor=self.manager, invoice=invoice, installment_count=2, first_due=self.today, interval_days=30, reason="x")
        self.pay(invoice, "3000.00")
        with self.assertRaises(BusinessConflictError):
            reschedule_plan(actor=self.manager, invoice=invoice, installment_count=2, first_due=self.today, interval_days=30, reason="x")

    def test_the_api_previews_saves_and_shows_the_history(self):
        invoice = self.issued()
        client = APIClient()
        client.force_authenticate(self.manager)
        url = f"/api/v1/invoices/{invoice.pk}/reschedule-installments/"
        body = {"installment_count": 2, "first_due": (self.today + timedelta(days=5)).isoformat(), "interval_days": 30}
        preview = client.post(url, {**body, "preview": True}, format="json")
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(len(preview.json()["rows"]), 2)
        saved = client.post(url, {**body, "reason": "تمدید یک‌ماهه"}, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        payload = saved.json()
        self.assertEqual(payload["reschedules"][0]["reason"], "تمدید یک‌ماهه")
        self.assertEqual(payload["reschedules"][0]["installment_count"], 2)
        agent = APIClient()
        agent.force_authenticate(self.agent)
        self.assertIn(agent.post(url, {**body, "reason": "x"}, format="json").status_code, (403, 404))

    def test_the_invoice_page_offers_it_to_a_payments_manager_only(self):
        invoice = self.issued()
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(f"/invoices/{invoice.pk}/"), 'id="invoice-installments-reschedule"')
        with override_active_profile(without("installment_reschedule")):
            self.assertNotContains(self.client.get(f"/invoices/{invoice.pk}/"), 'id="invoice-installments-reschedule"')


class SettingsTests(Base):
    def test_defaults_and_validation(self):
        row = installment_settings.get_settings()
        self.assertEqual((row.remind_days_before, row.remind_on_due, row.remind_days_after, row.remind_send_hour), (3, True, 3, 10))
        updated = installment_settings.update_settings(actor=self.admin, remind_days_before=5, template_due="امروز {تاریخ} سررسید {قسط} است.")
        self.assertEqual(updated.remind_days_before, 5)
        with self.assertRaises(BusinessRuleError):
            installment_settings.update_settings(actor=self.admin, template_before="سلام {اسم}")
        with self.assertRaises(BusinessRuleError):
            installment_settings.update_settings(actor=self.admin, remind_send_hour=23)
        with self.assertRaises(BusinessPermissionDenied):
            installment_settings.update_settings(actor=self.manager, remind_days_before=1)

    def test_the_api_and_the_settings_tab(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.patch("/api/v1/installment-settings/", {"remind_days_after": 7}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["remind_days_after"], 7)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        self.assertEqual(manager.get("/api/v1/installment-settings/").status_code, 403)
        with override_active_profile(without("installment_reschedule", "installment_reminders")):
            self.assertEqual(client.get("/api/v1/installment-settings/").status_code, 404)
        self.client.force_login(self.admin)
        page = self.client.get("/settings/?tab=installments")
        self.assertContains(page, 'id="installment-settings-form"')
        self.assertContains(page, "یادآور پیامکی اقساط")


class ReminderTests(Base):
    def setUp(self):
        super().setUp()
        self.ok = mock.patch.object(sms, "provider_is_available", return_value=True)
        self.send = mock.patch.object(
            sms, "send_via_configured_provider", return_value=sms.SmsSendResult(provider_code="http", success=True, status_detail="200")
        )
        self.ok.start()
        self.sender = self.send.start()
        self.addCleanup(self.ok.stop)
        self.addCleanup(self.send.stop)
        self.at_eleven = timezone.make_aware(datetime.combine(self.today, time(11, 0)))

    def test_before_on_and_after_each_once(self):
        soon = self.issued(first_due=self.today + timedelta(days=2), down=Decimal("0.00"))
        due_today = self.issued(first_due=self.today, down=Decimal("0.00"))
        late = self.issued(first_due=self.today - timedelta(days=4), down=Decimal("0.00"))
        far = self.issued(first_due=self.today + timedelta(days=20), down=Decimal("0.00"))
        sent, failed, skipped = dispatch_installment_reminders(now=self.at_eleven)
        self.assertEqual((sent, failed, skipped), (3, 0, 0))
        kinds = dict(InstallmentReminder.objects.values_list("installment__plan__invoice", "kind"))
        self.assertEqual(kinds, {soon.pk: "before", due_today.pk: "due", late.pk: "overdue"})
        self.assertNotIn(far.pk, kinds)
        self.assertEqual(OutboundSMS.objects.filter(sent_by__isnull=True, customer=self.customer).count(), 3)
        # A second run the same day sends nothing again.
        self.assertEqual(dispatch_installment_reminders(now=self.at_eleven), (0, 0, 0))
        body = self.sender.call_args_list[0].kwargs["body"]
        self.assertIn("مشتری اقساطی", body)
        self.assertNotIn("{", body)

    def test_nothing_before_the_send_hour_or_without_the_feature(self):
        self.issued(first_due=self.today, down=Decimal("0.00"))
        early = timezone.make_aware(datetime.combine(self.today, time(8, 0)))
        self.assertEqual(dispatch_installment_reminders(now=early), (0, 0, 0))
        with override_active_profile(without("installment_reminders")):
            self.assertEqual(dispatch_installment_reminders(now=self.at_eleven), (0, 0, 0))
        self.assertFalse(InstallmentReminder.objects.exists())

    def test_a_paid_row_is_not_reminded_and_a_missing_phone_is_recorded(self):
        paid = self.issued(first_due=self.today, down=Decimal("0.00"))
        self.pay(paid, "1000.00")
        dispatch_installment_reminders(now=self.at_eleven)
        self.assertFalse(InstallmentReminder.objects.filter(installment__plan__invoice=paid, installment__sequence=1).exists())
        no_phone = create_customer_with_phone(actor=self.manager, full_name="بی‌شماره", phone={"raw_phone": "09129990052", "is_primary": True})
        no_phone.phones.update(is_active=False)
        silent = self.issued(first_due=self.today, down=Decimal("0.00"), customer=no_phone)
        dispatch_installment_reminders(now=self.at_eleven)
        reminder = InstallmentReminder.objects.get(installment__plan__invoice=silent)
        self.assertEqual(reminder.status, "skipped")
        self.assertIn("شماره", reminder.detail)

    def test_the_text_uses_the_rows_own_facts(self):
        invoice = self.issued(first_due=self.today, down=Decimal("0.00"))
        row = Installment.objects.get(plan__invoice=invoice, sequence=1)
        text = render("{نام} {مبلغ} {تاریخ} {فاکتور} {قسط}", row)
        self.assertIn("مشتری اقساطی", text)
        self.assertIn("۱٬۰۰۰ ریال", text)
        self.assertIn("قسط ۱", text)
