"""Tasks (2.20.0): scope, who may assign to whom, moving between states,
the reminders bell and the person timeline."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.reminders import reminders_for
from sales.services import create_customer_with_phone
from tasks.models import Task
from tasks.services import create_system_task
from timeline.models import TimelineEntry

PASSWORD = "Strong-pass-448!"


class Fixtures(TestCase):
    # Throttle counters live in the cache and are keyed by user id, which
    # test databases reuse; clearing keeps this module from being throttled
    # by — or throttling — the rest of the suite.
    def tearDown(self):
        cache.clear()
        super().tearDown()

    def setUp(self):
        cache.clear()
        self.manager = User.objects.create_user(username="tk.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="tk.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other = User.objects.create_user(username="tk.other", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری وظیفه", phone={"raw_phone": "09150002222", "is_primary": True}
        )

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create(self, user, **body):
        payload = {"title": "پیگیری پیش‌فاکتور", **body}
        return self.api(user).post("/api/v1/tasks/", payload, format="json")


class CreationTests(Fixtures):
    def test_an_agent_creates_a_task_for_themselves(self):
        response = self.create(self.agent)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["assignee"], self.agent.pk)
        self.assertEqual(response.data["status"], "open")

    def test_an_agent_may_not_hand_a_task_to_someone_else(self):
        self.assertEqual(self.create(self.agent, assignee=self.other.pk).status_code, 403)

    def test_a_manager_assigns_to_a_marketer_about_a_customer(self):
        response = self.create(
            self.manager, assignee=self.agent.pk, person_type="customer", person_id=self.customer.pk,
            due_at=(timezone.now() + timedelta(hours=2)).isoformat(),
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["person_url"], f"/customers/{self.customer.pk}/")
        self.assertTrue(TimelineEntry.objects.filter(kind="task_created", person_id=self.customer.pk).exists())

    def test_a_task_about_someone_outside_scope_is_refused(self):
        response = self.create(self.agent, person_type="customer", person_id=self.customer.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn("person", response.data)

    def test_a_blank_title_is_refused(self):
        self.assertEqual(self.create(self.agent, title="  ").status_code, 400)

    def test_half_a_person_reference_cannot_be_stored(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Task.objects.create(title="x", assignee=self.agent, person_type="customer", person_id=None)


class ScopeAndStateTests(Fixtures):
    def test_an_agent_sees_only_their_own_tasks(self):
        self.create(self.manager, assignee=self.other.pk)
        mine = self.create(self.agent).data
        ids = [row["id"] for row in self.api(self.agent).get("/api/v1/tasks/").data["results"]]
        self.assertEqual(ids, [mine["id"]])
        self.assertEqual(len(self.api(self.manager).get("/api/v1/tasks/").data["results"]), 2)

    def test_done_cancelled_reopened(self):
        task = self.create(self.manager, assignee=self.agent.pk, person_type="customer", person_id=self.customer.pk).data
        done = self.api(self.agent).post(f"/api/v1/tasks/{task['id']}/complete/")
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.data["status"], "done")
        self.assertTrue(TimelineEntry.objects.filter(kind="task_done", source_ref=str(task["id"])).exists())
        self.assertEqual(self.api(self.agent).post(f"/api/v1/tasks/{task['id']}/complete/").status_code, 409)
        reopened = self.api(self.agent).post(f"/api/v1/tasks/{task['id']}/reopen/")
        self.assertEqual(reopened.data["status"], "open")
        self.assertFalse(TimelineEntry.objects.filter(kind="task_done", source_ref=str(task["id"])).exists())
        self.assertEqual(self.api(self.agent).post(f"/api/v1/tasks/{task['id']}/cancel/").data["status"], "cancelled")

    def test_someone_else_cannot_close_a_task(self):
        task = self.create(self.other).data
        self.assertEqual(self.api(self.agent).post(f"/api/v1/tasks/{task['id']}/complete/").status_code, 404)

    def test_the_list_filters_by_person_and_status(self):
        about = self.create(self.manager, assignee=self.agent.pk, person_type="customer", person_id=self.customer.pk).data
        self.create(self.manager, assignee=self.agent.pk)
        rows = self.api(self.manager).get(
            f"/api/v1/tasks/?person_type=customer&person_id={self.customer.pk}&status=open"
        ).data["results"]
        self.assertEqual([row["id"] for row in rows], [about["id"]])
        self.assertEqual(self.api(self.manager).get("/api/v1/tasks/?status=nope").status_code, 400)

    def test_deletion_is_the_platform_admins_or_granted(self):
        task = self.create(self.agent).data
        self.assertEqual(self.api(self.manager).delete(f"/api/v1/tasks/{task['id']}/").status_code, 403)


class ReminderTests(Fixtures):
    def test_a_due_task_rings_the_assignees_bell_only(self):
        self.create(self.manager, assignee=self.agent.pk, due_at=(timezone.now() - timedelta(hours=1)).isoformat())
        agent_groups = {group["kind"] for group in reminders_for(self.agent)["groups"]}
        manager_groups = {group["kind"] for group in reminders_for(self.manager)["groups"]}
        self.assertIn("task_due", agent_groups)
        self.assertNotIn("task_due", manager_groups)

    def test_a_task_due_next_week_is_not_a_reminder_yet(self):
        self.create(self.agent, due_at=(timezone.now() + timedelta(days=7)).isoformat())
        self.assertNotIn("task_due", {group["kind"] for group in reminders_for(self.agent)["groups"]})


class SystemTaskTests(Fixtures):
    def test_a_system_task_is_created_once_per_cause(self):
        first = create_system_task(title="تماس بی‌پاسخ", assignee=self.agent, source="missed_call", source_ref="call-7")
        second = create_system_task(title="تماس بی‌پاسخ", assignee=self.agent, source="missed_call", source_ref="call-7")
        self.assertEqual(first.pk, second.pk)
        self.assertIsNone(first.created_by)


class FeatureGateTests(Fixtures):
    def test_without_the_feature_the_api_is_absent(self):
        with override_active_profile(DeploymentProfile(
            profile_id="client-1", features=frozenset(ALL_FEATURES) - {"tasks"}, source="signed-manifest"
        )):
            self.assertEqual(self.api(self.agent).get("/api/v1/tasks/").status_code, 404)
            self.assertNotIn("task_due", {group["kind"] for group in reminders_for(self.agent)["groups"]})
