"""Live updates (2.38.0): publishing, the stream, and the ways it stays optional."""

import json
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from common import realtime, realtime_signals
from common.realtime_views import EventStreamView
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from sales.models import Customer

PASSWORD = "Strong-pass-937!"


@contextmanager
def without_feature():
    profile = DeploymentProfile(
        profile_id="x", features=frozenset(ALL_FEATURES) - {"realtime"}, source="signed-manifest"
    )
    with override_active_profile(profile):
        yield


class Fixtures(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="rt.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.subscriber = realtime.BROKER.subscribe(self.manager.pk)
        self.addCleanup(realtime.BROKER.unsubscribe, self.subscriber)

    def drain(self):
        events = []
        while not self.subscriber.queue.empty():
            events.append(self.subscriber.queue.get_nowait())
        return events


@override_settings(REALTIME_ENABLED=True, REALTIME_SERVE_STREAMS=True)
class PublishTests(Fixtures):
    def setUp(self):
        super().setUp()
        # These tests exercise the in-process path (what development uses); the
        # PostgreSQL path has its own test below. Pinned so a PostgreSQL test run
        # does not route them through NOTIFY, which nothing here listens to.
        patcher = mock.patch("common.realtime.connection", SimpleNamespace(vendor="sqlite"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_event_reaches_a_subscriber_only_after_the_transaction_commits(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            realtime.publish("customer", object_id=5)
        self.assertEqual(self.drain(), [])  # nothing yet: the write has not committed
        for callback in callbacks:
            callback()
        self.assertEqual([event["k"] for event in self.drain()], ["customer"])

    def test_saving_a_record_announces_its_kind(self):
        with self.captureOnCommitCallbacks(execute=True):
            Customer.objects.create(full_name="زنده", created_by=self.manager)
        self.assertIn("customer", [event["k"] for event in self.drain()])

    def test_a_targeted_event_reaches_only_the_users_it_names(self):
        other = realtime.BROKER.subscribe(user_id=999999)
        self.addCleanup(realtime.BROKER.unsubscribe, other)
        with self.captureOnCommitCallbacks(execute=True):
            realtime.publish("chat", object_id=1, users=[self.manager.pk])
        self.assertEqual(len(self.drain()), 1)
        self.assertTrue(other.queue.empty())

    def test_a_browser_is_told_the_kind_and_never_a_record_id_for_business_lists(self):
        shown = realtime.public_event({"k": "customer", "i": 42, "u": None, "t": 1})
        self.assertEqual(shown, {"k": "customer", "i": None, "t": 1})
        self.assertEqual(realtime.public_event({"k": "chat", "i": 7, "u": [1], "t": 2})["i"], 7)

    def test_a_slow_browser_is_told_to_re_read_instead_of_being_sent_a_backlog(self):
        for number in range(300):
            self.subscriber.offer({"k": "x", "t": number})
        self.assertTrue(self.subscriber.overflowed)

    def test_the_hard_off_switch_and_the_feature_each_silence_publishing(self):
        with override_settings(REALTIME_ENABLED=False), self.captureOnCommitCallbacks(execute=True):
            realtime.publish("customer")
        with without_feature(), self.captureOnCommitCallbacks(execute=True):
            realtime.publish("customer")
        self.assertEqual(self.drain(), [])

    def test_a_failure_in_publishing_never_breaks_the_write(self):
        with mock.patch("common.realtime.transaction.on_commit", side_effect=RuntimeError("boom")):
            with self.assertLogs("dolphin.realtime", level="ERROR"):
                realtime.publish("customer")  # must not raise

    def test_on_postgresql_the_event_goes_through_notify_inside_the_transaction(self):
        executed = []

        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params):
                executed.append((sql, params))

        fake = SimpleNamespace(vendor="postgresql", cursor=lambda: FakeCursor())
        with mock.patch("common.realtime.connection", fake):
            realtime.publish("invoice", object_id=3)
            realtime.publish("chat", object_id=1, users=list(range(5000)))  # too big: sent without recipients
        self.assertEqual(executed[0][0], "SELECT pg_notify(%s, %s)")
        self.assertEqual(executed[0][1][0], realtime.CHANNEL)
        self.assertEqual(json.loads(executed[0][1][1])["k"], "invoice")
        oversized = json.loads(executed[1][1][1])
        self.assertIsNone(oversized["u"])
        self.assertLessEqual(len(executed[1][1][1].encode()), realtime.MAX_PAYLOAD_BYTES)

    def test_the_chat_and_call_signals_name_their_recipients(self):
        seen = []
        participants = SimpleNamespace(values_list=lambda *a, **k: [4, 5])
        message = SimpleNamespace(thread=SimpleNamespace(participants=participants), thread_id=9)
        with mock.patch("common.realtime.publish", lambda kind, **kw: seen.append((kind, kw))):
            realtime_signals._chat_message(None, message, created=True)
            realtime_signals._chat_message(None, message, created=False)
            realtime_signals._call_notification(None, SimpleNamespace(user_id=8, pk=3), created=True)
        self.assertEqual(seen, [("chat", {"object_id": 9, "users": [4, 5]}), ("call", {"object_id": 3, "users": [8]})])


@override_settings(REALTIME_ENABLED=True, REALTIME_SERVE_STREAMS=True)
class StreamTests(Fixtures):
    url = "/api/v1/realtime/events/"

    def test_an_anonymous_visitor_is_refused(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_a_signed_in_user_gets_the_stream_and_the_events_queued_for_them(self):
        # Called directly rather than through the test client: closing a
        # streaming response through the client fires `request_finished`, which
        # on a real database closes the connection the rest of the run uses.
        request = RequestFactory().get(self.url)
        request.user = self.manager
        with mock.patch("common.realtime_views.connections") as connections:
            response = EventStreamView.as_view()(request)
        # A stream holds no database connection while it waits.
        connections.close_all.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        realtime.BROKER.deliver({"k": "customer", "i": 3, "u": None, "t": 10})
        chunks = iter(response.streaming_content)
        self.assertIn("retry:", next(chunks).decode())
        second = next(chunks).decode()
        self.assertEqual(json.loads(second.removeprefix("data: ").strip()), {"k": "customer", "i": None, "t": 10})
        before = realtime.BROKER.count()
        for closer in response._resource_closers:  # what closing the response runs
            closer()
        self.assertEqual(realtime.BROKER.count(), before - 1)

    @override_settings(REALTIME_SERVE_STREAMS=False)
    def test_the_ordinary_web_workers_never_hold_a_stream(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    @override_settings(REALTIME_ENABLED=False)
    def test_switched_off_it_is_not_there(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_without_the_feature_it_is_not_there(self):
        self.client.force_login(self.manager)
        with without_feature():
            self.assertEqual(self.client.get(self.url).status_code, 404)

    @override_settings(REALTIME_MAX_CONNECTIONS=1)
    def test_the_connection_ceiling_answers_503_with_a_retry_hint(self):
        self.client.force_login(self.manager)  # `self.subscriber` already fills the only slot
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "30")

    def test_the_health_probe_reports_without_authentication(self):
        body = self.client.get("/api/v1/realtime/health/").json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("connections", body)
        with override_settings(REALTIME_SERVE_STREAMS=False):
            self.assertEqual(self.client.get("/api/v1/realtime/health/").status_code, 404)


class PageTests(Fixtures):
    def page(self):
        self.client.force_login(self.manager)
        return self.client.get("/").content.decode("utf-8")

    @override_settings(REALTIME_ENABLED=True)
    def test_the_page_declares_its_stream_when_live_updates_are_on(self):
        self.assertIn(f'<meta name="dolphin-realtime" content="{reverse("realtime-events")}">', self.page())

    @override_settings(REALTIME_ENABLED=False)
    def test_the_page_is_unchanged_when_they_are_off(self):
        self.assertNotIn("dolphin-realtime", self.page())

    @override_settings(REALTIME_ENABLED=True)
    def test_the_feature_is_off_by_default_for_a_deployment(self):
        from common.deployment.registry import DEFAULT_FEATURES

        self.assertNotIn("realtime", DEFAULT_FEATURES)


class PerUserCeilingTests(Fixtures):
    @override_settings(REALTIME_MAX_PER_USER=2)
    def test_a_user_beyond_the_ceiling_pushes_out_their_oldest_connection(self):
        first = realtime.BROKER.subscribe(4242)
        second = realtime.BROKER.subscribe(4242)
        third = realtime.BROKER.subscribe(4242)
        for subscriber in (first, second, third):
            self.addCleanup(realtime.BROKER.unsubscribe, subscriber)
        self.assertTrue(first.evicted)
        self.assertFalse(second.evicted or third.evicted)

    @override_settings(REALTIME_ENABLED=True, REALTIME_SERVE_STREAMS=True)
    def test_every_connection_starts_with_a_resync(self):
        request = RequestFactory().get("/api/v1/realtime/events/")
        request.user = self.manager
        with mock.patch("common.realtime_views.connections"):
            response = EventStreamView.as_view()(request)
        first = next(iter(response.streaming_content)).decode()
        self.assertIn('"k": "resync"', first)
        for closer in response._resource_closers:
            closer()
