from pathlib import Path

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from sales.models import Customer


class RequestLimitTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="request-limit-admin",
            password="Long-Safe-Pass-741!",
            role=User.Role.PLATFORM_ADMIN,
        )

    def _client(self):
        client = APIClient()
        client.force_authenticate(self.user)
        return client

    def test_malformed_and_deep_json_fail_safely_without_writes(self):
        client = self._client()
        before = Customer.objects.count()

        malformed = client.generic(
            "POST",
            "/api/v1/customers/",
            b'{"full_name":',
            content_type="application/json",
            HTTP_X_REQUEST_ID="bad-json-1",
        )
        deep_value = "[" * 33 + "0" + "]" * 33
        deep = client.generic(
            "POST",
            "/api/v1/customers/",
            deep_value.encode("ascii"),
            content_type="application/json",
            HTTP_X_REQUEST_ID="deep-json-1",
        )

        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.data["error"], {"code": "parse_error", "request_id": "bad-json-1"})
        self.assertEqual(deep.status_code, 400)
        self.assertEqual(deep.data["error"], {"code": "parse_error", "request_id": "deep-json-1"})
        self.assertEqual(Customer.objects.count(), before)

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=128)
    def test_oversized_body_is_413_json_with_request_id(self):
        response = self._client().generic(
            "POST",
            "/api/v1/customers/",
            (b'{"full_name":"' + b"x" * 256 + b'"}'),
            content_type="application/json",
            HTTP_X_REQUEST_ID="large-body-1",
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response["X-Request-ID"], "large-body-1")
        self.assertEqual(
            response.json(),
            {
                "detail": "Request body is too large.",
                "error": {"code": "payload_too_large", "request_id": "large-body-1"},
            },
        )
        self.assertFalse(Customer.objects.exists())

    def test_edge_and_application_share_the_64_kib_limit(self):
        root = Path(__file__).resolve().parents[2]
        config = (root / "nginx" / "default.conf").read_text(encoding="utf-8")

        self.assertEqual(64 * 1024, 65536)
        self.assertIn("client_max_body_size 64k;", config)
        self.assertIn("error_page 413 = @payload_too_large;", config)
        self.assertIn('"code":"payload_too_large"', config)
