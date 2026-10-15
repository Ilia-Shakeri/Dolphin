"""2.40.47 — the owner's answers of 2026-10-14, first stage.

* secondary words read at 4.5:1 in light mode (`--dolphin-text-secondary`);
* the kit's red carries white text, and reads as words, at 4.5:1 in both themes;
* every activity row names a role (BIZ-012): `system` when nothing but a command
  acted, and rows written before roles were recorded get the actor's role,
  marked as filled in afterwards;
* the store manager stays a strict subset of the Platform Admin (BIZ-005).
"""

import importlib
import re

from django.apps import apps
from django.test import SimpleTestCase, TestCase

from accounts.access import ROLE_CAPABILITIES, can_delete, capabilities_for
from accounts.models import User
from auditlog.models import ActivityLog
from auditlog.selectors import activity_logs_for
from auditlog.services import SYSTEM_ROLE, log_activity
from common.color import _hex_to_rgb, contrast_ratio
from common.stylesheets import stylesheet_text

WHITE = (255, 255, 255)


def theme_block(css, selector_start):
    """The declarations of the panel's own token block that starts with `selector_start`."""
    start = css.index(selector_start + " {\n    --bs-danger:")
    return css[start:css.index("}", start)]


def token(block, name):
    return re.search(rf"--{name}:\s*([^;]+);", block).group(1).strip()


class RedTests(SimpleTestCase):
    def test_white_on_red_and_red_as_words_read_in_both_themes(self):
        css = stylesheet_text()
        light = theme_block(css, ":root,\n[data-bs-theme=light]")
        dark = theme_block(css, "[data-bs-theme=dark]")
        light_red = _hex_to_rgb(token(light, "bs-danger"))
        self.assertGreaterEqual(contrast_ratio(WHITE, light_red), 4.5)
        for surface in ("#ffffff", "#f2f2f7", "#ffeef3"):
            self.assertGreaterEqual(contrast_ratio(_hex_to_rgb(token(light, "bs-text-danger")), _hex_to_rgb(surface)), 4.5, surface)
        self.assertGreaterEqual(contrast_ratio(WHITE, _hex_to_rgb(token(dark, "bs-danger"))), 4.5)
        for surface in ("#15171c", "#09090b", "#1b1c22", "#302024"):
            self.assertGreaterEqual(contrast_ratio(_hex_to_rgb(token(dark, "bs-text-danger")), _hex_to_rgb(surface)), 4.5, surface)
        # The rgb triplet is the same colour as the hex, so tints follow it.
        self.assertEqual(token(light, "bs-danger-rgb"), ", ".join(str(c) for c in light_red))

    def test_the_panel_draws_no_red_of_its_own(self):
        css = stylesheet_text()
        self.assertNotIn("248 40 90", css)
        self.assertIn("rgba(var(--bs-danger-rgb), 0.08)", css)


class SecondaryTextTests(SimpleTestCase):
    def test_secondary_words_are_one_step_darker_in_light_mode_only(self):
        css = stylesheet_text()
        self.assertRegex(css, r":root,\n\[data-bs-theme=light\] \{\n    --bs-text-gray-600: var\(--bs-gray-700\);\n    --dolphin-text-secondary: var\(--bs-gray-700\);")
        self.assertRegex(css, r"\[data-bs-theme=dark\] \{\n    --bs-text-gray-600: var\(--bs-gray-600\);\n    --dolphin-text-secondary: var\(--bs-gray-600\);")
        # Gray-700 is the kit's own next step and reads at 7.3:1 on white.
        self.assertGreaterEqual(contrast_ratio(_hex_to_rgb("#4B5675"), WHITE), 4.5)

    def test_no_panel_rule_writes_words_in_the_bare_gray_600(self):
        css = stylesheet_text()
        uses = re.findall(r"([^{}]*)\{[^{}]*?(?<![-\w])color: var\(--bs-gray-600\)", css)
        # The login page's eye toggle is an icon, which needs 3:1, not words.
        self.assertEqual([selector.strip().splitlines()[-1] for selector in uses], [".login-page .login-password-toggle"])
        self.assertIn("body:not([data-page=\"login\"]) .table > thead > tr > th {\n    color: var(--dolphin-text-secondary) !important;", css)


class AuditRoleTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username="role.agent", password="Strong-pass-747!", role=User.Role.SALES_AGENT)
        self.it = User.objects.create_user(username="role.it", password="Strong-pass-747!", role=User.Role.COMPANY_IT)

    def test_an_event_with_no_actor_is_the_systems(self):
        log = log_activity(actor=None, operation="two_factor.reset", instance=self.agent)
        self.assertEqual(log.actor_role_snapshot, SYSTEM_ROLE)
        self.assertFalse(log.actor_role_inferred)
        self.assertIn(log, activity_logs_for(self.it))

    def test_rows_written_before_roles_were_recorded_get_one(self):
        with_actor = ActivityLog.objects.create(actor=self.agent, operation="customer.created", object_type="sales.customer", object_id="1")
        without_actor = ActivityLog.objects.create(actor=None, operation="two_factor.reset", object_type="accounts.user", object_id="2")
        recorded = log_activity(actor=self.agent, operation="customer.updated", instance=self.agent)
        migration = importlib.import_module("auditlog.migrations.0003_activitylog_actor_role_inferred")
        migration.fill_roles(apps, None)
        with_actor.refresh_from_db()
        without_actor.refresh_from_db()
        recorded.refresh_from_db()
        self.assertEqual((with_actor.actor_role_snapshot, with_actor.actor_role_inferred), (User.Role.SALES_AGENT, True))
        self.assertEqual((without_actor.actor_role_snapshot, without_actor.actor_role_inferred), (SYSTEM_ROLE, True))
        self.assertFalse(recorded.actor_role_inferred)
        # Reversible: exactly the filled rows go back to empty.
        migration.empty_filled_roles(apps, None)
        with_actor.refresh_from_db()
        recorded.refresh_from_db()
        self.assertEqual(with_actor.actor_role_snapshot, "")
        self.assertEqual(recorded.actor_role_snapshot, User.Role.SALES_AGENT)

    def test_the_page_says_when_a_role_was_filled_in(self):
        admin = User.objects.create_user(username="role.admin", password="Strong-pass-747!", role=User.Role.PLATFORM_ADMIN)
        log = ActivityLog.objects.create(actor=self.agent, operation="customer.created", object_type="sales.customer", object_id="1",
                                         actor_role_snapshot=User.Role.SALES_AGENT, actor_role_inferred=True)
        self.client.force_login(admin)
        payload = self.client.get(f"/api/v1/activity-logs/{log.pk}/").json()
        self.assertTrue(payload["actor_role_inferred"])
        from pathlib import Path
        config = (Path(__file__).resolve().parents[1] / "static" / "common" / "js" / "core" / "config.js").read_text(encoding="utf-8")
        self.assertIn('system: "سامانه"', config)
        self.assertIn("(نقش فعلی)", config)


class ManagerBoundaryTests(TestCase):
    def test_the_store_manager_is_a_strict_subset_of_the_platform_admin(self):
        # `dashboard.*` names which dashboard a role opens on, not a power.
        manager = {c for c in ROLE_CAPABILITIES[User.Role.SALES_MANAGER] if not c.startswith("dashboard.")}
        admin = {c for c in ROLE_CAPABILITIES[User.Role.PLATFORM_ADMIN] if not c.startswith("dashboard.")}
        self.assertLess(manager, admin)
        for capability in ("users.manage_all", "audit.all", "print_settings.manage", "customers.delete", "leads.delete"):
            with self.subTest(capability=capability):
                self.assertIn(capability, admin)
                self.assertNotIn(capability, manager)

    def test_a_manager_deletes_nothing_by_default(self):
        manager = User.objects.create_user(username="role.manager", password="Strong-pass-747!", role=User.Role.SALES_MANAGER)
        self.assertFalse(any(capability.endswith(".delete") for capability in capabilities_for(manager)))
        self.assertFalse(can_delete(manager, "customers.delete"))
