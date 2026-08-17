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

    def test_the_shell_comes_from_the_theme_not_from_a_second_design_system(self):
        """Layout is the purchased theme's job; the override sheet must not redo it.

        The responsive shell, sidebar and mobile drawer are the theme's own
        (`app-sidebar`, `data-kt-drawer`), so the rules that used to build a
        bespoke grid here are gone on purpose. What is left is only behaviour
        the theme does not cover, the brand mark, and the print sheet — and this
        test fails if a parallel design system starts growing back.
        """
        stylesheet = (ROOT / "common" / "static" / "common" / "kariz.css").read_text(encoding="utf-8")
        shell = (ROOT / "common" / "templates" / "common" / "base.html").read_text(encoding="utf-8")

        # The theme provides the shell.
        self.assertIn('class="app-sidebar flex-column"', shell)
        self.assertIn('data-kt-drawer="true"', shell)
        self.assertIn('data-kt-drawer-toggle="#nav-toggle"', shell)
        self.assertIn("css/style.bundle.rtl.css", shell)
        self.assertIn("js/scripts.bundle.js", shell)

        # The override sheet stays small and must not restate the theme.
        self.assertLess(len(stylesheet.splitlines()), 200)
        for recreated in ("grid-template-columns: 17rem", ".btn {", ".card {", ".table {"):
            self.assertNotIn(recreated, stylesheet, recreated)
        # It keeps exactly the three things it is for.
        self.assertIn("[hidden]", stylesheet)
        self.assertIn("dialog {", stylesheet)
        self.assertIn("@media print", stylesheet)

    def test_the_print_sheet_fits_a_phone(self):
        """The print page loads no theme bundle, so it owns its own containment.

        Each of these was a real overflow: the page box ignored its padding, the
        seven-column line-item table pushed the document sideways, and the
        totals column cut an eight-digit rial amount off at the edge of the
        sheet. On paper the table must go back to visible — a clipped line item
        is a missing line item.
        """
        stylesheet = (ROOT / "common" / "static" / "common" / "kariz.css").read_text(encoding="utf-8")
        self.assertIn(".print-page { box-sizing: border-box;", stylesheet)
        self.assertIn(".print-page .table-wrap { overflow-x: auto; }", stylesheet)
        self.assertIn(".print-page .table-wrap { overflow-x: visible; }", stylesheet)
        self.assertIn("width: min(100%, 26rem)", stylesheet)
        self.assertIn("grid-template-columns: minmax(0, 12rem) minmax(0, 1fr)", stylesheet)


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
            User.Role.SALES_MANAGER: ("پنل مدیر فروشگاه", {"customers", "leads", "interactions", "sales", "products", "performance"}),
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
                if role != User.Role.PLATFORM_ADMIN:
                    self.assertNotIn('data-module="users"', content)
                if role == User.Role.SALES_AGENT:
                    self.assertNotIn('data-module="audit"', content)
                    self.assertIn("محصولات (فقط خواندنی)", content)
                    self.assertIn('id="agent-work-queue"', content)
                    self.assertIn("پیگیری بعدی", content)
                    self.assertIn('data-performance-panel="dashboard"', content)
                    self.assertNotIn('id="dashboard-user"', content)
                else:
                    self.assertNotIn('id="agent-work-queue"', content)
                    self.assertIn('data-performance-panel="dashboard"', content)
                    self.assertIn('id="dashboard-user"', content)

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

    def test_only_platform_admin_can_open_user_management(self):
        # User administration is platform_admin only, so both the Sales Agent
        # and the Sales Manager are denied the pages and the navigation entry.
        for user in (self.agent, self.manager):
            self.client.force_login(user)
            with self.subTest(role=user.role):
                home = self.client.get("/")
                denied_list = self.client.get("/users/")
                denied_detail = self.client.get(f"/users/{self.agent.pk}/")

                self.assertEqual(home.status_code, 200)
                self.assertNotContains(home, "مدیریت کاربران")
                self.assertNotContains(home, "مدیریت بازاریابان")
                self.assertNotContains(home, 'href="/users/"')
                self.assertEqual(denied_list.status_code, 403)
                self.assertContains(denied_list, "اجازه مدیریت کاربران را ندارید", status_code=403)
                self.assertEqual(denied_detail.status_code, 403)

        self.client.force_login(self.platform)
        platform_list = self.client.get("/users/")
        platform_agent = self.client.get(f"/users/{self.agent.pk}/")
        self.assertEqual(platform_list.status_code, 200)
        self.assertContains(platform_list, "مدیریت کاربران")
        self.assertEqual(platform_agent.status_code, 200)
        self.assertContains(platform_agent, 'id="change-role-form"')

    def test_company_it_has_no_user_administration_pages(self):
        # Company IT holds no user-administration capability, so every user
        # page is denied before any target is resolved.
        self.client.force_login(self.company_it)

        home = self.client.get("/")
        platform_detail = self.client.get(f"/users/{self.platform.pk}/")
        agent_detail = self.client.get(f"/users/{self.agent.pk}/")

        self.assertEqual(home.status_code, 200)
        self.assertNotContains(home, 'href="/users/"')
        self.assertEqual(self.client.get("/users/").status_code, 403)
        self.assertEqual(platform_detail.status_code, 403)
        self.assertEqual(agent_detail.status_code, 403)

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
        self.assertContains(response, "ForooshBin | فروش‌بین", status_code=404)


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
