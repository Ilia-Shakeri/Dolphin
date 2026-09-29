"""The customer «آنالیز» tab (2.33.0): five figures, a monthly series each, and
scope that is the owning modules' own — what a viewer may not read is reported
as missing, never as zero."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Invoice, Payment
from billing.payments import allocate_payment, register_payment
from billing.services import create_invoice, issue_invoice
from common.deployment.profile import override_active_profile
from profiles.tests.test_profiles import profile_without
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-771!"


class CustomerAnalysisTests(TestCase):
    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(
            username="an.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="an.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.other = User.objects.create_user(
            username="an.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.customer = create_customer_with_phone(
            actor=self.agent,
            full_name="مشتری آنالیز",
            phone={"raw_phone": "09123334455", "is_primary": True},
        )
        product = create_product(
            actor=self.manager, sku="AN-1", name="کالای آنالیز", current_price=Decimal("1000.00")
        )
        first_due = timezone.localdate() + timedelta(days=20)
        invoice = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=self.customer,
                items=[{"product": product, "quantity": 3}],
                payment_type=Invoice.PaymentType.INSTALLMENT,
                installment_down_payment=Decimal("600.00"),
                installment_count=3,
                installment_first_due=first_due,
                installment_interval_days=30,
            ),
        )
        payment = register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH, amount=Decimal("600.00")
        )
        allocate_payment(actor=self.manager, payment=payment, invoice=invoice)
        self.first_due = first_due
        self.url = f"/api/v1/profiles/customer/{self.customer.pk}/analysis/"

    def get(self, user, url=None):
        client = APIClient()
        client.force_authenticate(user)
        return client.get(url or self.url)

    def test_a_manager_gets_all_five_figures_and_a_series_each(self):
        body = self.get(self.manager).json()
        kpis, series = body["kpis"], body["series"]
        self.assertEqual(
            set(kpis), {"total_purchase", "total_received", "debt_balance", "open_installments", "next_due"}
        )
        self.assertFalse(any(item["missing"] for item in kpis.values()))
        self.assertEqual(kpis["total_purchase"]["raw"], "3000.00")
        self.assertEqual(kpis["total_received"]["raw"], "600.00")
        self.assertEqual(kpis["open_installments"]["raw"], 3)
        self.assertEqual(kpis["next_due"]["raw"], self.first_due.isoformat())
        self.assertFalse(kpis["next_due"]["overdue"])
        self.assertEqual(len(series["total_purchase"]["points"]), 12)
        self.assertEqual(series["total_purchase"]["points"][-1]["value"], 3000.0)
        self.assertEqual(series["total_received"]["points"][-1]["value"], 600.0)
        self.assertEqual(series["debt_balance"]["points"][-1]["value"], 2400.0)
        self.assertEqual(sum(p["value"] for p in series["open_installments"]["points"]), 3.0)
        self.assertEqual(sum(p["value"] for p in series["next_due"]["points"]), 2400.0)

    def test_an_agent_sees_purchases_but_payments_and_instalments_are_missing(self):
        kpis = self.get(self.agent).json()["kpis"]
        self.assertFalse(kpis["total_purchase"]["missing"])
        for key in ("total_received", "open_installments", "next_due"):
            self.assertTrue(kpis[key]["missing"], key)
            self.assertEqual(kpis[key]["display"], "—")

    def test_a_customer_outside_the_readers_scope_is_a_404(self):
        self.assertEqual(self.get(self.other).status_code, 404)

    def test_only_a_customer_has_an_analysis(self):
        self.assertEqual(self.get(self.manager, f"/api/v1/profiles/user/{self.agent.pk}/analysis/").status_code, 404)

    def test_the_response_is_never_cached(self):
        self.assertIn("no-store", self.get(self.manager)["Cache-Control"])

    def test_the_tab_follows_the_invoices_feature(self):
        self.client.force_login(self.manager)
        page = f"/customers/{self.customer.pk}/"
        self.assertContains(self.client.get(page), 'id="customer-analysis"')
        with override_active_profile(profile_without("invoices")):
            self.assertNotContains(self.client.get(page), 'id="customer-analysis"')
            self.assertEqual(self.get(self.manager).status_code, 404)
