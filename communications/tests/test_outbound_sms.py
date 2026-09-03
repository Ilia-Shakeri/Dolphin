"""Outbound SMS: the provider core (`communications/sms.py`), the service
(`send_outbound_sms`), and the API surface it is reached through.

The HTTP provider is proven against a real `ThreadingHTTPServer` on an
OS-assigned loopback port — the same technique `test_manifest_builder.py`
uses for the same reason: a provider whose only test is a mock of
`urllib.request` could pass while the real request it builds is malformed in
a way no mock would catch (wrong method, missing Content-Type, a body that
does not survive the placeholder substitution as valid JSON).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from communications import sms
from communications.models import OutboundSMS
from communications.services import send_outbound_sms
from sales.services import create_customer_with_phone, create_lead


class _EchoHandler(BaseHTTPRequestHandler):
    """Accepts any POST; fails a message whose body contains "FAIL_ME"."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.last_request = {
            "path": self.path,
            "headers": dict(self.headers.items()),
            "body": json.loads(raw.decode("utf-8")) if raw else None,
        }
        if raw and b"FAIL_ME" in raw:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "rejected"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, *args):
        pass


class EchoServerCase(SimpleTestCase):
    """Base class starting one real HTTP server per test class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _EchoHandler)
        cls.server.last_request = None
        cls.port = cls.server.server_address[1]
        cls.url = f"http://127.0.0.1:{cls.port}/send"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        super().tearDownClass()


BODY_TEMPLATE = json.dumps({"receptor": sms.TO_PLACEHOLDER, "message": sms.BODY_PLACEHOLDER, "sender": sms.SENDER_PLACEHOLDER})


class ProviderConfigurationTests(SimpleTestCase):
    def test_unconfigured_provider_is_unavailable(self):
        with override_settings(SMS_PROVIDER=""):
            self.assertFalse(sms.provider_is_available())

    def test_a_provider_other_than_http_is_unavailable(self):
        with override_settings(SMS_PROVIDER="carrier_pigeon", SMS_API_URL="https://example.com", SMS_API_BODY_TEMPLATE="{}"):
            self.assertFalse(sms.provider_is_available())

    def test_http_without_url_or_template_is_unavailable(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL="", SMS_API_BODY_TEMPLATE=""):
            self.assertFalse(sms.provider_is_available())
        with override_settings(SMS_PROVIDER="http", SMS_API_URL="https://example.com", SMS_API_BODY_TEMPLATE=""):
            self.assertFalse(sms.provider_is_available())

    def test_fully_configured_http_provider_is_available(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL="https://example.com", SMS_API_BODY_TEMPLATE="{}"):
            self.assertTrue(sms.provider_is_available())

    def test_sending_with_no_provider_raises_unavailable(self):
        with override_settings(SMS_PROVIDER=""):
            with self.assertRaises(sms.SmsProviderUnavailable):
                sms.send_via_configured_provider(to="+989121110000", body="hi")


class HttpProviderRealRequestTests(EchoServerCase):
    """Every claim here is checked against what the server actually received."""

    def test_a_successful_send_builds_the_exact_request_the_settings_describe(self):
        with override_settings(
            SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE,
            SMS_SENDER_ID="30001234", SMS_API_HEADERS=json.dumps({"Authorization": "Bearer secret-token"}),
        ):
            result = sms.send_via_configured_provider(to="+989121110000", body="سلام")
        self.assertTrue(result.success)
        self.assertEqual(result.provider_code, "http")
        self.assertIn("HTTP 200", result.status_detail)

        received = self.server.last_request
        self.assertEqual(received["body"], {"receptor": "+989121110000", "message": "سلام", "sender": "30001234"})
        self.assertEqual(received["headers"].get("Authorization"), "Bearer secret-token")
        self.assertEqual(received["headers"].get("Content-Type"), "application/json")

    def test_placeholder_substitution_is_immune_to_quotes_and_newlines_in_the_body(self):
        """The exact injection a naive `.format()` on raw text would allow."""
        tricky_body = 'a "quoted" line\nwith a newline and a \\ backslash'
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            result = sms.send_via_configured_provider(to="+989121110000", body=tricky_body)
        self.assertTrue(result.success)
        self.assertEqual(self.server.last_request["body"]["message"], tricky_body)

    def test_a_non_2xx_response_is_a_failed_result_not_an_exception(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            result = sms.send_via_configured_provider(to="+989121110000", body="FAIL_ME please")
        self.assertFalse(result.success)
        self.assertIn("HTTP 400", result.status_detail)

    def test_a_malformed_json_template_is_a_failed_result_not_a_raise(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE="not json"):
            result = sms.send_via_configured_provider(to="+989121110000", body="hi")
        self.assertFalse(result.success)
        self.assertIn("misconfigured", result.status_detail)

    def test_malformed_headers_json_is_a_failed_result_not_a_raise(self):
        with override_settings(
            SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE,
            SMS_API_HEADERS="not json",
        ):
            result = sms.send_via_configured_provider(to="+989121110000", body="hi")
        self.assertFalse(result.success)
        self.assertIn("misconfigured", result.status_detail)

    def test_an_unreachable_url_is_a_failed_result_not_a_raise(self):
        with override_settings(
            SMS_PROVIDER="http", SMS_API_URL="http://127.0.0.1:1/", SMS_API_BODY_TEMPLATE=BODY_TEMPLATE,
        ):
            result = sms.send_via_configured_provider(to="+989121110000", body="hi")
        self.assertFalse(result.success)
        self.assertIn("connection error", result.status_detail)

    def test_the_api_key_never_appears_in_the_stored_status_detail(self):
        with override_settings(
            SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE,
            SMS_API_HEADERS=json.dumps({"Authorization": "Bearer super-secret-token"}),
        ):
            result = sms.send_via_configured_provider(to="+989121110000", body="hi")
        self.assertNotIn("super-secret-token", result.status_detail)


@override_settings(SMS_PROVIDER="")
class SendOutboundSmsPreflightTests(TestCase):
    """Validation that must be checked before any provider is even asked."""

    def setUp(self):
        self.manager = User.objects.create_user(username="sms.send.manager", password="Strong-pass-983!", role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="sms.send.agent", password="Strong-pass-983!", role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری پیامک خروجی", phone={"raw_phone": "09121110000", "is_primary": True},
        )

    def test_an_agent_without_sms_company_is_refused(self):
        with self.assertRaises(BusinessPermissionDenied):
            send_outbound_sms(actor=self.agent, body="سلام", phone="09121110000")
        self.assertEqual(OutboundSMS.objects.count(), 0)

    def test_an_empty_body_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            send_outbound_sms(actor=self.manager, body="   ", phone="09121110000")

    def test_a_too_long_body_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            send_outbound_sms(actor=self.manager, body="a" * 700, phone="09121110000")

    def test_no_recipient_at_all_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            send_outbound_sms(actor=self.manager, body="سلام")

    def test_an_invalid_phone_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            send_outbound_sms(actor=self.manager, body="سلام", phone="not-a-phone")

    def test_a_customer_with_no_active_phone_is_refused(self):
        bare = create_customer_with_phone(actor=self.manager, full_name="بدون شماره فعال", phone={"raw_phone": "09121110099"})
        bare.phones.update(is_active=False)
        with self.assertRaises(BusinessRuleError):
            send_outbound_sms(actor=self.manager, body="سلام", customer=bare)

    def test_a_lead_belonging_to_a_different_customer_is_refused(self):
        other = create_customer_with_phone(actor=self.manager, full_name="مشتری دیگر", phone={"raw_phone": "09121110088"})
        lead = create_lead(actor=self.manager, customer=self.customer, source="تماس")
        with self.assertRaises(BusinessRuleError):
            send_outbound_sms(actor=self.manager, body="سلام", customer=other, lead=lead)

    def test_no_provider_configured_is_refused_and_writes_nothing(self):
        with self.assertRaises(BusinessRuleError):
            send_outbound_sms(actor=self.manager, body="سلام", customer=self.customer)
        self.assertEqual(OutboundSMS.objects.count(), 0)


class SendOutboundSmsAttemptTests(EchoServerCase, TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="sms.attempt.manager", password="Strong-pass-983!", role=User.Role.SALES_MANAGER)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری موفق", phone={"raw_phone": "09121110000", "is_primary": True},
        )
        self.lead = create_lead(actor=self.manager, customer=self.customer, source="تماس")

    def test_a_successful_send_to_a_customer_records_sent_and_logs_it(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            message = send_outbound_sms(actor=self.manager, body="یادآوری قرار", customer=self.customer, lead=self.lead)
        self.assertEqual(message.status, OutboundSMS.Status.SENT)
        self.assertEqual(message.recipient_normalized, "+989121110000")
        self.assertEqual(message.customer, self.customer)
        self.assertEqual(message.lead, self.lead)
        self.assertEqual(message.sent_by, self.manager)
        self.assertTrue(ActivityLog.objects.filter(operation="outbound_sms.sent", object_id=str(message.pk)).exists())

    def test_a_provider_rejection_records_failed_not_an_exception_and_logs_it(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            message = send_outbound_sms(actor=self.manager, body="FAIL_ME on purpose", customer=self.customer)
        self.assertEqual(message.status, OutboundSMS.Status.FAILED)
        self.assertIn("HTTP 400", message.status_detail)
        self.assertTrue(ActivityLog.objects.filter(operation="outbound_sms.failed", object_id=str(message.pk)).exists())

    def test_a_lead_alone_resolves_its_own_customer(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            message = send_outbound_sms(actor=self.manager, body="یادآوری", lead=self.lead)
        self.assertEqual(message.customer, self.customer)
        self.assertEqual(message.recipient_normalized, "+989121110000")

    def test_a_raw_phone_needs_no_customer_or_lead(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            message = send_outbound_sms(actor=self.manager, body="سلام", phone="09359998877")
        self.assertIsNone(message.customer)
        self.assertIsNone(message.lead)
        self.assertEqual(message.recipient_normalized, "+989359998877")


class OutboundSMSAPITests(EchoServerCase, TestCase):
    password = "Strong-pass-983!"

    def setUp(self):
        self.manager = User.objects.create_user(username="sms.api.out.manager", password=self.password, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="sms.api.out.agent", password=self.password, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری API پیامک", phone={"raw_phone": "09121110000", "is_primary": True},
        )

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_manager_can_send_and_see_it_in_the_log(self):
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            response = self.client_for(self.manager).post(
                "/api/v1/outbound-sms/send/", {"customer": self.customer.pk, "body": "سلام از API"}, format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "sent")
        self.assertEqual(response.data["customer"], self.customer.pk)

        log = self.client_for(self.manager).get("/api/v1/outbound-sms/")
        self.assertEqual(log.status_code, 200)
        self.assertEqual(log.data["count"], 1)
        self.assertEqual(log.data["results"][0]["body_text"], "سلام از API")

    def test_an_agent_is_refused_send_and_the_log(self):
        client = self.client_for(self.agent)
        with override_settings(SMS_PROVIDER="http", SMS_API_URL=self.url, SMS_API_BODY_TEMPLATE=BODY_TEMPLATE):
            send = client.post("/api/v1/outbound-sms/send/", {"phone": "09121110000", "body": "سلام"}, format="json")
        self.assertEqual(send.status_code, 403)
        self.assertEqual(client.get("/api/v1/outbound-sms/").status_code, 200)
        self.assertEqual(client.get("/api/v1/outbound-sms/").data["count"], 0)

    def test_naming_both_customer_and_phone_is_rejected_by_the_serializer(self):
        response = self.client_for(self.manager).post(
            "/api/v1/outbound-sms/send/",
            {"customer": self.customer.pk, "phone": "09121110000", "body": "سلام"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_naming_nobody_is_rejected_by_the_serializer(self):
        response = self.client_for(self.manager).post(
            "/api/v1/outbound-sms/send/", {"body": "سلام"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_customer_outside_scope_is_refused_as_a_validation_error(self):
        response = self.client_for(self.manager).post(
            "/api/v1/outbound-sms/send/", {"customer": 999999, "body": "سلام"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_no_provider_configured_surfaces_as_a_field_error(self):
        with override_settings(SMS_PROVIDER=""):
            response = self.client_for(self.manager).post(
                "/api/v1/outbound-sms/send/", {"phone": "09121110000", "body": "سلام"}, format="json",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("provider", response.data)
