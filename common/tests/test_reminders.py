"""The topbar reminder bell: `common.reminders`, its API, and the header.

Four things are worth proving separately, because each is a different one of
the controls this codebase keeps apart:

* **what counts as due** — an overdue follow-up and one falling later today
  are reminders; one set for next week is not, and a cheque gets a week of
  warning because money needs arranging;
* **object scope is not re-implemented** — a marketer sees their own
  follow-ups and nothing about company money, and that must come from the
  owning module's existing selector rather than a rule written twice here;
* **the feature gate** — `reminders` off means no bell in the header and a
  404 from the API, and a deployment missing one *source* feature (say
  `payments`) still gets the sources it does have;
* **no read state** — the count reflects work, so it drops when the work is
  done and not when someone opens the panel.
"""

import pathlib
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from aftersales.services import create_after_sales_request, schedule_after_sales_appointment
from billing.models import Payment
from billing.payments import create_installment_plan, register_payment
from billing.services import create_invoice, issue_invoice
from common import reminders
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from inventory.services import create_warehouse, record_stock_movement
from inventory.models import StockMovement
from sales.services import assign_lead, create_customer_with_phone, create_lead, create_product

PASSWORD = "Strong-pass-771!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class ReminderFixtures(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="rem.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="rem.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales_agent = User.objects.create_user(
            username="rem.aftersales", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        self.now = timezone.now()

    # --- fixture builders -------------------------------------------------

    #: Phone numbers are unique per customer, so every fixture customer needs
    #: its own. A counter rather than a random number keeps a failure
    #: reproducible.
    phone_counter = 0

    def a_customer(self, name="مشتری یادآور", actor=None):
        ReminderFixtures.phone_counter += 1
        return create_customer_with_phone(
            actor=actor or self.manager,
            full_name=name,
            phone={"raw_phone": f"0912000{ReminderFixtures.phone_counter:04d}", "is_primary": True},
        )

    def a_lead_due(self, *, when, actor=None, assigned_to=None, customer=None):
        actor = actor or self.manager
        lead = create_lead(
            actor=actor,
            customer=customer or self.a_customer(actor=actor),
            source="کمپین یادآور",
        )
        # Assignment goes through the service: `assigned_to`, `assigned_by`
        # and `assigned_at` are one fact and a CHECK constraint refuses any
        # row that sets only some of them.
        if assigned_to is not None:
            assign_lead(actor=actor, lead=lead, to_user=assigned_to)
            lead.refresh_from_db()
        lead.next_follow_up_at = when
        lead.save(update_fields=["next_follow_up_at"])
        return lead


class DueWindowTests(ReminderFixtures):
    """What the four sources consider due, and what they leave alone."""

    def test_an_overdue_follow_up_is_a_reminder_and_is_marked_overdue(self):
        self.a_lead_due(when=self.now - timedelta(hours=3))
        data = reminders.reminders_for(self.manager)
        self.assertEqual(data["count"], 1)
        group = data["groups"][0]
        self.assertEqual(group["kind"], "lead_follow_up")
        self.assertTrue(group["items"][0]["overdue"])

    def test_a_follow_up_later_today_is_a_reminder_but_not_overdue(self):
        # 23:59 local today: still today, still ahead of now.
        end_of_day = timezone.localtime(self.now).replace(hour=23, minute=58, second=0, microsecond=0)
        if end_of_day <= timezone.localtime(self.now):
            self.skipTest("This test needs to run before 23:58 local time.")
        self.a_lead_due(when=end_of_day)
        data = reminders.reminders_for(self.manager)
        self.assertEqual(data["count"], 1)
        self.assertFalse(data["groups"][0]["items"][0]["overdue"])
        self.assertEqual(data["overdue_count"], 0)

    def test_a_follow_up_set_for_next_week_is_not_yet_due(self):
        self.a_lead_due(when=self.now + timedelta(days=7))
        self.assertEqual(reminders.reminders_for(self.manager)["count"], 0)

    def test_a_completed_lead_is_not_work_even_with_a_past_follow_up(self):
        lead = self.a_lead_due(when=self.now - timedelta(days=1))
        lead.status = lead.Status.COMPLETED
        lead.save(update_fields=["status"])
        self.assertEqual(reminders.reminders_for(self.manager)["count"], 0)

    def test_a_cancelled_lead_is_not_work_either(self):
        lead = self.a_lead_due(when=self.now - timedelta(days=1))
        lead.status = lead.Status.CANCELLED
        lead.save(update_fields=["status"])
        self.assertEqual(reminders.reminders_for(self.manager)["count"], 0)

    def test_a_lead_with_no_follow_up_date_is_never_a_reminder(self):
        create_lead(actor=self.manager, customer=self.a_customer(), source="بدون پیگیری")
        self.assertEqual(reminders.reminders_for(self.manager)["count"], 0)

    def test_an_after_sales_appointment_due_today_is_a_reminder(self):
        request = create_after_sales_request(
            actor=self.manager,
            customer=self.a_customer(name="مشتری پس از فروش"),
            subject="تعویض قطعه",
            description="شرح",
            status="باز",
            assigned_to=self.after_sales_agent,
        )
        schedule_after_sales_appointment(
            actor=self.manager, request=request, appointment_at=self.now - timedelta(hours=1),
        )
        data = reminders.reminders_for(self.after_sales_agent)
        kinds = [group["kind"] for group in data["groups"]]
        self.assertIn("after_sales_appointment", kinds)

    def test_a_closed_after_sales_request_is_not_a_reminder(self):
        request = create_after_sales_request(
            actor=self.manager,
            customer=self.a_customer(name="مشتری بسته"),
            subject="بسته",
            description="شرح",
            status="باز",
            assigned_to=self.after_sales_agent,
        )
        schedule_after_sales_appointment(
            actor=self.manager, request=request, appointment_at=self.now - timedelta(hours=1),
        )
        from aftersales.services import close_after_sales_request

        close_after_sales_request(actor=self.manager, request=request, reason="انجام شد")
        data = reminders.reminders_for(self.after_sales_agent)
        kinds = [group["kind"] for group in data["groups"]]
        self.assertNotIn("after_sales_appointment", kinds)


class MoneyReminderTests(ReminderFixtures):
    """Cheques and instalments — the two sources with a week of lead time."""

    def setUp(self):
        super().setUp()
        self.customer = self.a_customer(name="مشتری مالی")

    def a_cheque(self, *, due_date):
        payment = register_payment(
            actor=self.manager,
            customer=self.customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("1000000.00"),
            cheque={
                "bank_name": "بانک نمونه",
                "serial_number": f"SER-{due_date.isoformat()}",
                "due_date": due_date,
            },
        )
        return payment.cheque

    def test_a_cheque_due_inside_the_week_is_a_reminder(self):
        self.a_cheque(due_date=timezone.localdate() + timedelta(days=3))
        data = reminders.reminders_for(self.manager)
        kinds = [group["kind"] for group in data["groups"]]
        self.assertIn("cheque_due", kinds)

    def test_a_cheque_due_beyond_the_week_is_not_yet_a_reminder(self):
        self.a_cheque(due_date=timezone.localdate() + timedelta(days=30))
        kinds = [group["kind"] for group in reminders.reminders_for(self.manager)["groups"]]
        self.assertNotIn("cheque_due", kinds)

    def test_a_cheque_already_past_its_due_date_is_marked_overdue(self):
        self.a_cheque(due_date=timezone.localdate() - timedelta(days=2))
        group = next(
            g for g in reminders.reminders_for(self.manager)["groups"] if g["kind"] == "cheque_due"
        )
        self.assertTrue(group["items"][0]["overdue"])
        # A DateField has no clock, and the client is told so — rendering it
        # through the instant path could land it on the day before.
        self.assertEqual(group["items"][0]["due_kind"], "date")

    def test_a_cleared_cheque_stops_being_a_reminder(self):
        cheque = self.a_cheque(due_date=timezone.localdate() - timedelta(days=1))
        from billing.payments import transition_cheque

        transition_cheque(actor=self.manager, cheque=cheque, to_status="cleared")
        kinds = [group["kind"] for group in reminders.reminders_for(self.manager)["groups"]]
        self.assertNotIn("cheque_due", kinds)

    def test_an_instalment_due_inside_the_week_is_a_reminder(self):
        self._an_installment_plan(start_date=timezone.localdate() + timedelta(days=2))
        kinds = [group["kind"] for group in reminders.reminders_for(self.manager)["groups"]]
        self.assertIn("installment_due", kinds)

    def test_the_instalment_reminder_names_the_customer_through_its_invoice(self):
        self._an_installment_plan(start_date=timezone.localdate() - timedelta(days=1))
        group = next(
            g for g in reminders.reminders_for(self.manager)["groups"] if g["kind"] == "installment_due"
        )
        self.assertEqual(group["items"][0]["title"], self.customer.full_name)

    def _an_installment_plan(self, *, start_date):
        product = create_product(
            actor=self.manager, sku="REM-1", name="کالای قسطی", current_price=Decimal("500000.00"),
        )
        warehouse = create_warehouse(actor=self.manager, name="انبار یادآور", code="remwh")
        record_stock_movement(
            actor=self.manager,
            warehouse=warehouse,
            product=product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=10,
            unit_cost=Decimal("100000.00"),
        )
        invoice = create_invoice(
            actor=self.manager,
            customer=self.customer,
            items=[{"product": product, "quantity": 1}],
            warehouse=warehouse,
        )
        issue_invoice(actor=self.manager, invoice=invoice)
        return create_installment_plan(
            actor=self.manager, invoice=invoice, installment_count=2, start_date=start_date,
        )


class ScopeTests(ReminderFixtures):
    """Object scope comes from each module's own selector, never from here."""

    def test_a_marketer_sees_only_their_own_assigned_follow_up(self):
        mine = self.a_lead_due(when=self.now - timedelta(hours=2), assigned_to=self.agent)
        self.a_lead_due(when=self.now - timedelta(hours=2))  # somebody else's
        data = reminders.reminders_for(self.agent)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["groups"][0]["items"][0]["id"], mine.pk)

    def test_a_marketer_is_told_nothing_about_company_money(self):
        customer = self.a_customer(name="مشتری چک")
        register_payment(
            actor=self.manager,
            customer=customer,
            method=Payment.Method.CHEQUE,
            amount=Decimal("2000000.00"),
            cheque={
                "bank_name": "بانک نمونه",
                "serial_number": "SER-SCOPE-1",
                "due_date": timezone.localdate(),
            },
        )
        kinds = [group["kind"] for group in reminders.reminders_for(self.agent)["groups"]]
        self.assertNotIn("cheque_due", kinds)
        # And the manager, whose scope does include it, does see it — so the
        # assertion above is about scope, not about the row failing to exist.
        manager_kinds = [group["kind"] for group in reminders.reminders_for(self.manager)["groups"]]
        self.assertIn("cheque_due", manager_kinds)

    def test_an_after_sales_agent_gets_no_lead_follow_ups(self):
        self.a_lead_due(when=self.now - timedelta(hours=2))
        kinds = [group["kind"] for group in reminders.reminders_for(self.after_sales_agent)["groups"]]
        self.assertNotIn("lead_follow_up", kinds)


class FeatureGateTests(ReminderFixtures):
    """Availability is a separate control from permission and from scope."""

    def test_the_api_is_404_when_the_feature_is_off(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        with override_active_profile(profile_without("reminders")):
            self.assertEqual(client.get("/api/v1/reminders/").status_code, 404)
            self.assertEqual(client.get("/api/v1/reminders/count/").status_code, 404)

    def test_the_bell_is_absent_from_the_header_when_the_feature_is_off(self):
        self.client.force_login(self.manager)
        with override_active_profile(profile_without("reminders")):
            page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('id="reminder-bell-toggle"', page)

    def test_the_bell_is_in_the_header_by_default(self):
        self.client.force_login(self.manager)
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('id="reminder-bell-toggle"', page)
        self.assertIn("یادآورها", page)

    def test_a_deployment_without_payments_still_gets_its_lead_reminders(self):
        self.a_lead_due(when=self.now - timedelta(hours=1))
        with override_active_profile(profile_without("payments")):
            data = reminders.reminders_for(self.manager)
        kinds = [group["kind"] for group in data["groups"]]
        self.assertIn("lead_follow_up", kinds)
        self.assertNotIn("cheque_due", kinds)
        self.assertNotIn("installment_due", kinds)

    def test_a_deployment_without_leads_loses_only_that_source(self):
        self.a_lead_due(when=self.now - timedelta(hours=1))
        with override_active_profile(profile_without("leads")):
            data = reminders.reminders_for(self.manager)
        self.assertEqual(data["count"], 0)

    def test_reminders_is_on_by_default_unlike_the_opt_in_features(self):
        from common.deployment.registry import DEFAULT_FEATURES, DEFAULT_OFF_FEATURES

        self.assertIn("reminders", DEFAULT_FEATURES)
        self.assertNotIn("reminders", DEFAULT_OFF_FEATURES)


class ApiTests(ReminderFixtures):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.manager)

    def test_the_list_endpoint_returns_groups_and_a_true_total(self):
        self.a_lead_due(when=self.now - timedelta(hours=1))
        response = self.api.get("/api/v1/reminders/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["groups"][0]["kind"], "lead_follow_up")

    def test_the_count_endpoint_agrees_with_the_list(self):
        self.a_lead_due(when=self.now - timedelta(hours=1))
        self.a_lead_due(when=self.now - timedelta(hours=2))
        listed = self.api.get("/api/v1/reminders/").data["count"]
        counted = self.api.get("/api/v1/reminders/count/").data["count"]
        self.assertEqual(listed, counted)
        self.assertEqual(counted, 2)

    def test_neither_endpoint_may_be_cached(self):
        for url in ("/api/v1/reminders/", "/api/v1/reminders/count/"):
            with self.subTest(url=url):
                self.assertEqual(self.api.get(url)["Cache-Control"], "private, no-store")

    def test_an_anonymous_caller_is_refused(self):
        anonymous = APIClient()
        self.assertIn(anonymous.get("/api/v1/reminders/").status_code, (401, 403))

    def test_reading_the_list_does_not_clear_the_count(self):
        """No read state: only doing the work clears a reminder."""
        lead = self.a_lead_due(when=self.now - timedelta(hours=1))
        self.api.get("/api/v1/reminders/")
        self.assertEqual(self.api.get("/api/v1/reminders/count/").data["count"], 1)

        lead.next_follow_up_at = self.now + timedelta(days=3)
        lead.save(update_fields=["next_follow_up_at"])
        self.assertEqual(self.api.get("/api/v1/reminders/count/").data["count"], 0)


class GroupLimitTests(ReminderFixtures):
    def test_a_group_lists_a_page_but_reports_the_true_count(self):
        customer = self.a_customer(name="مشتری پرکار")
        for index in range(reminders.GROUP_ITEM_LIMIT + 3):
            self.a_lead_due(when=self.now - timedelta(hours=index + 1), customer=customer)
        group = reminders.reminders_for(self.manager)["groups"][0]
        self.assertEqual(group["count"], reminders.GROUP_ITEM_LIMIT + 3)
        self.assertEqual(len(group["items"]), reminders.GROUP_ITEM_LIMIT)

    def test_the_most_urgent_rows_are_the_ones_listed(self):
        customer = self.a_customer(name="مشتری ترتیب")
        oldest = self.a_lead_due(when=self.now - timedelta(days=9), customer=customer)
        for index in range(reminders.GROUP_ITEM_LIMIT + 2):
            self.a_lead_due(when=self.now - timedelta(minutes=index + 1), customer=customer)
        group = reminders.reminders_for(self.manager)["groups"][0]
        self.assertEqual(group["items"][0]["id"], oldest.pk)


class ThrottleBudgetTests(ReminderFixtures):
    """The polled badge must not spend the shared `sensitive` rate budget.

    `SensitiveRateThrottle` is one 30/min bucket per *user*, shared by every
    view that names it. The bell polls on every page load and once a minute
    after that, so throttling it there drained the budget that genuinely
    sensitive actions depend on — a user working quickly through the panel
    got a 429 on an unrelated write, with nothing on screen to explain it.
    Caught by the real-browser suite the first time; pinned here so it cannot
    come back quietly.
    """

    def test_neither_reminder_view_uses_the_sensitive_throttle(self):
        from common.reminders_views import ReminderCountView, ReminderListView
        from common.throttles import SensitiveRateThrottle

        for view in (ReminderListView, ReminderCountView):
            with self.subTest(view=view.__name__):
                classes = view().get_throttles()
                self.assertFalse(
                    [t for t in classes if isinstance(t, SensitiveRateThrottle)],
                    "the polled bell must not share the sensitive budget",
                )

    def test_many_badge_polls_in_a_row_all_succeed(self):
        api = APIClient()
        api.force_authenticate(self.manager)
        self.a_lead_due(when=self.now - timedelta(hours=1))
        for _ in range(40):
            self.assertEqual(api.get("/api/v1/reminders/count/").status_code, 200)


class DigitLocalisationTests(ReminderFixtures):
    def test_the_instalment_sequence_is_printed_in_persian_digits(self):
        MoneyReminderTests._an_installment_plan(
            self._money_case(), start_date=timezone.localdate() - timedelta(days=1),
        )
        group = next(
            g for g in reminders.reminders_for(self.manager)["groups"] if g["kind"] == "installment_due"
        )
        self.assertEqual(group["items"][0]["subtitle"], "قسط ۱")
        self.assertNotIn("1", group["items"][0]["subtitle"])

    def _money_case(self):
        """Borrow `MoneyReminderTests`' plan builder without its whole setUp."""
        case = MoneyReminderTests(methodName="test_an_instalment_due_inside_the_week_is_a_reminder")
        case.manager = self.manager
        case.customer = self.a_customer(name="مشتری ارقام")
        return case


class BadgeStyleTests(SimpleTestCase):
    """The badge must outrank the theme's own rule for badges inside buttons.

    The purchased theme ships `.btn .badge { position: relative; top: -1px; }`
    (`assets/css/style.bundle.css`). A single-class rule here loses to it, and
    when it did, the count rendered *beside* the bell inside the 40px button
    instead of over its corner, squeezing the icon off-centre. Nothing in the
    Python suite could see that — it was found in a live browser — so what is
    pinned here is the one thing that fixed it: the selector is anchored on
    the button's id, which beats two classes without `!important`.
    """

    css = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
    ).read_text(encoding="utf-8")

    def test_the_badge_rule_is_selected_through_the_button_id(self):
        self.assertIn("#reminder-bell-toggle .reminder-bell-badge {", self.css)

    def test_the_badge_is_taken_out_of_the_buttons_flow(self):
        rule = self.css.split("#reminder-bell-toggle .reminder-bell-badge {")[1].split("}")[0]
        self.assertIn("position: absolute", rule)

    def test_the_fix_does_not_reach_for_important(self):
        rule = self.css.split("#reminder-bell-toggle .reminder-bell-badge {")[1].split("}")[0]
        self.assertNotIn("!important", rule)
