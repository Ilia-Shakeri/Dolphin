from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.management.commands.bootstrap_platform_admin import Command
from accounts.models import User
from auditlog.models import ActivityLog


TEST_PASSWORD = "Long-Safe-Pass-963!"


class BootstrapPlatformAdminTests(TestCase):
    def run_command(self, *, username="platform-owner", passwords=None):
        stdout = StringIO()
        stderr = StringIO()
        entered_passwords = passwords or [TEST_PASSWORD, TEST_PASSWORD]
        with patch(
            "accounts.management.commands.bootstrap_platform_admin.getpass.getpass",
            side_effect=entered_passwords,
        ) as prompt:
            call_command(
                "bootstrap_platform_admin",
                username=username,
                stdout=stdout,
                stderr=stderr,
            )
        return stdout.getvalue(), stderr.getvalue(), prompt

    def test_creates_plain_crm_platform_admin_and_safe_system_audit(self):
        stdout, stderr, prompt = self.run_command()

        user = User.objects.get(username="platform-owner")
        self.assertEqual(user.role, User.Role.PLATFORM_ADMIN)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(TEST_PASSWORD))
        self.assertEqual(prompt.call_count, 2)
        self.assertNotIn(TEST_PASSWORD, stdout)
        self.assertNotIn(TEST_PASSWORD, stderr)

        log = ActivityLog.objects.get(
            operation="user.platform_admin_bootstrapped",
            object_id=str(user.pk),
        )
        self.assertIsNone(log.actor)
        self.assertEqual(log.object_type, "accounts.user")
        self.assertEqual(
            log.safe_changes,
            {
                "fields": ["username", "role", "is_active"],
                "password_set": True,
            },
        )
        self.assertEqual(log.request_id, "")
        self.assertIsNone(log.ip_address)

    def test_refuses_when_active_platform_admin_exists_without_prompt(self):
        User.objects.create_user(
            username="existing-platform",
            password=TEST_PASSWORD,
            role=User.Role.PLATFORM_ADMIN,
            is_active=True,
        )
        with patch(
            "accounts.management.commands.bootstrap_platform_admin.getpass.getpass",
        ) as prompt:
            with self.assertRaisesMessage(CommandError, "already exists"):
                call_command("bootstrap_platform_admin", username="next-platform")
        prompt.assert_not_called()

    def test_refuses_when_inactive_platform_admin_exists_without_prompt(self):
        User.objects.create_user(
            username="inactive-platform",
            password=TEST_PASSWORD,
            role=User.Role.PLATFORM_ADMIN,
            is_active=False,
        )
        with patch(
            "accounts.management.commands.bootstrap_platform_admin.getpass.getpass",
        ) as prompt:
            with self.assertRaisesMessage(CommandError, "already exists"):
                call_command("bootstrap_platform_admin", username="replacement-platform")
        prompt.assert_not_called()

    def test_refuses_duplicate_username_without_prompt(self):
        User.objects.create_user(
            username="used-name",
            password=TEST_PASSWORD,
            role=User.Role.SALES_AGENT,
            is_active=False,
        )
        with patch(
            "accounts.management.commands.bootstrap_platform_admin.getpass.getpass",
        ) as prompt:
            with self.assertRaisesMessage(CommandError, "Username already exists"):
                call_command("bootstrap_platform_admin", username="used-name")
        prompt.assert_not_called()

    def test_refuses_password_mismatch_without_writing(self):
        with self.assertRaisesMessage(CommandError, "do not match"):
            self.run_command(passwords=[TEST_PASSWORD, "Other-Safe-Pass-741!"])
        self.assertFalse(User.objects.exists())
        self.assertFalse(ActivityLog.objects.exists())

    def test_uses_configured_password_validators_without_leaking_password(self):
        weak_password = "12345678"
        with self.assertRaises(CommandError) as caught:
            self.run_command(passwords=[weak_password, weak_password])
        self.assertNotIn(weak_password, str(caught.exception))
        self.assertFalse(User.objects.exists())
        self.assertFalse(ActivityLog.objects.exists())

    def test_user_and_audit_write_roll_back_together(self):
        with patch(
            "accounts.management.commands.bootstrap_platform_admin.log_activity",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                self.run_command(username="rolled-back")
        self.assertFalse(User.objects.filter(username="rolled-back").exists())
        self.assertFalse(ActivityLog.objects.exists())

    def test_command_has_no_password_argument(self):
        parser = Command().create_parser("manage.py", "bootstrap_platform_admin")
        option_strings = {
            option
            for action in parser._actions
            for option in action.option_strings
        }
        self.assertNotIn("--password", option_strings)
