"""The person profile (2.19.0): adapters, the page, its timeline API and the
fields and presence tracking it introduced.

What is worth proving:

* **scope is the owning module's** — a customer outside the reader's book and
  a colleague outside every scope they hold are 404s, never 403s;
* **what is not permitted is not rendered** — a tab of a disabled feature or
  unpermitted data is absent from the page, not merely hidden;
* **nothing on the page is decorative** — every quick action links, switches
  a tab or runs a named behaviour;
* **the new data is safe on existing rows** — phone normalisation is kept in
  step by `User.save()` and backfilled idempotently; presence writes at most
  once per interval and never on an anonymous request.
"""

from datetime import timedelta
from importlib import import_module

from django.apps import apps as global_apps
from django.db import connection
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.middleware import ONLINE_WINDOW, PresenceMiddleware, is_online
from accounts.models import User
from accounts.services import update_crm_user, update_own_profile
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessRuleError
from common.phones import normalized_or_blank
from common.provinces import province_names
from common.ui_views import ROLE_LABELS as PAGE_ROLE_LABELS
from profiles import adapters as profile_adapters
from profiles.registry import PersonAdapter, adapter_for, person_types, register, resolve_person
from sales.services import create_customer_with_phone, create_lead, reassign_lead, record_interaction

PASSWORD = "Strong-pass-448!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class Fixtures(TestCase):
    counter = 0

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(
            username="pp.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.manager = User.objects.create_user(
            username="pp.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="pp.agent", password=PASSWORD, role=User.Role.SALES_AGENT,
            first_name="نگار", last_name="محمدی", phone="0912 111 2233",
        )
        self.other_agent = User.objects.create_user(
            username="pp.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def a_customer(self, name="مشتری پروفایل", *, actor=None, **extra):
        Fixtures.counter += 1
        return create_customer_with_phone(
            actor=actor or self.manager,
            full_name=name,
            phone={"raw_phone": f"0915000{Fixtures.counter:04d}", "is_primary": True},
            **extra,
        )

    def page(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)


class RegistryTests(TestCase):
    def test_both_person_types_are_registered(self):
        self.assertEqual(person_types(), ("customer", "user"))
        self.assertIsInstance(adapter_for("customer"), profile_adapters.CustomerAdapter)
        self.assertIsNone(adapter_for("supplier"))

    def test_a_second_adapter_class_may_not_claim_a_taken_key(self):
        class Impostor(PersonAdapter):
            key = "customer"

        with self.assertRaises(ValueError):
            register(Impostor())

    def test_an_unknown_type_resolves_to_nothing(self):
        user = User.objects.create_user(username="pp.reg", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.assertEqual(resolve_person(user, "supplier", 1), (None, None))

    def test_role_labels_match_the_panels_own(self):
        self.assertEqual(profile_adapters.ROLE_LABELS, PAGE_ROLE_LABELS)


class PhoneAndProvinceFieldTests(Fixtures):
    def test_save_keeps_the_normalised_phone_in_step(self):
        self.assertEqual(self.agent.normalized_phone, "+989121112233")
        self.agent.phone = "۰۹۱۳۵۵۵۶۶۷۷"
        self.agent.save(update_fields=["phone"])
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.normalized_phone, "+989135556677")

    def test_a_number_that_does_not_normalise_is_kept_but_not_matched(self):
        self.agent.phone = "داخلی ۲۰۴"
        self.agent.save()
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.phone, "داخلی ۲۰۴")
        self.assertEqual(self.agent.normalized_phone, "")
        self.assertEqual(normalized_or_blank(""), "")
        self.assertEqual(normalized_or_blank(None), "")

    def test_the_backfill_fills_old_rows_and_is_idempotent(self):
        migration = import_module("accounts.migrations.0008_backfill_user_normalized_phone")
        User.objects.filter(pk=self.agent.pk).update(normalized_phone="")
        migration.backfill(global_apps, None)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.normalized_phone, "+989121112233")
        with CaptureQueriesContext(connection) as queries:
            migration.backfill(global_apps, None)
        self.assertFalse(any("UPDATE" in query["sql"] for query in queries.captured_queries))

    def test_an_admin_sets_a_known_province_and_a_job_title(self):
        province = province_names()[0]
        target = update_crm_user(actor=self.admin, target=self.agent, province=province, job_title="  کارشناس فروش ")
        self.assertEqual(target.province, province)
        self.assertEqual(target.job_title, "کارشناس فروش")

    def test_an_unknown_province_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            update_crm_user(actor=self.admin, target=self.agent, province="استان خیالی")
        with self.assertRaises(BusinessRuleError):
            update_own_profile(actor=self.agent, province="استان خیالی")

    def test_a_person_edits_their_own_title_and_province_through_me(self):
        api = APIClient()
        api.force_authenticate(self.agent)
        province = province_names()[3]
        response = api.patch("/api/v1/auth/me/", {"job_title": "سرپرست تیم", "province": province}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["job_title"], "سرپرست تیم")
        self.assertEqual(response.data["normalized_phone"], "+989121112233")
        refused = api.patch("/api/v1/auth/me/", {"normalized_phone": "+989000000000"}, format="json")
        self.assertEqual(refused.status_code, 400)


class PresenceTests(Fixtures):
    def middleware(self):
        return PresenceMiddleware(lambda request: None)

    def request_for(self, user, *, cookie=True):
        request = RequestFactory().get("/")
        if cookie:
            request.COOKIES["sessionid"] = "x"
        request.user = user
        return request

    def test_a_signed_in_request_records_presence_once_per_interval(self):
        self.middleware()(self.request_for(self.agent))
        self.agent.refresh_from_db()
        first = self.agent.last_seen_at
        self.assertIsNotNone(first)
        self.middleware()(self.request_for(self.agent))
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.last_seen_at, first)

    def test_presence_does_not_touch_updated_at(self):
        before = User.objects.get(pk=self.agent.pk).updated_at
        self.middleware()(self.request_for(self.agent))
        self.assertEqual(User.objects.get(pk=self.agent.pk).updated_at, before)

    def test_a_request_without_a_session_cookie_costs_no_query(self):
        with CaptureQueriesContext(connection) as queries:
            self.middleware()(self.request_for(self.agent, cookie=False))
        self.assertEqual(len(queries.captured_queries), 0)

    def test_online_means_seen_within_the_window(self):
        now = timezone.now()
        self.agent.last_seen_at = now - ONLINE_WINDOW + timedelta(seconds=5)
        self.assertTrue(is_online(self.agent, now=now))
        self.agent.last_seen_at = now - ONLINE_WINDOW - timedelta(seconds=5)
        self.assertFalse(is_online(self.agent, now=now))
        self.agent.last_seen_at = None
        self.assertFalse(is_online(self.agent, now=now))


class CustomerProfilePageTests(Fixtures):
    def test_the_header_carries_title_province_and_a_dialable_phone(self):
        province = province_names()[5]
        customer = self.a_customer(job_title="مدیر خرید", province=province)
        page = self.page(self.manager, f"/customers/{customer.pk}/").content.decode("utf-8")
        self.assertIn('data-profile-field="job_title"', page)
        self.assertIn("مدیر خرید", page)
        self.assertIn(province, page)
        self.assertIn(f'href="tel:{customer.phones.get().normalized_phone}"', page)

    def test_a_missing_title_falls_back_to_the_kind_and_a_missing_province_explains_itself(self):
        customer = self.a_customer()
        page = self.page(self.manager, f"/customers/{customer.pk}/").content.decode("utf-8")
        self.assertIn("مشتری حقیقی", page)
        self.assertIn("استان این مشتری ثبت نشده است.", page)

    def test_every_tab_is_rendered_for_a_manager(self):
        customer = self.a_customer()
        page = self.page(self.manager, f"/customers/{customer.pk}/").content.decode("utf-8")
        for key in ("overview", "info", "leads", "activity", "calls", "finance", "documents"):
            self.assertIn(f'data-profile-tab="{key}"', page)

    def test_a_tab_of_a_disabled_feature_is_not_rendered(self):
        customer = self.a_customer()
        self.client.force_login(self.manager)
        with override_active_profile(profile_without("invoices", "attachments", "customer_timeline")):
            page = self.client.get(f"/customers/{customer.pk}/").content.decode("utf-8")
        for key in ("finance", "documents", "activity"):
            self.assertNotIn(f'data-profile-tab="{key}"', page)
        self.assertNotIn("data-attachments-panel", page)
        self.assertNotIn("data-recent-activity", page)

    def test_a_customer_outside_the_readers_book_is_a_404(self):
        customer = self.a_customer()
        self.assertEqual(self.page(self.agent, f"/customers/{customer.pk}/").status_code, 404)

    def test_a_marketer_gets_no_sms_action_without_the_capability(self):
        customer = self.a_customer(actor=self.agent)
        page = self.page(self.agent, f"/customers/{customer.pk}/").content.decode("utf-8")
        self.assertIn('data-quick-action="call"', page)
        self.assertNotIn('data-quick-action="sms"', page)
        self.assertIn('data-quick-action="edit"', page)

    def test_every_quick_action_does_something(self):
        customer = self.a_customer()
        self.client.force_login(self.manager)
        response = self.client.get(f"/customers/{customer.pk}/")
        for action in (*response.context["quick_actions"], *response.context["menu_actions"]):
            with self.subTest(action=action.key):
                self.assertTrue(action.href or action.tab or action.action)


class UserProfilePageTests(Fixtures):
    def test_an_administrator_gets_the_account_tabs(self):
        page = self.page(self.admin, f"/users/{self.agent.pk}/").content.decode("utf-8")
        for key in ("overview", "info", "leads", "performance", "activity", "access"):
            self.assertIn(f'data-profile-tab="{key}"', page)
        self.assertIn('action="/api/v1/users/', page)
        self.assertIn('id="edit-username"', page)
        self.assertIn('id="permissions-dialog"', page)

    def test_a_person_edits_only_their_own_profile_fields(self):
        page = self.page(self.agent, f"/users/{self.agent.pk}/").content.decode("utf-8")
        self.assertIn('data-profile-tab="info"', page)
        self.assertIn('action="/api/v1/auth/me/"', page)
        self.assertNotIn('id="edit-username"', page)
        self.assertNotIn('id="edit-workstream"', page)
        self.assertNotIn('data-profile-tab="access"', page)

    def test_a_manager_reads_but_does_not_edit_a_marketers_profile(self):
        page = self.page(self.manager, f"/users/{self.agent.pk}/").content.decode("utf-8")
        self.assertNotIn('data-profile-tab="info"', page)
        self.assertNotIn('data-quick-action="edit"', page)
        self.assertIn('data-profile-tab="performance"', page)

    def test_presence_is_shown(self):
        User.objects.filter(pk=self.agent.pk).update(last_seen_at=timezone.now())
        page = self.page(self.manager, f"/users/{self.agent.pk}/").content.decode("utf-8")
        self.assertIn("data-profile-presence-dot", page)
        self.assertIn("bg-success", page)

    def test_the_role_stands_in_for_a_missing_job_title(self):
        page = self.page(self.manager, f"/users/{self.agent.pk}/").content.decode("utf-8")
        self.assertIn("بازاریاب (کال سنتر)", page)
        self.assertIn("سمتی ثبت نشده است", page)


class TimelineApiTests(Fixtures):
    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_a_customer_timeline_matches_the_customer_endpoint(self):
        customer = self.a_customer()
        create_lead(actor=self.manager, customer=customer, source="کمپین پروفایل")
        unified = self.api(self.manager).get(f"/api/v1/profiles/customer/{customer.pk}/timeline/")
        legacy = self.api(self.manager).get(f"/api/v1/customers/{customer.pk}/timeline/")
        self.assertEqual(unified.status_code, 200)
        self.assertEqual(unified.data, legacy.data)

    def test_a_user_timeline_tells_what_the_person_did(self):
        customer = self.a_customer()
        lead = create_lead(actor=self.manager, customer=customer, source="کمپین کاربر")
        reassign_lead(actor=self.manager, lead=lead, to_user=self.agent)
        record_interaction(
            actor=self.agent, lead=lead, phone="09150000999", direction="outbound",
            outcome="پاسخ داد", occurred_at=timezone.now() - timedelta(hours=1),
        )
        data = self.api(self.manager).get(f"/api/v1/profiles/user/{self.agent.pk}/timeline/").data
        kinds = {event["kind"] for event in data["events"]}
        self.assertEqual(kinds & {"interaction", "lead"}, {"interaction", "lead"})

    def test_limit_trims_the_page_but_not_the_count(self):
        customer = self.a_customer()
        for index in range(3):
            create_lead(actor=self.manager, customer=customer, source=f"کمپین {index}")
        data = self.api(self.manager).get(f"/api/v1/profiles/customer/{customer.pk}/timeline/?limit=2").data
        self.assertEqual(len(data["events"]), 2)
        self.assertGreaterEqual(data["count"], 3)

    def test_out_of_scope_unknown_type_and_disabled_feature_are_404(self):
        customer = self.a_customer()
        self.assertEqual(self.api(self.agent).get(f"/api/v1/profiles/customer/{customer.pk}/timeline/").status_code, 404)
        self.assertEqual(self.api(self.agent).get(f"/api/v1/profiles/user/{self.other_agent.pk}/timeline/").status_code, 404)
        self.assertEqual(self.api(self.manager).get(f"/api/v1/profiles/supplier/{customer.pk}/timeline/").status_code, 404)
        with override_active_profile(profile_without("customer_timeline")):
            self.assertEqual(
                self.api(self.manager).get(f"/api/v1/profiles/customer/{customer.pk}/timeline/").status_code, 404
            )

    def test_a_signed_out_request_is_refused(self):
        customer = self.a_customer()
        self.assertEqual(APIClient().get(f"/api/v1/profiles/customer/{customer.pk}/timeline/").status_code, 403)


class LeadAssigneeFilterTests(Fixtures):
    def test_assigned_to_narrows_the_readers_own_scope(self):
        customer = self.a_customer()
        mine = create_lead(actor=self.manager, customer=customer, source="الف")
        theirs = create_lead(actor=self.manager, customer=customer, source="ب")
        reassign_lead(actor=self.manager, lead=mine, to_user=self.agent)
        reassign_lead(actor=self.manager, lead=theirs, to_user=self.other_agent)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        ids = [row["id"] for row in manager.get(f"/api/v1/leads/?assigned_to={self.agent.pk}").data["results"]]
        self.assertEqual(ids, [mine.pk])
        # An agent cannot use it to reach another marketer's leads.
        agent = APIClient()
        agent.force_authenticate(self.agent)
        self.assertEqual(agent.get(f"/api/v1/leads/?assigned_to={self.other_agent.pk}").data["results"], [])

    def test_a_malformed_assignee_is_a_400(self):
        api = APIClient()
        api.force_authenticate(self.manager)
        self.assertEqual(api.get("/api/v1/leads/?assigned_to=abc").status_code, 400)
