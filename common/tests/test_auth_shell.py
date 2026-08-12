import json
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase, override_settings

from accounts.models import User
from accounts.access import ROLE_CAPABILITIES
from common.ui_views import ROLE_LABELS


ROOT = Path(__file__).resolve().parents[2]


class AuthShellUnitTests(SimpleTestCase):
    def test_role_labels_cover_exact_fixed_roles(self):
        self.assertEqual(set(ROLE_LABELS), {value for value, _ in User.Role.choices})
        self.assertEqual(len(ROLE_LABELS), 4)

    def test_client_has_persian_error_states_and_same_origin_requests(self):
        script = (ROOT / "common" / "static" / "common" / "kariz-app.js").read_text(encoding="utf-8")

        for status in (403, 404, 409, 429):
            self.assertIn(f'{status}: "', script)
        self.assertIn('credentials: "same-origin"', script)
        self.assertIn('headers["X-CSRFToken"]', script)
        self.assertIn('class ApiError', script)
        self.assertNotIn(".html", script)

    def test_mobile_and_desktop_layout_contracts_exist(self):
        stylesheet = (ROOT / "common" / "static" / "common" / "kariz.css").read_text(encoding="utf-8")

        self.assertIn("grid-template-columns: 17rem minmax(0, 1fr)", stylesheet)
        self.assertIn("@media (max-width: 760px)", stylesheet)
        self.assertIn("body.nav-open .sidebar", stylesheet)
        self.assertIn("touch-action: manipulation", stylesheet)


class AuthShellBrowserTests(TestCase):
    def setUp(self):
        self.password = "Strong-pass-937!"
        self.platform = User.objects.create_user(
            username="platform.shell",
            password=self.password,
            role=User.Role.PLATFORM_ADMIN,
        )
        self.company_it = User.objects.create_user(
            username="it.shell",
            password=self.password,
            role=User.Role.COMPANY_IT,
        )
        self.manager = User.objects.create_user(
            username="manager.shell",
            password=self.password,
            role=User.Role.SALES_MANAGER,
        )
        self.agent = User.objects.create_user(
            username="agent.shell",
            password=self.password,
            role=User.Role.SALES_AGENT,
        )

    def test_public_login_is_persian_rtl_and_has_no_dead_auth_controls(self):
        response = self.client.get("/login/")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="fa" dir="rtl">', content)
        self.assertIn("ورود به سامانه", content)
        self.assertIn('action="/api/v1/auth/login/"', content)
        self.assertIn('name="username"', content)
        self.assertIn('name="password"', content)
        self.assertNotIn('action="#"', content)
        self.assertNotIn("ثبت نام", content)
        self.assertNotIn("sign-up", content)

    def test_protected_routes_redirect_anonymous_and_inactive_users(self):
        self.assertRedirects(self.client.get("/"), "/login/")
        self.client.force_login(self.agent)
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active"])

        response = self.client.get("/")

        self.assertRedirects(response, "/login/")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_desktop_user_shell_only_shows_real_routes(self):
        self.client.force_login(self.platform)

        response = self.client.get("/users/")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('name="viewport"', content)
        self.assertIn('id="app-sidebar"', content)
        self.assertIn('href="/"', content)
        self.assertIn('href="/users/"', content)
        self.assertIn('action="/api/v1/users/"', content)
        self.assertNotIn('action="#"', content)
        self.assertNotIn("roles/list.html", content)
        self.assertNotIn("ثبت نام", content)

    def test_role_aware_landing_and_navigation_match_backend_capabilities(self):
        expected = {
            User.Role.PLATFORM_ADMIN: ("پنل مدیر پلتفرم", {"users", "audit", "customers", "leads", "interactions", "sales", "products", "performance"}),
            User.Role.SALES_MANAGER: ("پنل مدیر فروشگاه", {"users", "customers", "leads", "interactions", "sales", "products", "performance"}),
            User.Role.SALES_AGENT: ("میز کار بازاریاب", {"customers", "leads", "interactions", "sales", "products", "performance"}),
        }
        for role, (title, modules) in expected.items():
            actor = {
                User.Role.PLATFORM_ADMIN: self.platform,
                User.Role.SALES_MANAGER: self.manager,
                User.Role.SALES_AGENT: self.agent,
            }[role]
            self.client.force_login(actor)
            content = self.client.get("/").content.decode("utf-8")
            with self.subTest(role=role):
                self.assertIn(title, content)
                self.assertIn(f'data-dashboard-capability="dashboard.{"platform" if role == User.Role.PLATFORM_ADMIN else "store" if role == User.Role.SALES_MANAGER else "agent"}"', content)
                for module in modules:
                    self.assertIn(f'data-module="{module}"', content)
                self.assertNotIn('href="#"', content)
                self.assertNotIn('data-future-module=', content)
                if role == User.Role.PLATFORM_ADMIN:
                    self.assertIn('data-platform-navigation="true"', content)
                else:
                    self.assertNotIn('data-platform-navigation="true"', content)
                if role == User.Role.SALES_AGENT:
                    self.assertNotIn('data-module="users"', content)
                    self.assertNotIn('data-module="audit"', content)
                    self.assertIn("محصولات (فقط خواندنی)", content)
                    self.assertIn('id="agent-work-queue"', content)
                    self.assertIn("پیگیری بعدی", content)
                else:
                    self.assertNotIn('id="agent-work-queue"', content)

    def test_mobile_shell_has_accessible_navigation_control(self):
        self.client.force_login(self.platform)

        response = self.client.get("/")

        self.assertContains(response, 'id="nav-toggle"')
        self.assertContains(response, 'aria-controls="app-sidebar"')
        self.assertContains(response, 'aria-expanded="false"')

    def test_home_renders_authoritative_label_for_each_fixed_role(self):
        role_labels = {
            User.Role.SALES_AGENT: "بازاریاب (کال سنتر)",
            User.Role.SALES_MANAGER: "مدیر فروشگاه",
            User.Role.COMPANY_IT: "مدیر فنی مشتری",
            User.Role.PLATFORM_ADMIN: "مدیر پلتفرم",
        }

        for role, label in role_labels.items():
            with self.subTest(role=role):
                user = User.objects.create_user(
                    username=f"role-label-{role}",
                    password=self.password,
                    role=role,
                )
                self.client.force_login(user)
                self.assertContains(self.client.get("/"), label)
                self.client.logout()

    def test_agent_cannot_open_user_management_but_manager_can_manage_agents(self):
        self.client.force_login(self.agent)

        home = self.client.get("/")
        denied = self.client.get("/users/")

        self.assertEqual(home.status_code, 200)
        self.assertNotContains(home, "مدیریت کاربران")
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, "اجازه مدیریت کاربران را ندارید", status_code=403)

        self.client.force_login(self.manager)
        manager_list = self.client.get("/users/")
        manager_agent = self.client.get(f"/users/{self.agent.pk}/")
        manager_platform = self.client.get(f"/users/{self.platform.pk}/")
        self.assertEqual(manager_list.status_code, 200)
        self.assertContains(manager_list, "مدیریت بازاریابان")
        self.assertEqual(manager_agent.status_code, 200)
        self.assertNotContains(manager_agent, 'id="change-role-form"')
        self.assertEqual(manager_platform.status_code, 404)

    def test_company_it_cannot_open_or_select_platform_admin(self):
        self.client.force_login(self.company_it)

        hidden = self.client.get(f"/users/{self.platform.pk}/")
        allowed = self.client.get(f"/users/{self.agent.pk}/")
        content = allowed.content.decode("utf-8")

        self.assertEqual(hidden.status_code, 404)
        self.assertContains(hidden, "کاربر پیدا نشد", status_code=404)
        self.assertEqual(allowed.status_code, 200)
        self.assertNotIn('<option value="platform_admin">', content)

    def test_platform_admin_sees_exact_controlled_role_options(self):
        self.client.force_login(self.platform)

        content = self.client.get(f"/users/{self.agent.pk}/").content.decode("utf-8")

        for role in ("sales_agent", "sales_manager", "company_it", "platform_admin"):
            self.assertEqual(content.count(f'<option value="{role}">'), 1)
        self.assertNotIn("permission", content.lower())

    @override_settings(DEBUG=False)
    def test_unknown_route_has_safe_persian_404(self):
        response = self.client.get("/route-that-does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "صفحه پیدا نشد", status_code=404)
        self.assertContains(response, "Kariz CRM | کاریز", status_code=404)


class AuthShellApiFlowTests(TestCase):
    def setUp(self):
        self.password = "Strong-pass-937!"
        self.platform = User.objects.create_user(
            username="platform.api.shell",
            password=self.password,
            role=User.Role.PLATFORM_ADMIN,
        )
        self.client = Client(enforce_csrf_checks=True)

    def _json(self, method, path, payload=None):
        csrf_token = self.client.cookies["csrftoken"].value
        return getattr(self.client, method)(
            path,
            data=json.dumps(payload) if payload is not None else None,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

    def test_same_origin_session_flow_covers_auth_and_user_lifecycle(self):
        login_page = self.client.get("/login/")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn("csrftoken", self.client.cookies)

        login = self._json("post", "/api/v1/auth/login/", {"username": self.platform.username, "password": self.password})
        self.assertEqual(login.status_code, 200)
        self.assertIn("sessionid", self.client.cookies)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

        created = self._json(
            "post",
            "/api/v1/users/",
            {
                "username": "made.by.shell",
                "password": "Another-strong-731!",
                "first_name": "کاربر",
                "last_name": "آزمایشی",
                "email": "shell@example.test",
                "phone": "02100000000",
            },
        )
        self.assertEqual(created.status_code, 201, created.content)
        created_data = created.json()
        self.assertEqual(created_data["role"], User.Role.SALES_AGENT)

        user_path = f'/api/v1/users/{created_data["id"]}/'
        self.assertEqual(self.client.get("/api/v1/users/").status_code, 200)
        self.assertEqual(self.client.get(user_path).status_code, 200)
        edited = self._json("patch", user_path, {"first_name": "ویرایش"})
        self.assertEqual(edited.status_code, 200)
        changed = self._json("post", f'{user_path}change-role/', {"role": User.Role.SALES_MANAGER})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["role"], User.Role.SALES_MANAGER)
        deactivated = self._json("patch", user_path, {"is_active": False})
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.json()["is_active"])
        self.assertEqual(self._json("post", "/api/v1/auth/logout/").status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)

    def test_shell_never_submits_server_owned_role_in_create_or_edit(self):
        self.client.force_login(self.platform)

        listing = self.client.get("/users/").content.decode("utf-8")
        detail = self.client.get(f"/users/{self.platform.pk}/").content.decode("utf-8")

        create_form = listing.split('id="create-user-form"', 1)[1].split("</form>", 1)[0]
        edit_form = detail.split('id="edit-user-form"', 1)[1].split("</form>", 1)[0]
        self.assertNotIn('name="role"', create_form)
        self.assertNotIn('name="is_active"', create_form)
        self.assertNotIn('name="role"', edit_form)
        self.assertNotIn('name="is_active"', edit_form)

    def test_me_returns_backend_authorized_capabilities(self):
        self.client.force_login(self.platform)
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["capabilities"], sorted(ROLE_CAPABILITIES[User.Role.PLATFORM_ADMIN]))
