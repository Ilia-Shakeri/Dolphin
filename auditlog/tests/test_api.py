from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from auditlog.services import log_activity


class ActivityLogApiTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(
            username="audit-agent",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_AGENT,
        )
        self.manager = User.objects.create_user(
            username="audit-manager",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_MANAGER,
        )
        self.company_it = User.objects.create_user(
            username="audit-it",
            password="Long-Safe-Pass-741!",
            role=User.Role.COMPANY_IT,
        )
        self.platform = User.objects.create_user(
            username="audit-platform",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )
        self.ordinary_log = log_activity(
            actor=self.company_it,
            operation="user.updated",
            instance=self.agent,
            changes={"fields": ["first_name"]},
        )
        self.platform_log = log_activity(
            actor=self.platform,
            operation="user.updated",
            instance=self.platform,
            changes={"fields": ["first_name"]},
        )

    def test_company_it_scope_hides_platform_admin_activity(self):
        client = APIClient()
        client.force_authenticate(self.company_it)
        response = client.get("/api/v1/activity-logs/")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.ordinary_log.pk, ids)
        self.assertNotIn(self.platform_log.pk, ids)
        self.assertEqual(client.get(f"/api/v1/activity-logs/{self.platform_log.pk}/").status_code, 404)

    def test_company_it_scope_uses_role_at_action_not_live_role(self):
        platform_actor_log = log_activity(
            actor=self.platform,
            operation="customer.updated",
            instance=self.agent,
        )
        platform_target_log = log_activity(
            actor=self.company_it,
            operation="user.updated",
            instance=self.platform,
        )
        ordinary_actor_log = log_activity(
            actor=self.manager,
            operation="customer.updated",
            instance=self.agent,
        )
        self.platform.role = User.Role.SALES_AGENT
        self.platform.save(update_fields=["role", "updated_at"])
        self.manager.role = User.Role.PLATFORM_ADMIN
        self.manager.save(update_fields=["role", "updated_at"])

        client = APIClient()
        client.force_authenticate(self.company_it)
        response = client.get("/api/v1/activity-logs/")
        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.data["results"]}
        self.assertNotIn(platform_actor_log.pk, ids)
        self.assertNotIn(platform_target_log.pk, ids)
        self.assertIn(ordinary_actor_log.pk, ids)

    def test_company_it_scope_hides_legacy_rows_without_role_snapshots(self):
        legacy = ActivityLog.objects.create(
            actor=self.agent,
            operation="customer.legacy_updated",
            object_type="sales.customer",
            object_id="1",
            safe_changes={"fields": ["full_name"]},
        )
        company_client = APIClient()
        company_client.force_authenticate(self.company_it)
        ids = {
            item["id"]
            for item in company_client.get("/api/v1/activity-logs/").data["results"]
        }
        self.assertNotIn(legacy.pk, ids)

        platform_client = APIClient()
        platform_client.force_authenticate(self.platform)
        platform_ids = {
            item["id"]
            for item in platform_client.get("/api/v1/activity-logs/").data["results"]
        }
        self.assertIn(legacy.pk, platform_ids)

    def test_platform_admin_reads_all_and_route_is_read_only(self):
        client = APIClient()
        client.force_authenticate(self.platform)
        response = client.get("/api/v1/activity-logs/?search=user.updated")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({item["id"] for item in response.data["results"]}, {self.ordinary_log.pk, self.platform_log.pk})
        self.assertEqual(client.post("/api/v1/activity-logs/", {}, format="json").status_code, 405)
        self.assertEqual(client.patch(f"/api/v1/activity-logs/{self.ordinary_log.pk}/", {}, format="json").status_code, 405)
        self.assertEqual(client.delete(f"/api/v1/activity-logs/{self.ordinary_log.pk}/").status_code, 405)

    def test_manager_and_agent_audit_access_fails_closed(self):
        for user in (self.manager, self.agent):
            with self.subTest(role=user.role):
                client = APIClient()
                client.force_authenticate(user)
                response = client.get("/api/v1/activity-logs/", HTTP_X_REQUEST_ID=f"audit-{user.role}")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.data["error"]["code"], "permission_denied")
                self.assertEqual(response.data["error"]["request_id"], response["X-Request-ID"])
