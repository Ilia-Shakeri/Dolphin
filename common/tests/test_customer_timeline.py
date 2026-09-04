"""The customer 360° timeline: `common.customer_timeline`, its API, the page.

What is worth proving:

* **the story is in the right order** — events sort by when the thing
  happened, not by when its row was written, which is the whole reason the
  page exists;
* **nine sources reach one column** — a call, a lead, an invoice, a payment
  and an after-sales case about the same customer all land in the same list;
* **object scope and the feature gate** — a customer outside someone's book
  is a 404 rather than a 403, a marketer sees no company money in the strip,
  and a deployment missing a source module simply lacks those events;
* **the Persian words come from one place** — several model enums carry
  English labels, and the timeline composes its sentences server-side, so
  this is the first Python reader that would have shown "Draft" to a user.
"""

import pathlib
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from aftersales.services import create_after_sales_request
from billing.models import Payment
from billing.payments import register_payment
from billing.services import create_invoice, issue_invoice
from common import customer_timeline
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import (
    create_customer_with_phone,
    create_lead,
    create_product,
    record_interaction,
)

PASSWORD = "Strong-pass-448!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class TimelineFixtures(TestCase):
    phone_counter = 0

    def setUp(self):
        self.manager = User.objects.create_user(
            username="tl.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="tl.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales_agent = User.objects.create_user(
            username="tl.aftersales", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        self.customer = self.a_customer("مشتری تاریخچه")
        self.now = timezone.now()

    def a_customer(self, name, *, actor=None):
        TimelineFixtures.phone_counter += 1
        return create_customer_with_phone(
            actor=actor or self.manager,
            full_name=name,
            phone={"raw_phone": f"0914000{TimelineFixtures.phone_counter:04d}", "is_primary": True},
        )

    def timeline(self, user=None, customer=None):
        return customer_timeline.timeline_for(user or self.manager, customer or self.customer)

    def kinds(self, data):
        return [event["kind"] for event in data["events"]]

    def an_invoice(self, *, issue=True, customer=None):
        product = create_product(
            actor=self.manager, sku=f"TL-{TimelineFixtures.phone_counter}", name="کالای تاریخچه",
            current_price=Decimal("300000.00"),
        )
        warehouse = create_warehouse(
            actor=self.manager, code=f"tlwh{TimelineFixtures.phone_counter}", name="انبار تاریخچه",
        )
        record_stock_movement(
            actor=self.manager, warehouse=warehouse, product=product,
            movement_type=StockMovement.MovementType.OPENING, quantity=5, unit_cost=Decimal("100000.00"),
        )
        invoice = create_invoice(
            actor=self.manager, customer=customer or self.customer,
            items=[{"product": product, "quantity": 1}], warehouse=warehouse,
        )
        return issue_invoice(actor=self.manager, invoice=invoice) if issue else invoice

    def a_lead_with_call(self):
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین تاریخچه")
        record_interaction(
            actor=self.manager, lead=lead, phone="09140000001",
            direction="outbound", outcome="پاسخ داد", occurred_at=self.now - timedelta(days=1),
        )
        return lead


class SourcesTests(TimelineFixtures):
    def test_every_kind_of_event_reaches_the_same_column(self):
        self.a_lead_with_call()
        self.an_invoice()
        register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH,
            amount=Decimal("100000.00"),
        )
        create_after_sales_request(
            actor=self.manager, customer=self.customer, subject="ایراد دستگاه",
            description="شرح", status="باز", assigned_to=self.after_sales_agent,
        )
        kinds = set(self.kinds(self.timeline()))
        self.assertEqual(
            kinds & {"interaction", "lead", "invoice", "payment", "after_sales"},
            {"interaction", "lead", "invoice", "payment", "after_sales"},
        )

    def test_a_customer_with_no_history_gets_an_empty_timeline(self):
        data = self.timeline()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["events"], [])

    def test_events_belonging_to_another_customer_are_not_included(self):
        other = self.a_customer("مشتری دیگر")
        create_lead(actor=self.manager, customer=other, source="کمپین دیگری")
        self.assertEqual(self.timeline()["count"], 0)
        self.assertEqual(self.timeline(customer=other)["count"], 1)

    def test_every_event_carries_a_link_to_its_own_record(self):
        lead = self.a_lead_with_call()
        urls = [event["url"] for event in self.timeline()["events"]]
        self.assertIn(f"/leads/{lead.pk}/", urls)
        self.assertTrue(all(url.startswith("/") for url in urls))


class OrderingTests(TimelineFixtures):
    def test_the_newest_event_comes_first(self):
        old_lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین قدیمی")
        # After the lead exists, so "newest" is unambiguous: `self.now` was
        # captured in setUp and predates the lead's own `created_at`.
        record_interaction(
            actor=self.manager, lead=old_lead, phone="09140000002",
            direction="inbound", outcome="تماس تازه", occurred_at=timezone.now(),
        )
        events = self.timeline()["events"]
        self.assertEqual(events[0]["kind"], "interaction")
        self.assertEqual(events[0]["title"], "تماس تازه")
        self.assertEqual(len(events), 2)

    def test_a_call_is_placed_by_when_it_happened_not_when_it_was_recorded(self):
        """A call logged today about last week belongs last week.

        Sorting on `created_at` would put it first, which is exactly the
        misreading this page exists to prevent.
        """
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین ترتیب")
        record_interaction(
            actor=self.manager, lead=lead, phone="09140000003",
            direction="outbound", outcome="تماس قدیمی", occurred_at=self.now - timedelta(days=30),
        )
        events = self.timeline()["events"]
        # The lead was created just now; the call happened a month ago.
        self.assertEqual(events[0]["kind"], "lead")
        self.assertEqual(events[-1]["title"], "تماس قدیمی")

    def test_each_event_reports_its_own_time(self):
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین زمان")
        when = self.now - timedelta(days=3)
        record_interaction(
            actor=self.manager, lead=lead, phone="09140000004",
            direction="outbound", outcome="زمان‌دار", occurred_at=when,
        )
        call = next(e for e in self.timeline()["events"] if e["kind"] == "interaction")
        self.assertEqual(call["at"][:10], when.isoformat()[:10])


class LabelTests(TimelineFixtures):
    """Several model enums carry English labels; a user must never see them."""

    def test_an_invoice_status_is_written_in_persian(self):
        self.an_invoice()
        invoice = next(e for e in self.timeline()["events"] if e["kind"] == "invoice")
        self.assertEqual(invoice["subtitle"], "صادرشده")

    def test_a_payment_method_is_written_in_persian(self):
        register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH,
            amount=Decimal("50000.00"),
        )
        payment = next(e for e in self.timeline()["events"] if e["kind"] == "payment")
        self.assertIn("نقدی", payment["subtitle"])
        self.assertIn("دریافتی", payment["subtitle"])

    def test_a_call_direction_is_written_in_persian(self):
        self.a_lead_with_call()
        call = next(e for e in self.timeline()["events"] if e["kind"] == "interaction")
        self.assertTrue(call["subtitle"].startswith("خروجی"))

    def test_no_event_leaks_an_english_enum_label(self):
        self.a_lead_with_call()
        self.an_invoice()
        register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.BANK_TRANSFER,
            amount=Decimal("70000.00"), bank_name="بانک نمونه",
        )
        english = {"Draft", "Issued", "Cancelled", "Cash", "Card", "Bank transfer", "Cheque",
                   "Inbound", "Outbound", "Sent", "Failed", "Confirmed", "Fulfilled"}
        for event in self.timeline()["events"]:
            with self.subTest(kind=event["kind"]):
                self.assertNotIn(event["subtitle"], english)


class ScopeTests(TimelineFixtures):
    def test_a_marketer_sees_no_company_money_in_the_strip(self):
        register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH,
            amount=Decimal("90000.00"),
        )
        # The customer itself has to be reachable by the marketer first, so
        # this one is entered by them.
        mine = self.a_customer("مشتری بازاریاب", actor=self.agent)
        register_payment(
            actor=self.manager, customer=mine, method=Payment.Method.CASH, amount=Decimal("10000.00"),
        )
        self.assertNotIn("payment", self.kinds(self.timeline(user=self.agent, customer=mine)))
        self.assertIn("payment", self.kinds(self.timeline(customer=mine)))

    def test_a_customer_outside_the_readers_scope_is_not_returned_at_all(self):
        self.assertIsNone(customer_timeline.visible_customer(self.agent, self.customer.pk))
        self.assertIsNotNone(customer_timeline.visible_customer(self.manager, self.customer.pk))


class FeatureGateTests(TimelineFixtures):
    def test_the_api_is_404_when_the_feature_is_off(self):
        api = APIClient()
        api.force_authenticate(self.manager)
        with override_active_profile(profile_without("customer_timeline")):
            self.assertEqual(
                api.get(f"/api/v1/customers/{self.customer.pk}/timeline/").status_code, 404
            )

    def test_the_section_is_absent_from_the_page_when_the_feature_is_off(self):
        self.client.force_login(self.manager)
        with override_active_profile(profile_without("customer_timeline")):
            page = self.client.get(f"/customers/{self.customer.pk}/").content.decode("utf-8")
        self.assertNotIn('id="customer-timeline"', page)

    def test_the_section_is_on_the_page_by_default(self):
        self.client.force_login(self.manager)
        page = self.client.get(f"/customers/{self.customer.pk}/").content.decode("utf-8")
        self.assertIn('id="customer-timeline-list"', page)
        self.assertIn("تاریخچهٔ مشتری", page)

    def test_a_deployment_without_payments_keeps_the_rest_of_the_story(self):
        self.a_lead_with_call()
        register_payment(
            actor=self.manager, customer=self.customer, method=Payment.Method.CASH,
            amount=Decimal("20000.00"),
        )
        with override_active_profile(profile_without("payments")):
            kinds = self.kinds(self.timeline())
        self.assertIn("interaction", kinds)
        self.assertNotIn("payment", kinds)

    def test_the_timeline_needs_customers_and_says_so(self):
        """A timeline is *about* a customer; nothing else is a hard dependency."""
        from common.deployment.registry import FEATURE_DEPENDENCIES

        self.assertEqual(FEATURE_DEPENDENCIES["customer_timeline"], frozenset({"customers"}))

    def test_customer_timeline_is_on_by_default(self):
        from common.deployment.registry import DEFAULT_FEATURES, DEFAULT_OFF_FEATURES

        self.assertIn("customer_timeline", DEFAULT_FEATURES)
        self.assertNotIn("customer_timeline", DEFAULT_OFF_FEATURES)


class ApiTests(TimelineFixtures):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.manager)

    def url(self, customer=None):
        return f"/api/v1/customers/{(customer or self.customer).pk}/timeline/"

    def test_the_endpoint_returns_the_merged_events(self):
        self.a_lead_with_call()
        response = self.api.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_a_customer_out_of_scope_is_a_404_not_a_403(self):
        """403 would confirm the customer exists to someone who may not know."""
        agent_api = APIClient()
        agent_api.force_authenticate(self.agent)
        self.assertEqual(agent_api.get(self.url()).status_code, 404)

    def test_a_customer_that_does_not_exist_is_also_a_404(self):
        self.assertEqual(self.api.get("/api/v1/customers/999999/timeline/").status_code, 404)

    def test_the_result_may_not_be_cached(self):
        self.assertEqual(self.api.get(self.url())["Cache-Control"], "private, no-store")

    def test_an_anonymous_caller_is_refused(self):
        self.assertIn(APIClient().get(self.url()).status_code, (401, 403))

    def test_the_endpoint_is_not_rate_limited(self):
        from common.throttles import SensitiveRateThrottle
        from common.timeline_views import CustomerTimelineView

        self.assertFalse(
            [t for t in CustomerTimelineView().get_throttles() if isinstance(t, SensitiveRateThrottle)]
        )


class CapTests(TimelineFixtures):
    def test_one_noisy_source_cannot_crowd_out_the_others(self):
        """Twenty calls must not push the invoice off the page."""
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین پرتماس")
        for index in range(customer_timeline.PER_SOURCE_LIMIT + 10):
            record_interaction(
                actor=self.manager, lead=lead, phone="09140000009",
                direction="outbound", outcome=f"تماس {index}",
                occurred_at=self.now - timedelta(minutes=index),
            )
        self.an_invoice()
        kinds = self.kinds(self.timeline())
        self.assertIn("invoice", kinds)
        self.assertEqual(kinds.count("interaction"), customer_timeline.PER_SOURCE_LIMIT)


class LabelModuleTests(SimpleTestCase):
    """The Python-side vocabulary lives in one module, not two."""

    ui_views = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "ui_views.py"
    ).read_text(encoding="utf-8")

    def test_ui_views_no_longer_defines_its_own_copy(self):
        self.assertNotIn('"draft": "پیش‌نویس"', self.ui_views)

    def test_ui_views_reads_the_shared_map(self):
        self.assertIn("DOCUMENT_STATUS_LABELS = labels.DOCUMENT_STATUS_LABELS", self.ui_views)

    def test_the_shared_map_still_answers_the_old_callers(self):
        from common.ui_views import DOCUMENT_STATUS_LABELS, SETTLEMENT_LABELS

        self.assertEqual(DOCUMENT_STATUS_LABELS["issued"], "صادرشده")
        self.assertEqual(SETTLEMENT_LABELS["paid"], "تسویه کامل")

    def test_an_untranslated_code_falls_back_to_itself(self):
        """Missing should look untranslated, not blank."""
        from common.labels import label

        self.assertEqual(label({}, "something_new"), "something_new")


class IconPathTests(SimpleTestCase):
    """Duotone keenicons are drawn from nested `.path*` spans, per glyph.

    Every icon this project names is checked against the theme's own
    stylesheet: `ki-call` has eight paths, `ki-calendar-tick` six,
    `ki-delivery` five. Rendering a fixed two draws a fraction of the glyph —
    which is what the first cut of all three topbar/timeline features did,
    found by reading the theme's CSS rather than by any test. `ki-paper-clip`
    is the sharper case: it is a *solid* icon with no `.path*` rules at all,
    so `ki-duotone` renders it blank, and the timeline uses `ki-file`.
    """

    css = (
        pathlib.Path(__file__).resolve().parents[2]
        / "assets" / "plugins" / "global" / "plugins.bundle.css"
    ).read_text(encoding="utf-8", errors="ignore")

    @classmethod
    def theme_path_count(cls, icon):
        import re

        name = icon.removeprefix("ki-")
        found = re.findall(rf"\.ki-{re.escape(name)}\s*\.path(\d+)", cls.css)
        return max((int(number) for number in found), default=0)

    def declared(self):
        """Every (icon, declared count) this project sends to the browser."""
        from common import customer_timeline, reminders, search

        pairs = {}
        for module in (reminders, search, customer_timeline):
            pairs.update(module.ICON_PATHS)
        return pairs

    def test_every_declared_icon_matches_the_themes_own_path_count(self):
        for icon, declared in self.declared().items():
            with self.subTest(icon=icon):
                self.assertEqual(declared, self.theme_path_count(icon))

    def test_every_icon_actually_used_is_declared(self):
        """An icon left out would silently fall back to two paths."""
        from common import customer_timeline, reminders, search

        declared = set(self.declared())
        used = set()
        for _feature, source in customer_timeline.SOURCES:
            used.update(self._icons_in(source))
        for _feature, source in reminders.SOURCES:
            used.update(self._icons_in(source))
        for _feature, source in search.SOURCES:
            used.update(self._icons_in(source))
        # Only icons whose real count is not the default need declaring, but
        # every one used must be *known* — an unknown name is a typo.
        for icon in used:
            with self.subTest(icon=icon):
                self.assertGreater(
                    self.theme_path_count(icon), 0, f"{icon} has no duotone paths in the theme",
                )
                if self.theme_path_count(icon) != 2:
                    self.assertIn(icon, declared, f"{icon} needs an ICON_PATHS entry")

    @staticmethod
    def _icons_in(source):
        import re

        import inspect

        return re.findall(r'"(ki-[a-z0-9-]+)"', inspect.getsource(source))

    def test_the_attachment_icon_is_a_duotone_one(self):
        """The event builders must not name the pathless solid icon.

        Checked against the builders themselves rather than the module text,
        because the module's own comment explains *why* `ki-paper-clip` was
        rejected and would match a naive substring search.
        """
        from common import customer_timeline

        self.assertGreater(self.theme_path_count("ki-file"), 0)
        self.assertEqual(self.theme_path_count("ki-paper-clip"), 0)
        for _feature, source in customer_timeline.SOURCES:
            with self.subTest(source=source.__name__):
                self.assertNotIn("ki-paper-clip", self._icons_in(source))
