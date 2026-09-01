"""The header user menu, self-service sessions, and the absence of password UI.

Three things are asserted together because they are one change: the account
owner's own controls moved out of the sidebar into the theme's user menu, that
menu carries session management, and no interface anywhere offers to change a
password.
"""

import pathlib
import re

from django.contrib.sessions.models import Session
from django.test import TestCase

from accounts.models import User
from accounts.sessions import session_reference


PASSWORD = "Strong-pass-937!"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPOSITORY_ROOT / "common" / "templates" / "common"
APP_JS = REPOSITORY_ROOT / "common" / "static" / "common" / "dolphin-app.js"


class HeaderUserMenuTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="menu.manager",
            password=PASSWORD,
            role=User.Role.SALES_MANAGER,
            first_name="مدیر",
            last_name="فروش",
        )
        self.client.force_login(self.user)

    def test_the_header_carries_the_user_menu_with_name_and_role(self):
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('id="user-menu-toggle"', page)
        self.assertIn('id="user-menu"', page)
        # Opened by the theme's own KTMenu, so no Bootstrap JavaScript is needed.
        self.assertIn('data-kt-menu-trigger="click"', page)
        self.assertIn('data-kt-menu="true"', page)
        self.assertIn("مدیر فروش", page)
        self.assertIn(self.user.username, page)

    def test_the_menu_holds_profile_sessions_and_logout(self):
        page = self.client.get("/").content.decode("utf-8")
        menu = page.split('id="user-menu"', 1)[1].split("</div>\n                        </div>", 1)[0]
        self.assertIn('id="open-profile"', menu)
        self.assertIn('id="open-sessions"', menu)
        self.assertIn('id="logout-form"', menu)

    def test_the_sidebar_no_longer_carries_a_profile_entry(self):
        page = self.client.get("/").content.decode("utf-8")
        sidebar = page.split('id="app-sidebar"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn('data-module="profile"', sidebar)
        self.assertNotIn("پروفایل من", sidebar)

    def test_the_sessions_dialog_is_present_and_needs_no_bootstrap(self):
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('id="sessions-dialog"', page)
        self.assertIn('id="revoke-other-sessions"', page)
        self.assertNotIn('data-bs-toggle="modal"', page)


class SelfServiceSessionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sess.self", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def sign_in(self):
        client = self.client_class()
        self.assertTrue(client.login(username=self.user.username, password=PASSWORD))
        return client

    def test_a_user_sees_their_own_sessions_without_being_an_administrator(self):
        client = self.sign_in()
        response = client.get("/api/v1/auth/me/sessions/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["results"][0]["reference"])

    def test_the_response_never_carries_a_session_key(self):
        client = self.sign_in()
        keys = list(Session.objects.values_list("session_key", flat=True))
        body = client.get("/api/v1/auth/me/sessions/").content.decode("utf-8")
        self.assertNotIn("session_key", body)
        for key in keys:
            self.assertNotIn(key, body)

    def test_the_current_session_is_marked_and_survives_ending_the_others(self):
        first = self.sign_in()
        second = self.sign_in()
        self.assertEqual(Session.objects.count(), 2)

        listing = second.get("/api/v1/auth/me/sessions/").json()
        current = [row for row in listing["results"] if row["is_current"]]
        self.assertEqual(len(current), 1)

        ended = second.post(
            "/api/v1/auth/me/sessions/", data={}, content_type="application/json"
        )
        self.assertEqual(ended.status_code, 200)
        self.assertEqual(ended.json()["ended"], 1)
        # The caller stays signed in; the other browser does not.
        self.assertEqual(second.get("/api/v1/auth/me/").status_code, 200)
        self.assertIn(first.get("/api/v1/auth/me/").status_code, (401, 403))

    def test_one_session_can_be_ended_by_reference(self):
        first = self.sign_in()
        second = self.sign_in()
        target = session_reference(first.session.session_key)
        ended = second.post(
            "/api/v1/auth/me/sessions/",
            data={"reference": target},
            content_type="application/json",
        )
        self.assertEqual(ended.status_code, 200)
        self.assertEqual(ended.json()["ended"], 1)
        self.assertIn(first.get("/api/v1/auth/me/").status_code, (401, 403))
        self.assertEqual(second.get("/api/v1/auth/me/").status_code, 200)

    def test_an_unknown_reference_ends_nothing(self):
        client = self.sign_in()
        response = client.post(
            "/api/v1/auth/me/sessions/",
            data={"reference": "0" * 32},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Session.objects.count(), 1)

    def test_a_user_cannot_reach_another_users_sessions(self):
        other = User.objects.create_user(
            username="sess.other", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        client = self.sign_in()
        self.assertEqual(client.get(f"/api/v1/users/{other.pk}/sessions/").status_code, 403)

    def test_a_reference_is_not_the_session_key_and_cannot_be_reversed(self):
        client = self.sign_in()
        key = client.session.session_key
        reference = session_reference(key)
        self.assertNotIn(reference, key)
        self.assertNotIn(key, reference)
        self.assertEqual(reference, session_reference(key))
        self.assertNotEqual(reference, session_reference(key + "x"))


class PasswordChangeAbsentTests(TestCase):
    """No served page offers to change a password, for any role."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username="pw.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )

    def test_the_user_edit_form_has_no_password_field(self):
        target = User.objects.create_user(
            username="pw.target", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.client.force_login(self.admin)
        page = self.client.get(f"/users/{target.pk}/").content.decode("utf-8")
        edit_form = page.split('id="edit-user-form"', 1)[1].split("</form>", 1)[0]
        self.assertNotIn('type="password"', edit_form)
        self.assertNotIn('name="password"', edit_form)
        self.assertNotIn("گذرواژه", edit_form)

    def test_only_account_creation_asks_for_a_password(self):
        """Creation still sets one — an account with no password cannot sign in."""
        self.client.force_login(self.admin)
        page = self.client.get("/users/").content.decode("utf-8")
        self.assertIn('id="create-password"', page)

    def test_no_served_template_offers_a_password_change(self):
        offenders = []
        for path in TEMPLATE_ROOT.rglob("*.html"):
            if path.name == "login.html":
                continue  # Signing in is not changing a password.
            text = path.read_text(encoding="utf-8")
            for marker in ("گذرواژه تازه", "تغییر گذرواژه", "تغییر رمز", "new-password"):
                if marker in text and "create-password" not in text:
                    offenders.append(f"{path.name}: {marker}")
        self.assertEqual(offenders, [])

    def test_the_edit_request_sends_no_password(self):
        script = APP_JS.read_text(encoding="utf-8")
        edit_block = script.split('const editForm = document.getElementById("edit-user-form");', 1)[1]
        edit_block = edit_block.split("const roleForm", 1)[0]
        self.assertNotIn('"password"', edit_block)
        self.assertNotIn("payload.password", edit_block)
