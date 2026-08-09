from unittest import mock

from django.core.cache import cache
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import change_user_role, create_crm_user, update_crm_user
from accounts.views import UserViewSet
from auditlog.models import ActivityLog
from common.throttles import SensitiveRateThrottle
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

    def test_server_managed_account_is_hidden_and_cannot_be_taken_over(self):
        server_admin = User.objects.create_superuser(
            username="server-admin",
            password="Server-Only-Pass-963!",
        )
        for actor in (self.company_it, self.platform):
            with self.subTest(actor=actor.role):
                client = APIClient()
                client.force_authenticate(actor)
                listed = client.get("/api/v1/users/")
                self.assertEqual(listed.status_code, 200)
                self.assertNotIn(server_admin.pk, [item["id"] for item in listed.data["results"]])
                self.assertEqual(client.get(f"/api/v1/users/{server_admin.pk}/").status_code, 404)
                self.assertEqual(
                    client.patch(
                        f"/api/v1/users/{server_admin.pk}/",
                        {"password": "Taken-Over-Pass-741!"},
                        format="json",
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    client.post(
                        f"/api/v1/users/{server_admin.pk}/change-role/",
                        {"role": User.Role.SALES_MANAGER},
                        format="json",
                    ).status_code,
                    404,
                )

        with self.assertRaises(BusinessPermissionDenied):
            update_crm_user(actor=self.platform, target=server_admin, first_name="Taken")
        with self.assertRaises(BusinessPermissionDenied):
            change_user_role(actor=self.platform, target=server_admin, role=User.Role.SALES_MANAGER)
        server_admin.refresh_from_db()
        self.assertTrue(server_admin.check_password("Server-Only-Pass-963!"))
        self.assertEqual(server_admin.first_name, "")
        self.assertTrue(server_admin.is_staff)
        self.assertTrue(server_admin.is_superuser)

        server_client = APIClient()
        server_client.force_authenticate(server_admin)
        self.assertEqual(server_client.get("/api/v1/customers/").status_code, 403)
        self.assertEqual(server_client.get("/api/v1/auth/me/").status_code, 403)
        login = APIClient().post(
            "/api/v1/auth/login/",
            {"username": server_admin.username, "password": "Server-Only-Pass-963!"},
            format="json",
        )
        self.assertEqual(login.status_code, 400)
        self.assertEqual(login.data["error"]["code"], "validation_error")

    def test_django_group_or_direct_permission_blocks_crm_access(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        platform_client = APIClient()
        platform_client.force_authenticate(self.platform)
        group = Group.objects.create(name="server-group")
        self.agent.groups.add(group)
        self.assertEqual(client.get("/api/v1/customers/").status_code, 403)
        self.assertEqual(platform_client.get(f"/api/v1/users/{self.agent.pk}/").status_code, 404)

        self.agent.groups.clear()
        permission = Permission.objects.order_by("pk").first()
        self.assertIsNotNone(permission)
        self.agent.user_permissions.add(permission)
        self.assertEqual(client.get("/api/v1/customers/").status_code, 403)
        self.assertEqual(platform_client.get(f"/api/v1/users/{self.agent.pk}/").status_code, 404)

    def test_inactive_crm_account_is_visible_and_can_be_reactivated(self):
        inactive = User.objects.create_user(
            username="inactive-agent",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_AGENT,
            is_active=False,
        )
        client = APIClient()
        client.force_authenticate(self.company_it)

        listed = client.get("/api/v1/users/")
        self.assertEqual(listed.status_code, 200)
        self.assertIn(inactive.pk, [item["id"] for item in listed.data["results"]])
        detail = client.get(f"/api/v1/users/{inactive.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.data["is_active"])

        updated = client.patch(
            f"/api/v1/users/{inactive.pk}/",
            {"first_name": "Restored", "is_active": True},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.data["is_active"])
        inactive.refresh_from_db()
        self.assertTrue(inactive.is_active)
        self.assertEqual(inactive.first_name, "Restored")
        self.assertTrue(
            ActivityLog.objects.filter(
                operation="user.updated",
                object_id=str(inactive.pk),
            ).exists()
        )

    def test_inactive_actor_and_inactive_server_target_stay_blocked(self):
        inactive_it = User.objects.create_user(
            username="inactive-it",
            password="Long-Safe-Pass-741!",
            role=User.Role.COMPANY_IT,
            is_active=False,
        )
        server_target = User.objects.create_user(
            username="inactive-server-target",
            password="Server-Only-Pass-963!",
            role=User.Role.SALES_AGENT,
            is_active=False,
            is_staff=True,
        )

        inactive_client = APIClient()
        inactive_client.force_authenticate(inactive_it)
        self.assertEqual(inactive_client.get("/api/v1/users/").status_code, 403)
        self.assertEqual(
            inactive_client.patch(
                f"/api/v1/users/{self.agent.pk}/",
                {"first_name": "Blocked"},
                format="json",
            ).status_code,
            403,
        )
        with self.assertRaises(BusinessPermissionDenied):
            update_crm_user(actor=inactive_it, target=self.agent, first_name="Blocked")

        platform_client = APIClient()
        platform_client.force_authenticate(self.platform)
        listed = platform_client.get("/api/v1/users/")
        self.assertNotIn(server_target.pk, [item["id"] for item in listed.data["results"]])
        self.assertEqual(platform_client.get(f"/api/v1/users/{server_target.pk}/").status_code, 404)
        self.assertEqual(
            platform_client.patch(
                f"/api/v1/users/{server_target.pk}/",
                {"is_active": True},
                format="json",
            ).status_code,
            404,
        )
        with self.assertRaises(BusinessPermissionDenied):
            update_crm_user(actor=self.platform, target=server_target, is_active=True)
        server_target.refresh_from_db()
        self.assertFalse(server_target.is_active)
        self.assertTrue(server_target.is_staff)

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

    def test_login_and_profile_reject_unknown_or_server_fields(self):
        client = APIClient()
        for field, value in (("unexpected", "value"), ("is_staff", True), ("id", 99)):
            with self.subTest(login_field=field):
                response = client.post(
                    "/api/v1/auth/login/",
                    {
                        "username": self.agent.username,
                        "password": "strong-pass-1",
                        field: value,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

        client.force_authenticate(self.agent)
        profile = client.patch("/api/v1/auth/me/", {"id": self.company_it.pk}, format="json")
        self.assertEqual(profile.status_code, 400)
        self.assertIn("id", profile.data)

        client.force_authenticate(self.company_it)
        user_update = client.patch(f"/api/v1/users/{self.agent.pk}/", {"id": self.company_it.pk}, format="json")
        self.assertEqual(user_update.status_code, 400)
        self.assertIn("id", user_update.data)

    def test_sales_manager_user_directory_fails_closed_without_team_scope(self):
        manager = User.objects.create_user(
            username="manager-user-reader",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_MANAGER,
        )
        client = APIClient()
        client.force_authenticate(manager)
        self.assertEqual(client.get("/api/v1/users/").status_code, 403)
        self.assertEqual(client.get(f"/api/v1/users/{self.platform.pk}/").status_code, 403)

    def test_role_change_audit_has_safe_codes_only(self):
        change_user_role(actor=self.platform, target=self.agent, role=User.Role.SALES_MANAGER)
        log = ActivityLog.objects.get(operation="user.role_changed", object_id=str(self.agent.pk))
        self.assertEqual(
            log.safe_changes,
            {"from": User.Role.SALES_AGENT, "to": User.Role.SALES_MANAGER},
        )
        with self.assertRaises(BusinessRuleError):
            change_user_role(actor=self.platform, target=self.agent, role=User.Role.SALES_MANAGER)
        self.assertEqual(ActivityLog.objects.filter(operation="user.role_changed", object_id=str(self.agent.pk)).count(), 1)

    def test_last_active_platform_admin_cannot_be_deactivated_or_demoted(self):
        client = APIClient()
        client.force_authenticate(self.platform)

        deactivated = client.patch(
            f"/api/v1/users/{self.platform.pk}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(deactivated.status_code, 409)
        self.assertEqual(deactivated.data["error"]["code"], "conflict")

        demoted = client.post(
            f"/api/v1/users/{self.platform.pk}/change-role/",
            {"role": User.Role.COMPANY_IT},
            format="json",
        )
        self.assertEqual(demoted.status_code, 409)
        self.assertEqual(demoted.data["error"]["code"], "conflict")
        self.platform.refresh_from_db()
        self.assertTrue(self.platform.is_active)
        self.assertEqual(self.platform.role, User.Role.PLATFORM_ADMIN)

    def test_one_platform_admin_can_step_down_when_second_stays_active(self):
        User.objects.create_user(
            username="platform-second",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )
        client = APIClient()
        client.force_authenticate(self.platform)
        response = client.post(
            f"/api/v1/users/{self.platform.pk}/change-role/",
            {"role": User.Role.COMPANY_IT},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.platform.refresh_from_db()
        self.assertEqual(self.platform.role, User.Role.COMPANY_IT)
        self.assertEqual(
            User.objects.filter(role=User.Role.PLATFORM_ADMIN, is_active=True).count(),
            1,
        )
        log = ActivityLog.objects.get(operation="user.role_changed", object_id=str(self.platform.pk))
        self.assertEqual(log.actor_role_snapshot, User.Role.PLATFORM_ADMIN)
        self.assertEqual(log.object_role_snapshot, User.Role.PLATFORM_ADMIN)

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

    def test_api_csrf_failure_is_safe_json_and_ui_failure_stays_html(self):
        client = Client(enforce_csrf_checks=True)
        payload = {"username": self.agent.username, "password": "strong-pass-1"}
        api_response = client.post(
            "/api/v1/auth/login/",
            payload,
            HTTP_X_REQUEST_ID="csrf-login-1",
        )

        self.assertEqual(api_response.status_code, 403)
        self.assertEqual(api_response["Content-Type"], "application/json")
        self.assertEqual(api_response["X-Request-ID"], "csrf-login-1")
        self.assertEqual(
            api_response.json(),
            {
                "detail": "CSRF check failed.",
                "error": {
                    "code": "csrf_failed",
                    "request_id": "csrf-login-1",
                },
            },
        )

        ui_response = client.post(
            "/admin/login/",
            payload,
            HTTP_X_REQUEST_ID="csrf-ui-1",
        )
        self.assertEqual(ui_response.status_code, 403)
        self.assertTrue(ui_response["Content-Type"].startswith("text/html"))

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

    @mock.patch.object(SensitiveRateThrottle, "get_rate", lambda self: "1/min")
    def test_user_write_actions_use_sensitive_throttle(self):
        cache.clear()
        self.assertEqual(
            UserViewSet.sensitive_actions,
            frozenset({"create", "update", "partial_update", "change_role"}),
        )
        client = APIClient()
        client.force_authenticate(self.platform)

        first = client.post(
            f"/api/v1/users/{self.agent.pk}/change-role/",
            {"role": User.Role.SALES_MANAGER},
            format="json",
        )
        second = client.post(
            f"/api/v1/users/{self.agent.pk}/change-role/",
            {"role": User.Role.SALES_AGENT},
            format="json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.data["error"]["code"], "throttled")
        self.assertEqual(client.get("/api/v1/users/").status_code, 200)
        cache.clear()
