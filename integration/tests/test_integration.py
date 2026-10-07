"""PRELIMINARY, UNCOMMITTED — see integration/apps.py.

Covers the CRM-side half of the cross-product integration goal: the
`enqueue_event`/pairing-settings service layer, the hand-off token
round-trip, the two API views, and — using a real
`ThreadingHTTPServer`, the same technique `communications/tests/
test_outbound_sms.py` already uses for its own HTTP provider — the outbox
dispatcher management command actually posting a real, correctly-signed
request.

Also exercises one real call site (`register_payment`) end to end rather
than only the `enqueue_event` helper in isolation, so a wiring mistake at
the call site itself (wrong kwarg, wrong side of the transaction) would
be caught here — the same reasoning `test_end_to_end.py` gives for testing
the whole commercial chain together.
"""

import hashlib
import hmac
import json
import threading
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO

from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from billing.models import Payment
from billing.payments import register_payment
from common.deployment.profile import DeploymentProfile, override_active_profile
from integration.models import OutboundEvent, PairingSettings
from integration.services import enqueue_event, get_pairing_settings, update_pairing_settings
from integration.tokens import TokenError, mint_handoff_token, verify_handoff_token
from sales.services import create_customer_with_phone

PASSWORD = "Strong-pass-604!"


def paired_profile(accounting_base_url="https://accounting.example.test", **extra):
    from common.deployment.registry import ALL_FEATURES

    return DeploymentProfile(
        profile_id="client-1", features=ALL_FEATURES, source="signed-manifest",
        accounting_base_url=accounting_base_url, **extra,
    )


class EnqueueEventTests(TestCase):
    def test_a_disabled_pairing_enqueues_nothing(self):
        self.assertIsNone(enqueue_event(event_type="invoice.issued", payload={}))
        self.assertEqual(OutboundEvent.objects.count(), 0)

    def test_an_enabled_pairing_with_no_secret_still_enqueues_nothing(self):
        admin = User.objects.create_user(username="admin1", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        update_pairing_settings(actor=admin, is_enabled=False, shared_secret="")
        row = get_pairing_settings()
        row.is_enabled = True  # bypass update_pairing_settings' own guard, to prove enqueue_event checks too
        row.save()
        self.assertIsNone(enqueue_event(event_type="invoice.issued", payload={}))

    def test_a_fully_configured_pairing_enqueues_a_real_row_with_a_unique_idempotency_key(self):
        admin = User.objects.create_user(username="admin2", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        update_pairing_settings(actor=admin, is_enabled=True, shared_secret="s3cret")
        first = enqueue_event(event_type="invoice.issued", payload={"number": "INV-1"})
        second = enqueue_event(event_type="invoice.issued", payload={"number": "INV-2"})
        self.assertIsNotNone(first)
        self.assertNotEqual(first.idempotency_key, second.idempotency_key)
        self.assertEqual(OutboundEvent.objects.count(), 2)
        self.assertIsNone(first.dispatched_at)

    def test_update_pairing_settings_refuses_enabling_without_a_secret(self):
        admin = User.objects.create_user(username="admin3", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        with self.assertRaises(Exception):
            update_pairing_settings(actor=admin, is_enabled=True, shared_secret="")


class RealCallSiteTests(TestCase):
    """One real business-service call, not just enqueue_event in isolation."""

    def test_registering_a_receipt_enqueues_payment_received(self):
        mgr = User.objects.create_user(username="mgr1", password=PASSWORD, role=User.Role.SALES_MANAGER)
        cust = create_customer_with_phone(
            actor=mgr, full_name="آزمون یکپارچگی",
            phone={"raw_phone": "09121234599", "is_primary": True},
        )
        update_pairing_settings(actor=mgr, is_enabled=True, shared_secret="s3cret")
        register_payment(actor=mgr, customer=cust, method=Payment.Method.CASH, amount=Decimal("500.00"))
        event = OutboundEvent.objects.get(event_type="payment.received")
        self.assertEqual(event.payload["amount"], "500.00")

    def test_a_disbursement_enqueues_nothing_only_a_receipt_does(self):
        mgr = User.objects.create_user(username="mgr2", password=PASSWORD, role=User.Role.SALES_MANAGER)
        update_pairing_settings(actor=mgr, is_enabled=True, shared_secret="s3cret")
        register_payment(actor=mgr, method=Payment.Method.CASH, amount=Decimal("50.00"), direction=Payment.Direction.DISBURSEMENT, payee="فروشنده")
        self.assertEqual(OutboundEvent.objects.count(), 0)


class HandoffTokenTests(SimpleTestCase):
    def test_a_valid_token_round_trips(self):
        token = mint_handoff_token(
            secret="shhh", issuer="dolphin-crm", audience="dolphin-accounting",
            claims={"username": "u1"}, ttl_seconds=60,
        )
        claims = verify_handoff_token(secret="shhh", token=token, expected_audience="dolphin-accounting")
        self.assertEqual(claims["username"], "u1")

    def test_a_tampered_token_is_refused(self):
        token = mint_handoff_token(secret="shhh", issuer="a", audience="b", claims={"username": "u1"}, ttl_seconds=60)
        body, _, sig = token.partition(".")
        tampered = f"{body}x.{sig}"
        with self.assertRaises(TokenError):
            verify_handoff_token(secret="shhh", token=tampered, expected_audience="b")

    def test_the_wrong_secret_is_refused(self):
        token = mint_handoff_token(secret="shhh", issuer="a", audience="b", claims={}, ttl_seconds=60)
        with self.assertRaises(TokenError):
            verify_handoff_token(secret="different", token=token, expected_audience="b")

    def test_the_wrong_audience_is_refused(self):
        token = mint_handoff_token(secret="shhh", issuer="a", audience="dolphin-accounting", claims={}, ttl_seconds=60)
        with self.assertRaises(TokenError):
            verify_handoff_token(secret="shhh", token=token, expected_audience="someone-else")

    def test_an_expired_token_is_refused(self):
        token = mint_handoff_token(secret="shhh", issuer="a", audience="b", claims={}, ttl_seconds=0)
        time.sleep(1.1)
        with self.assertRaises(TokenError):
            verify_handoff_token(secret="shhh", token=token, expected_audience="b")


class PairingSettingsViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="pa1", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="mg1", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.client = APIClient()

    def test_absent_without_an_accounting_entitlement(self):
        self.client.login(username="pa1", password=PASSWORD)
        with override_active_profile(paired_profile(accounting_base_url="")):
            self.assertEqual(self.client.get("/api/v1/integration/pairing/").status_code, 404)

    def test_forbidden_for_a_non_platform_admin_even_with_entitlement(self):
        self.client.login(username="mg1", password=PASSWORD)
        with override_active_profile(paired_profile()):
            self.assertEqual(self.client.get("/api/v1/integration/pairing/").status_code, 403)

    def test_a_platform_admin_can_read_and_write_it(self):
        self.client.login(username="pa1", password=PASSWORD)
        with override_active_profile(paired_profile()):
            response = self.client.post(
                "/api/v1/integration/pairing/",
                {"is_enabled": True, "shared_secret": "topsecret"},
                format="json",
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["has_shared_secret"])
            self.assertNotIn("shared_secret", response.data)  # never echoed back
            row = get_pairing_settings()
            self.assertEqual(row.shared_secret, "topsecret")


class HandoffMintAndAcceptTests(TestCase):
    def setUp(self):
        self.agent = User.objects.create_user(username="ag1", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.admin = User.objects.create_user(username="pa2", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        update_pairing_settings(actor=self.admin, is_enabled=True, shared_secret="topsecret")
        self.client = APIClient()

    def test_mint_is_404_without_entitlement(self):
        self.client.login(username="ag1", password=PASSWORD)
        with override_active_profile(paired_profile(accounting_base_url="")):
            self.assertEqual(self.client.post("/api/v1/integration/handoff/mint/").status_code, 404)

    def test_mint_returns_a_url_carrying_a_verifiable_token(self):
        self.client.login(username="ag1", password=PASSWORD)
        with override_active_profile(paired_profile()):
            response = self.client.post("/api/v1/integration/handoff/mint/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["url"].startswith("https://accounting.example.test/integration/handoff/?token="))
        token = response.data["url"].split("token=", 1)[1]
        claims = verify_handoff_token(secret="topsecret", token=token, expected_audience="dolphin-accounting")
        self.assertEqual(claims["username"], "ag1")

    def test_accept_view_is_the_mirror_side_of_the_same_flow(self):
        """A token minted *by* Accounting (audience dolphin-crm) is what
        HandoffAcceptView on this side must accept — proven directly against
        the mint/verify functions rather than a live Accounting deployment."""
        token = mint_handoff_token(
            secret="topsecret", issuer="dolphin-accounting", audience="dolphin-crm",
            claims={"username": "external.user", "email": "e@example.test"}, ttl_seconds=60,
        )
        plain_client = Client()
        with override_active_profile(paired_profile()):
            response = plain_client.get(f"/integration/handoff/?token={token}")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="accounting:external.user").exists())

    def test_accept_view_refuses_a_bad_token(self):
        plain_client = Client()
        with override_active_profile(paired_profile()):
            response = plain_client.get("/integration/handoff/?token=garbage")
        self.assertEqual(response.status_code, 404)

    def test_accept_view_is_absent_without_entitlement(self):
        plain_client = Client()
        with override_active_profile(paired_profile(accounting_base_url="")):
            response = plain_client.get("/integration/handoff/?token=garbage")
        self.assertEqual(response.status_code, 404)


class _WebhookEchoHandler(BaseHTTPRequestHandler):
    """Records exactly what the dispatcher sent, and always answers 200 —
    proving the request itself is well-formed is this test's job, not
    proving Accounting's own receiver logic (covered in that repo)."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.last_request = {
            "headers": dict(self.headers.items()),
            "body": json.loads(raw.decode("utf-8")),
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, *args):
        pass


class DispatchOutboundEventsCommandTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _WebhookEchoHandler)
        cls.server.last_request = None
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
        self.admin = User.objects.create_user(username="pa3", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        update_pairing_settings(actor=self.admin, is_enabled=True, shared_secret="s3cret")

    def test_a_pending_event_is_delivered_with_a_correct_signature_and_marked_dispatched(self):
        event = OutboundEvent.objects.create(
            idempotency_key="k-1", event_type="invoice.issued",
            payload={"number": "INV-1"}, occurred_at=timezone.now(),
        )
        with override_active_profile(paired_profile(accounting_base_url=f"http://127.0.0.1:{self.port}")):
            call_command("dispatch_outbound_events", stdout=StringIO())
        event.refresh_from_db()
        self.assertIsNotNone(event.dispatched_at)

        sent = self.server.last_request
        self.assertEqual(sent["body"]["idempotency_key"], "k-1")
        # The dispatcher signs the exact bytes it transmits — `json.dumps`
        # with its default separators (see integration/management/commands/
        # dispatch_outbound_events.py's `_dispatch_one`), over the same four
        # keys in the same order it always writes them in.
        expected_body = json.dumps({
            "idempotency_key": event.idempotency_key,
            "event_type": event.event_type,
            "payload": event.payload,
            "occurred_at": event.occurred_at.isoformat(),
        }).encode("utf-8")
        expected_signature = hmac.new(b"s3cret", expected_body, hashlib.sha256).hexdigest()
        self.assertEqual(sent["headers"].get("X-Dolphin-Signature"), expected_signature)

    def test_an_undispatchable_event_records_the_error_and_increments_attempts(self):
        event = OutboundEvent.objects.create(
            idempotency_key="k-2", event_type="invoice.issued",
            payload={}, occurred_at=timezone.now(),
        )
        with override_active_profile(paired_profile(accounting_base_url="http://127.0.0.1:1")):
            call_command("dispatch_outbound_events", stdout=StringIO(), stderr=StringIO())
        event.refresh_from_db()
        self.assertIsNone(event.dispatched_at)
        self.assertEqual(event.attempts, 1)
        self.assertIn("خطای اتصال", event.last_error)

    def test_no_pairing_configured_is_a_silent_no_op(self):
        PairingSettings.objects.all().delete()
        event = OutboundEvent.objects.create(
            idempotency_key="k-3", event_type="invoice.issued",
            payload={}, occurred_at=timezone.now(),
        )
        with override_active_profile(paired_profile()):
            call_command("dispatch_outbound_events", stdout=StringIO())
        event.refresh_from_db()
        self.assertIsNone(event.dispatched_at)
