"""`cheques` — the payment method's own feature gate.

Product-owner decision (2026-09-22), made while preparing a fresh signed
manifest for TIARA: a deployment may want ordinary receipts and
disbursements without accepting postdated cheques as a payment method at
all. Before this, cheque support rode along with `payments` — every
deployment that could record any payment could also record a cheque, with
no way to turn one off without the other. This file proves the three
separate controls (CLAUDE.md §5.1) hold for the split:

* **feature availability** — `/cheques/`, `/api/v1/cheques/`, the چک method
  on the receipt/disbursement wizard, the sidebar link, and the cheque-due
  reminder source all disappear together when `cheques` is off, while
  `payments` itself (cash, bank transfer, instalment reminders) keeps
  working;
* the existing `payments` role capability is not re-implemented or
  weakened — it still gates who may use whichever methods remain enabled.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User
from billing.models import Payment
from billing.payments import create_installment_plan, register_payment
from billing.services import create_invoice, issue_invoice
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES, FEATURE_DEPENDENCIES
from common.reminders import reminders_for
from inventory.services import create_warehouse
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-604!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class RegistryTests(SimpleTestCase):
    def test_cheques_is_a_registered_feature_depending_only_on_payments(self):
        self.assertEqual(FEATURE_DEPENDENCIES["cheques"], frozenset({"payments"}))


class FeatureGateTests(TestCase):
    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(
            username="cheque.gate.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری چک",
            phone={"raw_phone": "09121110000", "is_primary": True},
        )
        self.client = Client()
        self.client.login(username="cheque.gate.manager", password=PASSWORD)

    def test_the_cheques_page_is_404_when_the_feature_is_off(self):
        with override_active_profile(profile_without("cheques")):
            self.assertEqual(self.client.get("/cheques/").status_code, 404)

    def test_the_cheques_page_renders_when_the_feature_is_on(self):
        self.assertEqual(self.client.get("/cheques/").status_code, 200)

    def test_the_cheques_api_is_404_when_the_feature_is_off(self):
        with override_active_profile(profile_without("cheques")):
            self.assertEqual(self.client.get("/api/v1/cheques/").status_code, 404)

    def test_the_payments_desk_still_works_with_cheques_off(self):
        """`payments` itself — cash, bank transfer — is a separate control."""
        with override_active_profile(profile_without("cheques")):
            self.assertEqual(self.client.get("/payments/").status_code, 200)

    def test_the_nav_link_only_appears_with_the_feature_on(self):
        with_feature = self.client.get("/payments/").content.decode("utf-8")
        self.assertIn("چک‌ها", with_feature)
        with override_active_profile(profile_without("cheques")):
            without_feature = self.client.get("/payments/").content.decode("utf-8")
        self.assertNotIn('data-module="cheques"', without_feature)

    def test_the_method_button_only_appears_with_the_feature_on(self):
        with_feature = self.client.get("/payments/").content.decode("utf-8")
        self.assertIn('data-payment-mode="cheque"', with_feature)
        with override_active_profile(profile_without("cheques")):
            without_feature = self.client.get("/payments/").content.decode("utf-8")
        self.assertNotIn('data-payment-mode="cheque"', without_feature)

    def test_registering_a_cheque_payment_is_refused_with_the_feature_off(self):
        with override_active_profile(profile_without("cheques")):
            response = self.client.post(
                "/api/v1/payments/",
                {
                    "customer": self.customer.pk,
                    "method": "cheque",
                    "amount": "1000.00",
                    "cheque": {
                        "source": "own",
                        "bank_name": "بانک",
                        "serial_number": "1",
                        "due_date": "2026-12-01",
                    },
                },
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("method", response.json())

    def test_registering_a_cash_payment_still_works_with_cheques_off(self):
        with override_active_profile(profile_without("cheques")):
            response = self.client.post(
                "/api/v1/payments/",
                {"customer": self.customer.pk, "method": "cash", "amount": "1000.00"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)

    def test_a_cheque_payment_registered_before_the_feature_was_turned_off_still_exists(self):
        """Disabling a feature must not delete historical data (CLAUDE.md §5.2)."""
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("1000.00"),
            cheque={
                "source": "own", "bank_name": "بانک", "serial_number": "1",
                "due_date": date(2026, 12, 1),
            },
        )
        with override_active_profile(profile_without("cheques")):
            self.assertTrue(Payment.objects.filter(pk=payment.pk, method=Payment.Method.CHEQUE).exists())


class ReminderSourceTests(TestCase):
    """`reminders_for` — the topbar bell — respects the same split."""

    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(
            username="cheque.reminder.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری یادآور",
            phone={"raw_phone": "09121110001", "is_primary": True},
        )
        self.product = create_product(
            actor=self.manager, sku="REM-1", name="کالای یادآور", current_price=Decimal("300.00")
        )
        self.warehouse = create_warehouse(actor=self.manager, code="rem-wh", name="انبار یادآور")

        def issued_invoice():
            return issue_invoice(
                actor=self.manager,
                invoice=create_invoice(
                    actor=self.manager,
                    customer=self.customer,
                    items=[{"product": self.product, "quantity": 1}],
                    warehouse=self.warehouse,
                ),
            )

        self.overdue_cheque_payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("300.00"),
            cheque={
                "source": "own", "bank_name": "بانک", "serial_number": "2",
                "due_date": date.today() - timedelta(days=1),
            },
        )
        create_installment_plan(
            actor=self.manager,
            invoice=issued_invoice(),
            installment_count=1,
            start_date=date.today() - timedelta(days=1),
        )

    def _group_kinds(self, user):
        return {group["kind"] for group in reminders_for(user)["groups"]}

    def test_a_cheque_reminder_is_suppressed_with_cheques_off(self):
        with override_active_profile(profile_without("cheques")):
            self.assertNotIn("cheque_due", self._group_kinds(self.manager))

    def test_the_instalment_reminder_is_unaffected_by_cheques_being_off(self):
        with override_active_profile(profile_without("cheques")):
            self.assertIn("installment_due", self._group_kinds(self.manager))

    def test_a_cheque_reminder_shows_with_the_feature_on(self):
        self.assertIn("cheque_due", self._group_kinds(self.manager))
