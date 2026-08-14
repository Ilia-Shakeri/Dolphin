from datetime import UTC, datetime
from threading import Barrier, Lock, Thread
from unittest import skipUnless

from django.core.exceptions import FieldDoesNotExist
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.urls import Resolver404, resolve
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common.exceptions import BusinessRuleError
from communications.models import InboundSMS
from communications.services import (
    IdempotencyConflict,
    NormalizedInboundSMSEvent,
    store_normalized_inbound_sms,
)
from sales.services import create_customer_with_phone, create_lead


def sms_event(**overrides):
    values = {
        "provider_code": "future_provider",
        "external_message_id": "external-1",
        "sender_normalized": "+989121110000",
        "recipient_normalized": "+989999990000",
        "provider_received_at": datetime(2026, 8, 13, 20, 45, tzinfo=UTC),
        "metadata": {"route": "primary", "attempt": 1},
    }
    values.update(overrides)
    return NormalizedInboundSMSEvent(**values)


class InboundSMSServiceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="sms.manager",
            password="Strong-pass-983!",
            role=User.Role.SALES_MANAGER,
        )

    def test_storage_links_only_deterministic_customer_and_lead_without_body(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری پیامک",
            phone={"raw_phone": "09121110000", "is_primary": True},
        )
        lead = create_lead(actor=self.manager, customer=customer, source="پیامک")

        stored = store_normalized_inbound_sms(event=sms_event(), actor=self.manager)

        self.assertTrue(stored.created)
        self.assertEqual(stored.message.customer, customer)
        self.assertEqual(stored.message.lead, lead)
        self.assertEqual(stored.message.processing_state, InboundSMS.ProcessingState.LINKED)
        self.assertEqual(stored.message.body_retention_policy, InboundSMS.BodyRetentionPolicy.NOT_RETAINED)
        with self.assertRaises(FieldDoesNotExist):
            InboundSMS._meta.get_field("body")
        audit = ActivityLog.objects.get(operation="inbound_sms.stored")
        self.assertEqual(audit.object_id, str(stored.message.pk))
        self.assertEqual(set(audit.safe_changes), {"fields"})
        self.assertNotIn("external-1", str(audit.safe_changes))
        self.assertNotIn("+989121110000", str(audit.safe_changes))

    def test_multiple_leads_keep_customer_but_do_not_guess_lead(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری چند سرنخ",
            phone={"raw_phone": "09121110000"},
        )
        create_lead(actor=self.manager, customer=customer, source="اول")
        create_lead(actor=self.manager, customer=customer, source="دوم")

        message = store_normalized_inbound_sms(event=sms_event()).message

        self.assertEqual(message.customer, customer)
        self.assertIsNone(message.lead)

    def test_replay_is_idempotent_and_identifier_collision_fails_closed(self):
        first = store_normalized_inbound_sms(event=sms_event())
        replay = store_normalized_inbound_sms(event=sms_event())
        self.assertTrue(first.created)
        self.assertFalse(replay.created)
        self.assertEqual(first.message.pk, replay.message.pk)
        self.assertEqual(InboundSMS.objects.count(), 1)

        with self.assertRaises(IdempotencyConflict):
            store_normalized_inbound_sms(event=sms_event(sender_normalized="+989121110001"))
        self.assertEqual(InboundSMS.objects.count(), 1)

    def test_metadata_is_bounded_and_restricted(self):
        bad_values = [
            {"message_body": "متن"},
            {"signature": "proof"},
            {"nested": {"bad": True}},
            {f"field_{index}": index for index in range(21)},
            {"note": "x" * 257},
        ]
        for metadata in bad_values:
            with self.subTest(metadata=list(metadata)):
                with self.assertRaises(BusinessRuleError):
                    store_normalized_inbound_sms(event=sms_event(metadata=metadata))
        self.assertFalse(InboundSMS.objects.exists())

    def test_only_normalized_inbound_events_are_accepted(self):
        invalid = [
            {"sender_normalized": "09121110000"},
            {"recipient_normalized": "service-line"},
            {"direction": "outbound"},
            {"provider_received_at": datetime(2026, 8, 14, 0, 15)},
        ]
        for change in invalid:
            with self.subTest(change=change):
                with self.assertRaises(BusinessRuleError):
                    store_normalized_inbound_sms(event=sms_event(**change))


class InboundSMSReportAPITests(TestCase):
    password = "Strong-pass-983!"

    def setUp(self):
        self.manager = User.objects.create_user(
            username="sms.api.manager",
            password=self.password,
            role=User.Role.SALES_MANAGER,
        )
        self.agent = User.objects.create_user(
            username="sms.api.agent",
            password=self.password,
            role=User.Role.SALES_AGENT,
        )
        self.platform = User.objects.create_user(
            username="sms.api.platform",
            password=self.password,
            role=User.Role.PLATFORM_ADMIN,
        )
        self.message = store_normalized_inbound_sms(event=sms_event(), actor=self.manager).message
        store_normalized_inbound_sms(
            event=sms_event(
                external_message_id="external-2",
                provider_received_at=datetime(2026, 8, 13, 21, 45, tzinfo=UTC),
            )
        )
        self.query = {
            "period_start": "2026-08-13T19:00:00Z",
            "period_end": "2026-08-14T22:00:00Z",
        }

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_manager_report_groups_by_tehran_date_and_hour(self):
        response = self.client_for(self.manager).get("/api/v1/reports/inbound-sms/", self.query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["timezone"], "Asia/Tehran")
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(
            response.data["results"],
            [
                {"local_date": "2026-08-14", "local_hour": 0, "inbound_sms_count": 1},
                {"local_date": "2026-08-14", "local_hour": 1, "inbound_sms_count": 1},
            ],
        )

    def test_report_filters_and_drilldown_keep_same_scope(self):
        query = {**self.query, "provider_code": "future_provider", "recipient_normalized": "+989999990000"}
        report = self.client_for(self.manager).get("/api/v1/reports/inbound-sms/", query)
        self.assertEqual(report.status_code, 200)
        detail = self.client_for(self.manager).get(
            "/api/v1/reports/inbound-sms/drilldown/",
            {**query, "local_date": "2026-08-14", "local_hour": 0},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["count"], 1)
        self.assertEqual(detail.data["results"][0]["id"], self.message.pk)
        self.assertNotIn("body", detail.data["results"][0])

    def test_agent_and_inactive_user_cannot_read_counts_or_direct_rows(self):
        agent_client = self.client_for(self.agent)
        self.assertEqual(agent_client.get("/api/v1/reports/inbound-sms/", self.query).status_code, 403)
        self.assertEqual(
            agent_client.get(f"/api/v1/reports/inbound-sms/messages/{self.message.pk}/").status_code,
            403,
        )
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active"])
        self.assertEqual(agent_client.get("/api/v1/reports/inbound-sms/", self.query).status_code, 403)

    def test_elevated_direct_detail_is_read_only_and_no_webhook_exists(self):
        client = self.client_for(self.platform)
        detail_url = f"/api/v1/reports/inbound-sms/messages/{self.message.pk}/"
        self.assertEqual(client.get(detail_url).status_code, 200)
        self.assertEqual(client.post(detail_url, {}, format="json").status_code, 405)
        self.assertEqual(client.post("/api/v1/reports/inbound-sms/", {}, format="json").status_code, 405)
        with self.assertRaises(Resolver404):
            resolve("/api/v1/sms/webhook/")

    def test_query_limits_and_duplicate_parameters_fail(self):
        client = self.client_for(self.manager)
        too_long = client.get(
            "/api/v1/reports/inbound-sms/",
            {"period_start": "2025-01-01T00:00:00Z", "period_end": "2026-08-14T00:00:00Z"},
        )
        self.assertEqual(too_long.status_code, 400)
        duplicate = client.get(
            "/api/v1/reports/inbound-sms/?period_start=2026-08-13T19%3A00%3A00Z&period_start=2026-08-13T20%3A00%3A00Z&period_end=2026-08-14T22%3A00%3A00Z"
        )
        self.assertEqual(duplicate.status_code, 400)


@skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL concurrency proof runs in the isolated PostgreSQL harness.",
)
class InboundSMSConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def test_concurrent_same_event_creates_one_row(self):
        barrier = Barrier(2)
        lock = Lock()
        results = []
        errors = []

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                result = store_normalized_inbound_sms(event=sms_event())
                with lock:
                    results.append(result.created)
            except Exception as exc:
                with lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [Thread(target=worker), Thread(target=worker)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(InboundSMS.objects.count(), 1)
