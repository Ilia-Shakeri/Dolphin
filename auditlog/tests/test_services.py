from django.test import TestCase

from accounts.models import User
from auditlog.services import log_activity
from common.request_context import bind_request_context, reset_request_context


class AuditSafetyTests(TestCase):
    def test_unapproved_keys_and_values_never_enter_safe_changes(self):
        user = User.objects.create_user(username="audit-user", password="Long-Safe-Pass-741!")
        log = log_activity(
            actor=user,
            operation="user.tested",
            instance=user,
            changes={
                "value": "private-value",
                "password": "private-value",
                "fields": ["email", "bad value"],
                "reason_provided": True,
            },
        )
        self.assertEqual(log.safe_changes, {"fields": ["email"], "reason_provided": True})
        self.assertNotIn("private-value", str(log.safe_changes))
        self.assertEqual(log.actor_role_snapshot, User.Role.SALES_AGENT)
        self.assertEqual(log.object_role_snapshot, User.Role.SALES_AGENT)

    def test_explicit_role_snapshots_override_live_values(self):
        user = User.objects.create_user(
            username="role-snapshot-user",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_MANAGER,
        )
        log = log_activity(
            actor=user,
            operation="user.role_changed",
            instance=user,
            actor_role_snapshot=User.Role.PLATFORM_ADMIN,
            object_role_snapshot=User.Role.COMPANY_IT,
        )
        self.assertEqual(log.actor_role_snapshot, User.Role.PLATFORM_ADMIN)
        self.assertEqual(log.object_role_snapshot, User.Role.COMPANY_IT)

    def test_request_context_does_not_leak_after_reset(self):
        user = User.objects.create_user(username="context-user", password="Long-Safe-Pass-741!")
        token = bind_request_context(request_id="request-123", ip_address="203.0.113.5")
        try:
            inside = log_activity(actor=user, operation="user.inside", instance=user)
        finally:
            reset_request_context(token)
        outside = log_activity(actor=user, operation="user.outside", instance=user)

        self.assertEqual(inside.request_id, "request-123")
        self.assertEqual(str(inside.ip_address), "203.0.113.5")
        self.assertEqual(outside.request_id, "")
        self.assertIsNone(outside.ip_address)
