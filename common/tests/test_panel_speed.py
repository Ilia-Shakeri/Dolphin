"""Panel speed (2.18.9).

Product owner, 2026-09-27: «سرعت پنل باید بیشتر شود و زمان بارگذاری صفحه‌ها
کمتر شود». What was actually slow, measured before any change:

* every page load re-asked for ~7 MB of uncompressed static assets (nginx
  sent them with `expires -1` and no gzip);
* a list page ran 24 queries, 16 of them the same two permission lookups
  about the signed-in user, asked again and again while rendering;
* the dashboard counted twelve scopes whichever tiles the role held;
* three single-request Gunicorn workers, so one slow request held a third of
  the site.
"""

import re
from pathlib import Path

from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from accounts.access import capabilities_for, is_crm_account
from accounts.models import User, UserCapabilityOverride
from common.request_context import bind_request_memo, forget_request_memo, reset_request_memo

ROOT = Path(__file__).resolve().parents[2]
NGINX = (ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
BASE = (ROOT / "common" / "templates" / "common" / "base.html").read_text(encoding="utf-8")
DEPLOY = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
PASSWORD = "Strong-pass-937!"


def static_location():
    start = NGINX.index("    location /static/ {")
    return NGINX[start:NGINX.index("\n    }", start)]


class StaticDeliveryTests(SimpleTestCase):
    def test_static_files_are_compressed(self):
        block = static_location()
        self.assertIn("gzip on;", block)
        self.assertIn("application/javascript", block)
        self.assertIn("text/css", block)

    def test_a_versioned_url_is_cached_for_a_year_and_nothing_else_is(self):
        self.assertIn('default "public, max-age=31536000, immutable";', NGINX)
        self.assertIn('""      "no-cache";', NGINX)
        self.assertNotIn("expires -1;", static_location())

    def test_the_static_block_keeps_the_servers_security_headers(self):
        """`add_header` in a location replaces the server's own."""
        block = static_location()
        self.assertIn("add_header X-Request-ID $request_id always;", block)
        self.assertIn('add_header Strict-Transport-Security "${DOLPHIN_HSTS_HEADER}" always;', block)

    def test_only_static_files_are_compressed(self):
        """A dynamic response can carry a secret beside attacker-chosen text
        (BREACH); compression stays confined to the static block."""
        outside = NGINX.replace(static_location(), "")
        self.assertNotIn("gzip on;", outside)

    def test_https_speaks_http2(self):
        self.assertIn("http2 on;", NGINX)

    def test_every_bundle_the_shell_links_carries_the_release(self):
        """Year-long caching is only safe when every release changes the URL."""
        for asset in ("plugins/global/plugins.bundle.rtl.css", "css/style.bundle.rtl.css",
                      "plugins/global/plugins.bundle.js", "js/scripts.bundle.js"):
            with self.subTest(asset=asset):
                self.assertIn(f"{{% static '{asset}' %}}?v={{{{ dolphin_version }}}}", BASE)
        for template in ("leads/board.html", "orders/board.html", "leads/calendar.html",
                         "after_sales/calendar.html", "error.html"):
            text = (ROOT / "common" / "templates" / "common" / template).read_text(encoding="utf-8")
            unversioned = re.findall(r"\{% static '(?:plugins|css|js)/[^']+' %\}\"", text)
            self.assertEqual(unversioned, [], template)

    def test_a_release_that_changes_nginx_actually_reaches_nginx(self):
        self.assertIn("check_nginx_config_is_valid", DEPLOY)
        self.assertIn("$COMPOSE up -d --no-deps --force-recreate nginx", DEPLOY)
        self.assertLess(DEPLOY.index("    $COMPOSE up -d\n") if "    $COMPOSE up -d\n" in DEPLOY
                        else DEPLOY.index("    $COMPOSE up -d\r\n"), DEPLOY.index("    apply_nginx_config"))


class ServerConcurrencyTests(SimpleTestCase):
    def test_workers_are_threaded(self):
        self.assertIn('"--worker-class", "gthread", "--threads", "4"', DOCKERFILE)


class RequestMemoTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="speed.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)

    def test_outside_a_request_nothing_is_remembered(self):
        with CaptureQueriesContext(connection) as first:
            capabilities_for(self.manager)
        with CaptureQueriesContext(connection) as second:
            capabilities_for(self.manager)
        self.assertEqual(len(first.captured_queries), len(second.captured_queries))
        self.assertGreater(len(second.captured_queries), 0)

    def test_inside_a_request_each_question_is_asked_once(self):
        token = bind_request_memo()
        try:
            capabilities_for(self.manager)
            is_crm_account(self.manager)
            with CaptureQueriesContext(connection) as again:
                for _ in range(10):
                    capabilities_for(self.manager)
                    is_crm_account(self.manager)
            self.assertEqual(len(again.captured_queries), 0)
        finally:
            reset_request_memo(token)

    def test_a_changed_override_is_seen_after_forgetting(self):
        token = bind_request_memo()
        try:
            self.assertNotIn("customers.delete", capabilities_for(self.manager))
            UserCapabilityOverride.objects.create(user=self.manager, capability="customers.delete", granted=True)
            forget_request_memo()
            self.assertIn("customers.delete", capabilities_for(self.manager))
        finally:
            reset_request_memo(token)

    def test_a_list_page_runs_a_handful_of_queries(self):
        """24 before 2.18.9, 16 of them repeats of the same two lookups."""
        self.client.force_login(self.manager)
        self.client.get("/customers/")
        with CaptureQueriesContext(connection) as page:
            response = self.client.get("/customers/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(page.captured_queries), 10)

    def test_the_permission_screen_answers_with_what_it_just_saved(self):
        """The one path that changes permissions and reads them back inside a
        single request — the memo must not hand back the old answer."""
        admin = User.objects.create_user(username="speed.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.client.force_login(admin)
        matrix = self.client.get(f"/api/v1/users/{self.manager.pk}/permissions/").json()["matrix"]
        request = {key: {"read": entry["read"], "write": entry["write"], "delete": entry["delete"]}
                   for key, entry in matrix.items()}
        request["customers"]["delete"] = True
        response = self.client.patch(
            f"/api/v1/users/{self.manager.pk}/permissions/", {"matrix": request}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["matrix"]["customers"]["delete"])
