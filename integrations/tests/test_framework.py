"""The integrations framework (2.21.0).

What must hold:

* **no plaintext secret** — not in the database row, not in an API response,
  not in a log; a blank secret on edit keeps the stored one;
* **inbound webhooks** are authenticated by signature, idempotent, logged, and
  land on the matched person's timeline;
* **the outbox** handles an event after commit, retries a failure with
  backoff, and never emits the same fact twice;
* **outbound webhooks** are signed, retried and finally failed, and refuse
  non-public targets;
* **API tokens** carry exactly their user's rights, narrowed by scope, and are
  shown once;
* **contact matching** finds a caller however the PBX spells the number.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from billing.models import Payment
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from integrations import crypto, events, webhooks
from integrations.matching import best_match, match_phone
from integrations.models import (
    ApiToken,
    DomainEvent,
    InboundWebhookReceipt,
    Integration,
    IntegrationLog,
    WebhookDelivery,
    WebhookSubscription,
)
from integrations.services import create_integration, create_subscription
from sales.models import CustomerPhone, Interaction
from sales.services import create_customer_with_phone, create_lead, record_interaction
from timeline.models import TimelineEntry

PASSWORD = "Strong-pass-448!"


def without(*features):
    return DeploymentProfile(profile_id="client-1", features=frozenset(ALL_FEATURES) - frozenset(features), source="signed-manifest")


class Fixtures(TestCase):
    # Throttle counters live in the cache and are keyed by user id, which
    # test databases reuse; clearing keeps this module from being throttled
    # by — or throttling — the rest of the suite.
    def tearDown(self):
        cache.clear()
        super().tearDown()

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(username="ig.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="ig.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="ig.agent", password=PASSWORD, role=User.Role.SALES_AGENT, phone="09127776655")
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری یکپارچه", phone={"raw_phone": "09151234567", "is_primary": True}
        )

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def generic(self, secret="s3cret-signing", enabled=True):
        return create_integration(
            actor=self.admin, provider_key="generic_webhook", name="ربات تلگرام",
            config={"channel_label": "تلگرام"}, secrets={"signing_secret": secret}, enabled=enabled,
        )

    def post_webhook(self, integration, payload, secret="s3cret-signing", **headers):
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with self.captureOnCommitCallbacks(execute=True):
            return self.api().post(
                f"/api/v1/integrations/{integration.pk}/webhook/", data=body, content_type="application/json",
                HTTP_X_DOLPHIN_SIGNATURE=f"sha256={signature}", **headers,
            )


class CryptoTests(TestCase):
    def test_a_round_trip_and_rotation(self):
        old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
        with override_settings(DOLPHIN_SECRETS_KEY=old):
            token = crypto.encrypt_json({"password": "هیچ‌کس"})
        self.assertNotIn("هیچ‌کس", token)
        with override_settings(DOLPHIN_SECRETS_KEY=f"{new},{old}"):
            self.assertEqual(crypto.decrypt_json(token), {"password": "هیچ‌کس"})
        with override_settings(DOLPHIN_SECRETS_KEY=new), self.assertRaises(crypto.SecretsUnavailable):
            crypto.decrypt_json(token)

    def test_without_a_key_nothing_is_stored(self):
        with override_settings(DOLPHIN_SECRETS_KEY=""):
            self.assertFalse(crypto.secrets_available())
            with self.assertRaises(crypto.SecretsUnavailable):
                crypto.encrypt_json({"a": "b"})


class IntegrationApiTests(Fixtures):
    def test_secrets_are_encrypted_masked_and_never_returned(self):
        response = self.api(self.admin).post("/api/v1/integrations/", {
            "provider_key": "generic_webhook", "name": "فرم سایت", "enabled": True,
            "config": {"channel_label": "وب‌سایت"}, "secrets": {"signing_secret": "a-very-long-secret-value"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        body = json.dumps(response.data, ensure_ascii=False)
        self.assertNotIn("a-very-long-secret-value", body)
        self.assertEqual(response.data["secret_hints"]["signing_secret"][-4:], "alue")
        row = Integration.objects.get(pk=response.data["id"])
        self.assertNotIn("a-very-long-secret-value", row.secrets_token)
        self.assertEqual(crypto.decrypt_json(row.secrets_token)["signing_secret"], "a-very-long-secret-value")
        self.assertTrue(ActivityLog.objects.filter(operation="integration.created").exists())
        self.assertFalse(any("a-very-long" in json.dumps(log.safe_changes) for log in ActivityLog.objects.all()))

    def test_a_blank_secret_keeps_the_stored_one(self):
        integration = self.generic()
        self.api(self.admin).patch(f"/api/v1/integrations/{integration.pk}/", {"secrets": {"signing_secret": ""}, "name": "نام تازه"}, format="json")
        integration.refresh_from_db()
        self.assertEqual(crypto.decrypt_json(integration.secrets_token)["signing_secret"], "s3cret-signing")
        self.assertEqual(integration.name, "نام تازه")

    def test_the_schema_is_enforced(self):
        response = self.api(self.admin).post("/api/v1/integrations/", {
            "provider_key": "generic_webhook", "name": "بی‌کلید", "config": {"nope": 1},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("signing_secret", response.data)
        self.assertIn("nope", response.data)

    def test_only_the_platform_admin_and_only_with_the_feature(self):
        self.assertEqual(self.api(self.manager).get("/api/v1/integrations/").status_code, 403)
        with override_active_profile(without("integrations", "outbound_webhooks", "public_api")):
            self.assertEqual(self.api(self.admin).get("/api/v1/integrations/").status_code, 404)

    def test_a_connection_test_records_health(self):
        integration = self.generic()
        result = self.api(self.admin).post(f"/api/v1/integrations/{integration.pk}/test/").data
        self.assertTrue(result["ok"])
        integration.refresh_from_db()
        self.assertEqual(integration.status, Integration.Status.OK)
        self.assertIsNotNone(integration.last_health_at)

    def test_the_page_shows_the_framework_to_the_platform_admin_only(self):
        # The connections card itself is shared with the built-in services
        # (2.24.0); the framework's rows, tabs and catalog are not.
        self.client.force_login(self.admin)
        response = self.client.get("/settings/integrations/")
        for marker in ('id="integrations-table-body"', 'data-profile-tab="logs"', 'id="integration-catalog-dialog"'):
            self.assertContains(response, marker)
        self.assertContains(response, "یکپارچه‌سازی‌ها")
        self.client.force_login(self.manager)
        response = self.client.get("/settings/integrations/")
        for marker in ('id="integrations-table-body"', 'data-profile-tab="logs"', 'id="integration-catalog-dialog"'):
            self.assertNotContains(response, marker)


class InboundWebhookTests(Fixtures):
    def test_a_signed_message_is_matched_recorded_and_idempotent(self):
        integration = self.generic()
        payload = {"id": "tg-1", "type": "message.received", "from": "+989151234567", "text": "سلام، قیمت؟"}
        response = self.post_webhook(integration, payload)
        self.assertEqual(response.status_code, 202, response.data)
        entry = TimelineEntry.objects.get(person_type="customer", person_id=self.customer.pk, kind="message")
        self.assertIn("تلگرام", entry.title)
        self.assertEqual(entry.body, "سلام، قیمت؟")
        self.assertEqual(self.post_webhook(integration, payload).status_code, 200)
        self.assertEqual(InboundWebhookReceipt.objects.count(), 1)
        self.assertEqual(DomainEvent.objects.filter(event_type="message.received").count(), 1)

    def test_the_log_offers_to_create_a_customer_for_an_unknown_sender(self):
        """Only for a number no one has, and only while that stays true."""
        integration = self.generic()
        self.post_webhook(integration, {"id": "m-1", "type": "message.received", "from": "09350001122", "text": "سلام"})
        self.post_webhook(integration, {"id": "m-2", "type": "message.received", "from": "+989151234567", "text": "سلام"})
        rows = self.api(self.admin).get("/api/v1/integration-logs/").data["results"]
        by_id = {row["message"]: row["create_customer_url"] for row in rows}
        unknown = next(url for message, url in by_id.items() if "بدون تطبیق" in message)
        self.assertEqual(unknown, "/customers/?new_phone=%2B989350001122")
        known = next(url for message, url in by_id.items() if "تطبیق با" in message)
        self.assertEqual(known, "")
        CustomerPhone.objects.create(customer=self.customer, raw_phone="09350001122", normalized_phone="+989350001122")
        rows = self.api(self.admin).get("/api/v1/integration-logs/").data["results"]
        self.assertTrue(all(row["create_customer_url"] == "" for row in rows))

    def test_a_bad_signature_is_refused_and_logged(self):
        integration = self.generic()
        response = self.post_webhook(integration, {"id": "x", "type": "message.received"}, secret="wrong")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(IntegrationLog.objects.filter(integration=integration, status="error").exists())

    def test_a_disabled_connection_does_not_exist_to_the_caller(self):
        integration = self.generic(enabled=False)
        self.assertEqual(self.post_webhook(integration, {"id": "x", "type": "message.received"}).status_code, 404)

    def test_the_log_never_holds_a_secret(self):
        integration = self.generic()
        self.post_webhook(integration, {"id": "tg-9", "type": "message.received", "from": "0915", "token": "leak-me"})
        for row in IntegrationLog.objects.all():
            self.assertNotIn("leak-me", json.dumps(row.payload, ensure_ascii=False))


class OutboxTests(Fixtures):
    def test_a_failing_handler_leaves_the_event_pending_with_a_retry_time(self):
        with mock.patch.dict(events._HANDLERS, {"payment.received": [mock.Mock(side_effect=RuntimeError("boom"))]}):
            event = events.emit("payment.received", {"x": 1})
            events.process(event.pk)
        event.refresh_from_db()
        self.assertEqual(event.status, DomainEvent.Status.PENDING)
        self.assertEqual(event.attempts, 1)
        self.assertIn("boom", event.last_error)
        self.assertGreater(event.available_at, timezone.now())
        self.assertEqual(events.process_pending(), 0)  # not due yet
        self.assertEqual(events.process_pending(now=event.available_at + timedelta(seconds=1)), 1)
        event.refresh_from_db()
        self.assertEqual(event.status, DomainEvent.Status.PROCESSED)

    def test_the_same_fact_is_emitted_once(self):
        self.assertIsNotNone(events.emit("payment.received", {}, dedupe_key="payment:1:received"))
        self.assertIsNone(events.emit("payment.received", {}, dedupe_key="payment:1:received"))

    def test_nothing_is_emitted_without_the_feature(self):
        with override_active_profile(without("integrations", "outbound_webhooks", "public_api")):
            self.assertIsNone(events.emit("payment.received", {}))

    def test_a_confirmed_receipt_emits_payment_received(self):
        from billing.payments import register_payment

        with self.captureOnCommitCallbacks(execute=True):
            register_payment(actor=self.manager, customer=self.customer, method=Payment.Method.CASH, amount=Decimal("50000.00"))
        event = DomainEvent.objects.get(event_type="payment.received")
        self.assertEqual(event.person_id, self.customer.pk)
        self.assertEqual(event.status, DomainEvent.Status.PROCESSED)


class OutboundWebhookTests(Fixtures):
    def subscribe(self, event_types=()):
        with override_settings(DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS=True):
            subscription, secret = create_subscription(
                actor=self.admin, name="سامانهٔ حسابداری", url="https://hooks.example.test/in", event_types=list(event_types)
            )
        return subscription, secret

    def test_an_event_is_queued_signed_and_delivered(self):
        subscription, secret = self.subscribe(["payment.received"])
        with self.captureOnCommitCallbacks(execute=True):
            events.emit("payment.received", {"amount": "10"})
            events.emit("message.sent", {})
        self.assertEqual(WebhookDelivery.objects.count(), 1)
        sent = {}

        def fake_post(url, body, headers):
            sent.update(url=url, body=body, headers=headers)
            return 200, "ok"

        with mock.patch.object(webhooks, "_post", fake_post), override_settings(DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS=True):
            self.assertEqual(webhooks.deliver_due(), 1)
        delivery = WebhookDelivery.objects.get()
        self.assertEqual(delivery.status, WebhookDelivery.Status.DELIVERED)
        timestamp, signature = [part.split("=", 1)[1] for part in sent["headers"]["X-Dolphin-Signature"].split(",")]
        self.assertEqual(signature, webhooks.sign(secret, timestamp, sent["body"]))
        self.assertEqual(json.loads(sent["body"])["type"], "payment.received")

    def test_a_failing_subscriber_is_retried_then_failed(self):
        self.subscribe()
        with self.captureOnCommitCallbacks(execute=True):
            events.emit("payment.received", {})
        now = timezone.now()
        with mock.patch.object(webhooks, "_post", return_value=(500, "down")), override_settings(DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS=True):
            for _ in range(webhooks.MAX_ATTEMPTS):
                webhooks.deliver_due(now=now)
                now += timedelta(days=1)
        delivery = WebhookDelivery.objects.get()
        self.assertEqual(delivery.status, WebhookDelivery.Status.FAILED)
        self.assertEqual(delivery.attempts, webhooks.MAX_ATTEMPTS)
        self.assertIn("500", delivery.last_error)

    def test_only_public_https_targets_are_accepted(self):
        for url in ("http://example.com/hook", "https://127.0.0.1/hook", "https://10.0.0.5/hook", "https://user:pw@example.com/"):
            with self.subTest(url=url), override_settings(DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS=False):
                self.assertEqual(
                    self.api(self.admin).post("/api/v1/webhook-subscriptions/", {"name": "x", "url": url}, format="json").status_code,
                    400,
                )

    def test_the_signing_secret_is_shown_once(self):
        with override_settings(DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS=True):
            created = self.api(self.admin).post(
                "/api/v1/webhook-subscriptions/", {"name": "x", "url": "https://hooks.example.test/"}, format="json"
            ).data
        self.assertIn("secret", created)
        listed = self.api(self.admin).get("/api/v1/webhook-subscriptions/").data
        self.assertNotIn("secret", listed[0])
        self.assertNotIn(created["secret"], WebhookSubscription.objects.get().secret_token)


class ApiTokenTests(Fixtures):
    def make(self, user, scopes):
        response = self.api(self.admin).post("/api/v1/api-tokens/", {"name": "ربات", "user": user.pk, "scopes": scopes}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["token"]

    def test_a_token_carries_its_users_rights_only(self):
        plain = self.make(self.agent, ["read"])
        stored = ApiToken.objects.get()
        self.assertEqual(stored.token_hash, hashlib.sha256(plain.encode()).hexdigest())
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {plain}")
        self.assertEqual(client.get("/api/v1/customers/").status_code, 200)
        self.assertEqual(client.get("/api/v1/customers/").data["count"], 0)  # the agent's own book
        self.assertEqual(client.get("/api/v1/users/").status_code, 403)
        self.assertEqual(client.post("/api/v1/customers/", {"full_name": "x"}, format="json").status_code, 403)

    def test_revoked_and_unknown_tokens_are_refused(self):
        plain = self.make(self.manager, ["read", "write"])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {plain}")
        self.assertEqual(client.get("/api/v1/customers/").status_code, 200)
        self.api(self.admin).post(f"/api/v1/api-tokens/{ApiToken.objects.get().pk}/revoke/")
        self.assertIn(client.get("/api/v1/customers/").status_code, (401, 403))
        client.credentials(HTTP_AUTHORIZATION="Bearer dol_not-a-real-token")
        self.assertIn(client.get("/api/v1/customers/").status_code, (401, 403))

    def test_a_platform_admin_token_is_refused(self):
        response = self.api(self.admin).post("/api/v1/api-tokens/", {"name": "x", "user": self.admin.pk, "scopes": ["read"]}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_without_public_api_a_token_authenticates_nobody(self):
        plain = self.make(self.manager, ["read"])
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {plain}")
        with override_active_profile(without("public_api")):
            self.assertEqual(client.get("/api/v1/customers/").status_code, 403)


class MatchingTests(Fixtures):
    def test_every_spelling_of_a_number_finds_the_customer(self):
        for raw in ("09151234567", "+989151234567", "00989151234567", "9151234567", "۰۹۱۵۱۲۳۴۵۶۷", "909151234567"):
            with self.subTest(raw=raw):
                match = best_match(raw)
                self.assertIsNotNone(match)
                self.assertEqual((match.person_type, match.person_id), ("customer", self.customer.pk))

    def test_a_colleague_and_an_unknown_number(self):
        self.assertEqual(best_match("09127776655").person_type, "user")
        self.assertEqual(match_phone("09129999999"), [])
        self.assertEqual(match_phone("داخلی ۲۰۴"), [])

    def test_a_called_number_points_back_to_its_customer(self):
        lead = create_lead(actor=self.manager, customer=self.customer, source="کمپین")
        record_interaction(
            actor=self.manager, lead=lead, phone="09133330000", direction="outbound",
            outcome="پاسخ داد", occurred_at=timezone.now(),
        )
        self.assertEqual(Interaction.objects.get().normalized_phone, "+989133330000")
        match = best_match("09133330000")
        self.assertEqual((match.person_id, match.how), (self.customer.pk, "history"))


class WorkerTests(Fixtures):
    def test_one_pass_handles_what_is_pending(self):
        DomainEvent.objects.create(event_type="payment.received", payload={}, available_at=timezone.now())
        call_command("run_integrations_worker", "--once", stdout=StringIO())
        self.assertFalse(DomainEvent.objects.filter(status=DomainEvent.Status.PENDING).exists())

    def test_the_key_generator_prints_a_usable_key(self):
        out = StringIO()
        call_command("generate_secrets_key", stdout=out)
        Fernet(out.getvalue().strip().encode())
