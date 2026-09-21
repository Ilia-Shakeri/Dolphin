"""Item 9 of the 2026-09-21 follow-up: «تنظیمات سامانه پست هم مثل پیامک
باید صفحه برای تنظیم کردن api داشته باشه».

Mirrors `communications/tests` coverage of `SmsProviderSettings` — the read/
update service, the masked-secret contract, the capability gate, and a real
connectivity test against an HTTP server this test suite starts itself
(the same approach `communications`' own SMS provider tests already use for
`test_connectivity`, not a mock of `urllib`).
"""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales import postal_provider
from sales.models import PostProviderSettings

PASSWORD = "Strong-pass-983!"


class _EchoHandler(BaseHTTPRequestHandler):
    """Answers every GET with 200 and echoes the header this test cares
    about, so a real request can be told apart from a fabricated one."""

    def do_GET(self):
        seen_key = self.headers.get("X-Test-Key", "")
        body = f"ok:{seen_key}".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D401 — silence stderr during tests
        pass


class PostProviderSettingsServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="post-manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="post-agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def test_a_fresh_row_is_unconfigured(self):
        row = postal_provider.get_post_provider_settings()
        self.assertFalse(row.is_enabled)
        self.assertEqual(row.api_key_header, "X-API-Key")

    def test_updating_is_independent_and_optional(self):
        postal_provider.update_post_provider_settings(actor=self.manager, label="پست الف")
        row = postal_provider.update_post_provider_settings(actor=self.manager, base_url="https://a.example/api")
        self.assertEqual(row.label, "پست الف")
        self.assertEqual(row.base_url, "https://a.example/api")

    def test_the_key_is_never_cleared_by_a_change_that_omits_it(self):
        postal_provider.update_post_provider_settings(actor=self.manager, api_key="s3cr3t")
        row = postal_provider.update_post_provider_settings(actor=self.manager, label="دوباره")
        self.assertEqual(row.api_key, "s3cr3t")

    def test_enabling_without_a_base_url_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            postal_provider.update_post_provider_settings(actor=self.manager, is_enabled=True)

    def test_an_unknown_field_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            postal_provider.update_post_provider_settings(actor=self.manager, not_a_real_field="x")

    def test_timeout_is_bounded(self):
        with self.assertRaises(BusinessRuleError):
            postal_provider.update_post_provider_settings(actor=self.manager, timeout_seconds=0)
        with self.assertRaises(BusinessRuleError):
            postal_provider.update_post_provider_settings(actor=self.manager, timeout_seconds=999)


class PostProviderConnectivityTests(TestCase):
    """A real HTTP round trip, not a mocked one — this test suite starts its
    own local server and tears it down afterwards."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = HTTPServer(("127.0.0.1", 0), _EchoHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def test_a_real_request_reaches_the_configured_url_with_the_configured_key(self):
        row = PostProviderSettings(
            test_url=f"http://127.0.0.1:{self.port}/ping",
            api_key_header="X-Test-Key",
            api_key="abc123",
            timeout_seconds=5,
        )
        result = postal_provider.test_connectivity(row)
        self.assertTrue(result.success, result.status_detail)
        # The echoed header proves the key actually travelled on the wire,
        # not merely that some request reached the server.
        self.assertIn("abc123", result.status_detail)

    def test_no_test_url_is_reported_not_attempted(self):
        row = PostProviderSettings(test_url="", timeout_seconds=5)
        result = postal_provider.test_connectivity(row)
        self.assertFalse(result.success)
        self.assertIn("تنظیم نشده", result.status_detail)

    def test_an_unreachable_host_fails_cleanly(self):
        row = PostProviderSettings(
            test_url="http://127.0.0.1:1/unreachable", timeout_seconds=2
        )
        result = postal_provider.test_connectivity(row)
        self.assertFalse(result.success)
        self.assertIn("connection error", result.status_detail)


class PostProviderSettingsApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="post-api-manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="post-api-agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_a_sales_manager_may_read_and_write(self):
        response = self._client(self.manager).get("/api/v1/post-provider-settings/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("api_key", response.data)

        response = self._client(self.manager).post(
            "/api/v1/post-provider-settings/", {"label": "پست ب", "api_key": "top-secret"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["label"], "پست ب")
        self.assertTrue(response.data["has_api_key"])
        self.assertNotIn("api_key", response.data)

    def test_a_sales_agent_may_not(self):
        response = self._client(self.agent).get("/api/v1/post-provider-settings/")
        self.assertEqual(response.status_code, 403)

    def test_signed_out_may_not(self):
        response = APIClient().get("/api/v1/post-provider-settings/")
        self.assertIn(response.status_code, {401, 403})

    def test_the_test_endpoint_tests_the_saved_row_not_the_request_body(self):
        self._client(self.manager).post(
            "/api/v1/post-provider-settings/", {"test_url": ""}, format="json"
        )
        response = self._client(self.manager).post(
            "/api/v1/post-provider-settings/test/",
            {"test_url": "http://this-is-ignored.invalid/"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["success"])
        self.assertIn("تنظیم نشده", response.data["status_detail"])
