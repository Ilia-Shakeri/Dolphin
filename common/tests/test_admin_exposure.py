"""Django Admin is a server-administration plane, not a customer surface.

Two independent layers keep it away from the customer application network:
the application only registers `admin/` when `ENABLE_DJANGO_ADMIN` is true, and
the customer-facing Nginx configuration denies `/admin/` outright.

CRM Platform Admin and Django/server administration stay separate security
planes: no CRM identity is Django staff, so enabling the route would still not
let a customer user in.
"""

import importlib
from pathlib import Path

from django.contrib import admin
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import URLPattern, URLResolver, path

from accounts.models import User


ROOT = Path(__file__).resolve().parents[2]

# A self-contained URLConf used only to prove behaviour when admin IS enabled.
urlpatterns = [path("admin/", admin.site.urls)]


def _admin_routes(patterns):
    found = []
    for entry in patterns:
        prefix = str(entry.pattern)
        if isinstance(entry, URLResolver) and prefix.startswith("admin/"):
            found.append(prefix)
        elif isinstance(entry, URLPattern) and prefix.startswith("admin/"):
            found.append(prefix)
    return found


class AdminIsDisabledByDefaultTests(TestCase):
    def test_default_settings_disable_admin(self):
        from django.conf import settings

        self.assertFalse(settings.ENABLE_DJANGO_ADMIN)

    def test_admin_routes_are_not_registered(self):
        urlconf = importlib.import_module("config.urls")
        self.assertEqual(_admin_routes(urlconf.urlpatterns), [])

    def test_anonymous_cannot_reach_admin(self):
        for target in ("/admin/", "/admin/login/"):
            with self.subTest(target=target):
                self.assertEqual(self.client.get(target).status_code, 404)

    def test_crm_user_cannot_reach_admin(self):
        User.objects.create_user(
            username="admin-probe",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )
        self.client.login(username="admin-probe", password="Long-Safe-Pass-741!")
        self.assertEqual(self.client.get("/admin/").status_code, 404)


class AdminBuildsOnlyWhenExplicitlyEnabledTests(SimpleTestCase):
    """The gate is the setting itself, and it is independent of DEBUG."""

    def test_urlpatterns_include_admin_when_enabled(self):
        urlconf = importlib.import_module("config.urls")
        with override_settings(ENABLE_DJANGO_ADMIN=True):
            self.assertNotEqual(_admin_routes(urlconf.build_urlpatterns()), [])

    def test_urlpatterns_exclude_admin_when_disabled(self):
        urlconf = importlib.import_module("config.urls")
        with override_settings(ENABLE_DJANGO_ADMIN=False):
            self.assertEqual(_admin_routes(urlconf.build_urlpatterns()), [])

    def test_debug_alone_does_not_enable_admin(self):
        urlconf = importlib.import_module("config.urls")
        with override_settings(DEBUG=True, ENABLE_DJANGO_ADMIN=False):
            self.assertEqual(_admin_routes(urlconf.build_urlpatterns()), [])

    def test_production_settings_disable_admin(self):
        source = (ROOT / "config" / "production_settings.py").read_text(encoding="utf-8")
        self.assertIn("ENABLE_DJANGO_ADMIN = False", source)


@override_settings(ROOT_URLCONF=__name__)
class CrmIdentitiesStayOutOfAdminEvenWhenEnabledTests(TestCase):
    """Registering the route must not by itself admit any CRM identity."""

    def test_no_crm_role_can_authenticate_into_admin(self):
        for role in User.Role.values:
            user = User.objects.create_user(
                username=f"admin-gate-{role}",
                password="Long-Safe-Pass-741!",
                role=role,
            )
            with self.subTest(role=role):
                self.assertFalse(user.is_staff)
                self.assertFalse(user.is_superuser)
                client = self.client_class()
                self.assertTrue(
                    client.login(username=user.username, password="Long-Safe-Pass-741!")
                )
                # Authenticated as a CRM user, but Django admin requires staff.
                self.assertEqual(client.get("/admin/").status_code, 302)
                response = client.post(
                    "/admin/login/",
                    {
                        "username": user.username,
                        "password": "Long-Safe-Pass-741!",
                        "next": "/admin/",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("Location", response)

    def test_admin_login_page_is_persian_rtl_and_kariz_branded(self):
        response = self.client.get("/admin/login/")
        content = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<html lang="fa" dir="rtl">', content)
        self.assertContains(response, "مدیریت فروش‌بین")


class NginxDeniesAdminTests(SimpleTestCase):
    """The reverse proxy denies /admin/ independently of the application."""

    def setUp(self):
        self.config = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")

    def test_admin_location_is_denied(self):
        self.assertIn("location ^~ /admin/ {", self.config)
        self.assertIn("return 404;", self.config)

    def test_admin_is_not_proxied_to_the_application(self):
        block = self.config.split("location ^~ /admin/ {", 1)[1].split("}", 1)[0]
        self.assertNotIn("proxy_pass", block)

    def test_management_network_allowlist_is_documented_for_later(self):
        # P14 configures the real management VPN/CIDR once the target-site
        # survey is done. The placeholder must stay explicit, not invented.
        self.assertIn("P14", self.config)
