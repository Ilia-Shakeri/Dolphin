import re

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog


class SystemApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="schema-user",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )

    def test_health_splits_liveness_and_readiness(self):
        client = APIClient()
        self.assertEqual(client.get("/api/v1/health/live/").status_code, 200)
        ready = client.get("/api/v1/health/ready/")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.data["database"], "up")

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_security_redirect_has_request_id(self):
        response = APIClient().get("/api/v1/health/live/")
        self.assertEqual(response.status_code, 301)
        self.assertRegex(response["X-Request-ID"], re.compile(r"^[0-9a-f]{32}$"))

    def test_schema_and_docs_require_active_login(self):
        client = APIClient()
        self.assertEqual(client.get("/api/v1/schema/").status_code, 403)
        self.assertEqual(client.get("/api/v1/docs/").status_code, 403)
        client.force_authenticate(self.user)
        self.assertEqual(client.get("/api/v1/schema/").status_code, 200)
        self.assertEqual(client.get("/api/v1/docs/").status_code, 200)

    def test_schema_documents_status_filters(self):
        client = APIClient()
        client.force_authenticate(self.user)
        response = client.get("/api/v1/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
        self.assertEqual(response.status_code, 200)
        lead_parameters = response.data["paths"]["/api/v1/leads/"]["get"]["parameters"]
        sale_parameters = response.data["paths"]["/api/v1/sales/"]["get"]["parameters"]
        self.assertIn("status", {parameter["name"] for parameter in lead_parameters})
        self.assertIn("status", {parameter["name"] for parameter in sale_parameters})

    def test_request_id_is_returned_and_bound_to_audit(self):
        client = APIClient()
        client.force_authenticate(self.user)
        first = client.patch(
            "/api/v1/auth/me/",
            {"first_name": "Trace"},
            format="json",
            HTTP_X_REQUEST_ID="crm.test-123",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first["X-Request-ID"], "crm.test-123")
        first_log = ActivityLog.objects.get(operation="user.profile_updated", object_id=str(self.user.pk))
        self.assertEqual(first_log.request_id, "crm.test-123")
        self.assertEqual(str(first_log.ip_address), "127.0.0.1")

        second = client.patch(
            "/api/v1/auth/me/",
            {"last_name": "Fresh"},
            format="json",
            HTTP_X_REQUEST_ID="bad request id",
        )
        self.assertEqual(second.status_code, 200)
        self.assertRegex(second["X-Request-ID"], re.compile(r"^[0-9a-f]{32}$"))
        self.assertNotEqual(second["X-Request-ID"], first["X-Request-ID"])
        second_log = ActivityLog.objects.filter(
            operation="user.profile_updated",
            object_id=str(self.user.pk),
        ).latest("id")
        self.assertEqual(second_log.request_id, second["X-Request-ID"])

    @override_settings(AUDIT_TRUSTED_PROXY_CIDRS=["10.20.0.0/24"])
    def test_audit_ip_trusts_only_configured_proxy_peer(self):
        client = APIClient()
        client.force_authenticate(self.user)
        trusted = client.patch(
            "/api/v1/auth/me/",
            {"first_name": "Trusted"},
            format="json",
            REMOTE_ADDR="10.20.0.4",
            HTTP_X_REAL_IP="203.0.113.8",
        )
        self.assertEqual(trusted.status_code, 200)
        trusted_log = ActivityLog.objects.get(operation="user.profile_updated", object_id=str(self.user.pk))
        self.assertEqual(str(trusted_log.ip_address), "203.0.113.8")

        untrusted = client.patch(
            "/api/v1/auth/me/",
            {"last_name": "Peer"},
            format="json",
            REMOTE_ADDR="198.51.100.7",
            HTTP_X_REAL_IP="203.0.113.9",
        )
        self.assertEqual(untrusted.status_code, 200)
        untrusted_log = ActivityLog.objects.filter(
            operation="user.profile_updated",
            object_id=str(self.user.pk),
        ).latest("id")
        self.assertEqual(str(untrusted_log.ip_address), "198.51.100.7")
