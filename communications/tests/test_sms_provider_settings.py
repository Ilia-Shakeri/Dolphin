"""The SMS provider settings singleton: the service layer
(`communications/sms_provider_settings.py`), the serializers' secret
masking, and the settings API's feature/role gates.

`communications/tests/test_outbound_sms.py` covers the actual send/token
HTTP mechanics (`OAuth2ProviderRealRequestTests`) and the legacy
environment-variable path this settings row now takes precedence over
(`ProviderConfigurationTests`) — this file does not repeat that.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessRuleError
from communications.models import SmsProviderSettings
from communications.sms_provider_settings import get_sms_provider_settings, update_sms_provider_settings

PASSWORD = "Strong-pass-604!"


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class UpdateServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="sms.settings.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)

    def test_the_singleton_row_is_created_empty_on_first_read(self):
        row = get_sms_provider_settings()
        self.assertFalse(row.is_enabled)
        self.assertEqual(row.auth_mode, SmsProviderSettings.AuthMode.API_KEY)
        self.assertEqual(SmsProviderSettings.objects.count(), 1)

    def test_a_second_read_returns_the_same_row(self):
        first = get_sms_provider_settings()
        second = get_sms_provider_settings()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SmsProviderSettings.objects.count(), 1)

    def test_updating_one_field_leaves_the_rest_untouched(self):
        update_sms_provider_settings(actor=self.admin, label="اولیه", sender_id="30001234")
        row = update_sms_provider_settings(actor=self.admin, label="تازه")
        self.assertEqual(row.label, "تازه")
        self.assertEqual(row.sender_id, "30001234")

    def test_an_unknown_field_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            update_sms_provider_settings(actor=self.admin, not_a_real_field="x")

    def test_an_invalid_auth_mode_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            update_sms_provider_settings(actor=self.admin, auth_mode="carrier_pigeon")

    def test_a_malformed_body_template_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            update_sms_provider_settings(actor=self.admin, body_template="not json")

    def test_a_body_template_that_is_a_json_array_is_accepted(self):
        """TIARA's own /panel/webservice/send expects an array root."""
        row = update_sms_provider_settings(actor=self.admin, body_template='[{"a": 1}]')
        self.assertEqual(row.body_template, '[{"a": 1}]')

    def test_a_blank_body_template_is_accepted(self):
        row = update_sms_provider_settings(actor=self.admin, body_template="")
        self.assertEqual(row.body_template, "")

    def test_timeout_out_of_bounds_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            update_sms_provider_settings(actor=self.admin, timeout_seconds=0)
        with self.assertRaises(BusinessRuleError):
            update_sms_provider_settings(actor=self.admin, timeout_seconds=121)

    def test_enabling_without_a_send_url_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            update_sms_provider_settings(actor=self.admin, is_enabled=True)

    def test_enabling_oauth2_without_a_token_url_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            update_sms_provider_settings(
                actor=self.admin, is_enabled=True, auth_mode="oauth2_password", send_url="https://example.com/send",
            )

    def test_a_fully_configured_oauth2_row_is_accepted(self):
        row = update_sms_provider_settings(
            actor=self.admin, is_enabled=True, auth_mode="oauth2_password",
            send_url="https://example.com/send", token_url="https://example.com/token",
        )
        self.assertTrue(row.is_enabled)

    def test_the_activity_log_never_carries_the_password_value(self):
        update_sms_provider_settings(actor=self.admin, token_password="super-secret-value")
        entries = ActivityLog.objects.filter(operation="sms_provider_settings.updated")
        self.assertEqual(entries.count(), 1)
        self.assertNotIn("super-secret-value", json.dumps(entries.first().safe_changes))
        self.assertIn("token_password", entries.first().safe_changes["fields"])

    def test_leaving_the_password_out_keeps_the_stored_value(self):
        update_sms_provider_settings(actor=self.admin, token_password="first-value")
        row = update_sms_provider_settings(actor=self.admin, label="something else")
        self.assertEqual(row.token_password, "first-value")

    def test_an_explicit_empty_password_clears_it(self):
        update_sms_provider_settings(actor=self.admin, token_password="first-value")
        row = update_sms_provider_settings(actor=self.admin, token_password="")
        self.assertEqual(row.token_password, "")


class SerializerMaskingTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="sms.settings.serial", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_the_read_endpoint_never_returns_the_password(self):
        update_sms_provider_settings(actor=self.admin, token_password="super-secret-value")
        response = self.client.get("/api/v1/sms-provider-settings/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("token_password", response.json())
        self.assertTrue(response.json()["has_token_password"])
        self.assertNotIn("super-secret-value", response.content.decode("utf-8"))

    def test_has_token_password_is_false_before_one_is_set(self):
        response = self.client.get("/api/v1/sms-provider-settings/")
        self.assertFalse(response.json()["has_token_password"])


class AccessControlTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="sms.settings.access.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="sms.settings.access.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)

    def test_a_platform_admin_can_read_and_write(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        self.assertEqual(client.get("/api/v1/sms-provider-settings/").status_code, 200)
        response = client.post("/api/v1/sms-provider-settings/", {"label": "تست"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["label"], "تست")

    def test_a_non_admin_role_is_refused_with_403_not_a_leak(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        self.assertEqual(client.get("/api/v1/sms-provider-settings/").status_code, 403)
        self.assertEqual(client.post("/api/v1/sms-provider-settings/", {}, format="json").status_code, 403)

    def test_the_page_is_404_when_outbound_sms_is_off(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        with override_active_profile(profile_without("outbound_sms")):
            self.assertEqual(client.get("/api/v1/sms-provider-settings/").status_code, 404)

    def test_an_unwritable_server_field_is_refused(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post("/api/v1/sms-provider-settings/", {"id": 9}, format="json")
        self.assertEqual(response.status_code, 400)


class _StubEndpointHandler(BaseHTTPRequestHandler):
    """A minimal GET-only server for the "تست اتصال" endpoint's own test."""

    def do_GET(self):
        self.server.last_request_headers = dict(self.headers.items())
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"balance": 12345}')

    def log_message(self, *args):
        pass


class TestConnectionViewTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _StubEndpointHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        super().tearDownClass()

    def setUp(self):
        self.admin = User.objects.create_user(username="sms.settings.test.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_a_configured_test_url_reports_success(self):
        update_sms_provider_settings(actor=self.admin, test_url=f"http://127.0.0.1:{self.port}/balance")
        response = self.client.post("/api/v1/sms-provider-settings/test/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertIn("HTTP 200", response.json()["status_detail"])

    def test_no_test_url_configured_is_a_reported_failure_not_an_error(self):
        response = self.client.post("/api/v1/sms-provider-settings/test/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])
