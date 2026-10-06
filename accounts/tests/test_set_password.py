"""A Platform Admin sets a user's password from the profile (2.40.32).

Product-owner decision, 2026-10-07, reversing 2026-08-18's "no interface
changes a password": admin only, Django's validators, the value never logged,
and the account's sessions end.
"""

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog

STRONG = "Strong-pass-274!"
NEW = "Tazeh-ramz-9581!"


class SetPasswordTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="sp.admin", password=STRONG, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="sp.manager", password=STRONG, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="sp.agent", password=STRONG, role=User.Role.SALES_AGENT)

    def post(self, actor, target, body):
        client = APIClient()
        client.force_login(actor)
        return client.post(f"/api/v1/users/{target.pk}/set-password/", body, format="json")

    def agent_session(self):
        store = SessionStore()
        store["_auth_user_id"] = str(self.agent.pk)
        store.create()
        return store.session_key

    def test_the_admin_sets_it_and_the_old_one_stops_working(self):
        key = self.agent_session()
        response = self.post(self.admin, self.agent, {"password": NEW, "password_confirm": NEW})
        self.assertEqual(response.status_code, 204)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.check_password(NEW))
        self.assertFalse(self.agent.check_password(STRONG))
        self.assertFalse(Session.objects.filter(session_key=key).exists())

    def test_the_value_is_never_logged(self):
        self.post(self.admin, self.agent, {"password": NEW, "password_confirm": NEW})
        row = ActivityLog.objects.get(operation="user.password_set")
        self.assertNotIn(NEW, str(row.safe_changes))

    def test_nobody_else_may(self):
        response = self.post(self.manager, self.agent, {"password": NEW, "password_confirm": NEW})
        self.assertIn(response.status_code, (403, 404))
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.check_password(STRONG))

    def test_validators_and_the_repeat_apply(self):
        self.assertEqual(self.post(self.admin, self.agent, {"password": "123", "password_confirm": "123"}).status_code, 400)
        response = self.post(self.admin, self.agent, {"password": NEW, "password_confirm": NEW + "x"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("password_confirm", response.json().get("errors", response.json()))

    def test_the_profile_offers_it_to_the_admin_only(self):
        client = APIClient()
        client.force_login(self.admin)
        self.assertContains(client.get(f"/users/{self.agent.pk}/?tab=access"), 'id="set-password-form"')
