from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import change_user_role, create_crm_user, update_crm_user
from auditlog.models import ActivityLog
from sales.exceptions import BusinessPermissionDenied, BusinessRuleError


class AccountSecurityTests(TestCase):
    def setUp(self):
        self.company_it = User.objects.create_user(username="it", password="strong-pass-1", role=User.Role.COMPANY_IT)
        self.platform = User.objects.create_user(username="platform", password="strong-pass-1", role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="agent", password="strong-pass-1", role=User.Role.SALES_AGENT)

    def test_roles_are_fixed(self):
        self.assertEqual({value for value, _ in User.Role.choices}, {"sales_agent", "sales_manager", "company_it", "platform_admin"})
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(username="bad-role", password="Long-Safe-Pass-741!", role="bad_role")

    def test_company_it_cannot_grant_platform_admin(self):
        with self.assertRaises(BusinessPermissionDenied):
            change_user_role(actor=self.company_it, target=self.agent, role=User.Role.PLATFORM_ADMIN)

    def test_company_it_cannot_see_platform_admin(self):
        client = APIClient()
        client.force_authenticate(self.company_it)
        response = client.get("/api/v1/users/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.platform.pk, [item["id"] for item in response.data["results"]])

    def test_server_security_fields_are_rejected(self):
        client = APIClient()
        client.force_authenticate(self.company_it)
        response = client.post("/api/v1/users/", {
            "username": "bad",
            "password": "strong-pass-2",
            "is_superuser": True,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("is_superuser", response.data)
        for field, value in (("is_staff", True), ("groups", [1]), ("user_permissions", [1]), ("role", User.Role.PLATFORM_ADMIN)):
            with self.subTest(field=field):
                response = client.post("/api/v1/users/", {
                    "username": f"blocked-{field}",
                    "password": "Long-Safe-Pass-741!",
                    field: value,
                }, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_unknown_fields_are_rejected(self):
        client = APIClient()
        client.force_authenticate(self.company_it)
        response = client.post("/api/v1/users/", {
            "username": "typo",
            "password": "Long-Safe-Pass-741!",
            "frist_name": "typo",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("frist_name", response.data)

    def test_weak_password_is_rejected(self):
        client = APIClient()
        client.force_authenticate(self.company_it)
        response = client.post("/api/v1/users/", {
            "username": "weak",
            "password": "12345678",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data)

    def test_user_create_and_password_change_are_safely_audited(self):
        client = APIClient()
        client.force_authenticate(self.company_it)
        created = client.post("/api/v1/users/", {
            "username": "new-agent",
            "password": "Long-Safe-Pass-741!",
        }, format="json")
        self.assertEqual(created.status_code, 201)
        changed = client.patch(f"/api/v1/users/{created.data['id']}/", {"password": "Other-Safe-Pass-852!"}, format="json")
        self.assertEqual(changed.status_code, 200)
        logs = list(ActivityLog.objects.filter(object_id=str(created.data["id"])).values_list("operation", "safe_changes"))
        self.assertEqual({operation for operation, _ in logs}, {"user.created", "user.updated"})
        self.assertNotIn("Other-Safe-Pass-852!", str(logs))

    def test_profile_update_cannot_undo_role_change(self):
        stale_agent = User.objects.get(pk=self.agent.pk)
        change_user_role(actor=self.platform, target=self.agent, role=User.Role.SALES_MANAGER)
        update_crm_user(actor=self.platform, target=stale_agent, first_name="Fresh")
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.role, User.Role.SALES_MANAGER)
        self.assertEqual(self.agent.first_name, "Fresh")

    def test_user_service_rejects_server_role(self):
        with self.assertRaises(BusinessRuleError):
            create_crm_user(
                actor=self.platform,
                username="bypass",
                password="Long-Safe-Pass-741!",
                role=User.Role.PLATFORM_ADMIN,
            )

    def test_user_service_rejects_weak_password(self):
        with self.assertRaises(BusinessRuleError):
            create_crm_user(actor=self.platform, username="weak-service", password="12345678")

    def test_inactive_user_is_rejected(self):
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active", "updated_at"])
        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.get("/api/v1/customers/")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 403)
        self.assertEqual(client.patch("/api/v1/auth/me/", {"first_name": "No"}, format="json").status_code, 403)

    def test_login_and_logout_require_csrf(self):
        cache.clear()
        client = Client(enforce_csrf_checks=True)
        client.get("/api/v1/auth/me/")
        csrf_cookie = client.cookies.get("csrftoken")
        self.assertIsNotNone(csrf_cookie)
        payload = {"username": self.agent.username, "password": "strong-pass-1"}
        self.assertEqual(client.post("/api/v1/auth/login/", payload).status_code, 403)
        login_response = client.post("/api/v1/auth/login/", payload, HTTP_X_CSRFTOKEN=csrf_cookie.value)
        self.assertEqual(login_response.status_code, 200)
        me_response = client.get("/api/v1/auth/me/")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["username"], self.agent.username)
        csrf_cookie = client.cookies["csrftoken"]
        self.assertEqual(client.patch("/api/v1/auth/me/", {"first_name": "No CSRF"}, content_type="application/json").status_code, 403)
        profile_response = client.patch(
            "/api/v1/auth/me/",
            {"first_name": "Safe"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_cookie.value,
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertTrue(ActivityLog.objects.filter(operation="user.profile_updated", actor=self.agent).exists())
        self.assertEqual(client.post("/api/v1/auth/logout/").status_code, 403)
        csrf_cookie = client.cookies["csrftoken"]
        self.assertEqual(client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=csrf_cookie.value).status_code, 204)

    def test_login_is_throttled(self):
        cache.clear()
        client = Client(enforce_csrf_checks=True)
        client.get("/api/v1/auth/me/")
        csrf_cookie = client.cookies["csrftoken"]
        payload = {"username": self.agent.username, "password": "wrong-password"}
        responses = [
            client.post("/api/v1/auth/login/", payload, HTTP_X_CSRFTOKEN=csrf_cookie.value)
            for _ in range(11)
        ]
        self.assertEqual(responses[-1].status_code, 429)
        cache.clear()
