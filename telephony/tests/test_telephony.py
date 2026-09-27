"""The Asterisk connector (2.22.0), tested without a PBX.

* the AMI client against a fake AMI server: login, refused login, heartbeat,
  malformed lines, reconnecting after the server drops the session;
* the call tracker against recorded event sequences: inbound answered and
  missed, outbound answered and busy, a transfer, a queue;
* the CDR sync against fixture rows: gap-filling, correcting, idempotence;
* recordings: `Range`, refusal of a path out of the recordings root, the
  permission and the audit trail;
* the listener end to end, from the fake server to a `Call` row.
"""

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, UserCapabilityOverride
from auditlog.models import ActivityLog
from integrations.models import DomainEvent, Integration
from integrations.services import create_integration
from sales.services import create_customer_with_phone
from telephony import ami
from telephony.cdr import sync
from telephony.models import Call, CdrSyncState, Extension
from telephony.tests.fake_ami import FakeAMIServer, load_fixture
from telephony.tracker import CallTracker, channel_peer

PASSWORD = "Strong-pass-448!"
TEHRAN = ZoneInfo("Asia/Tehran")


def asterisk_config(port=5038, **extra):
    return {
        "ami_host": "127.0.0.1", "ami_port": port, "ami_username": "dolphin",
        "internal_extension_max_length": 5, "outbound_prefix": "9",
        "originate_context": "from-internal", "originate_channel": "Local/{extension}@from-internal",
        **extra,
    }


class SteppingClock:
    """A clock that moves ten seconds each time it is read."""

    def __init__(self):
        self.now = timezone.now().replace(microsecond=0)

    def __call__(self):
        self.now += timedelta(seconds=10)
        return self.now


class Fixtures(TestCase):
    def tearDown(self):
        cache.clear()
        super().tearDown()

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(username="tp.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="tp.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="tp.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other = User.objects.create_user(username="tp.other", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مشتری تلفنی", phone={"raw_phone": "09151234567", "is_primary": True}
        )
        self.pbx = create_integration(
            actor=self.admin, provider_key="asterisk", name="مرکز تلفن اصلی",
            config=asterisk_config(), secrets={"ami_password": "amipass"}, enabled=True,
        )
        Extension.objects.create(integration=self.pbx, number="201", user=self.agent)
        Extension.objects.create(integration=self.pbx, number="202", user=self.other)

    def play(self, name):
        tracker = CallTracker(self.pbx, clock=SteppingClock())
        with self.captureOnCommitCallbacks(execute=True):
            for event in load_fixture(name):
                tracker.handle(event)
        return Call.objects.get(linkedid=load_fixture(name)[0]["Linkedid"])


class ParserTests(SimpleTestCase):
    def test_messages_are_parsed_and_malformed_lines_skipped(self):
        message = ami.parse_message(["Event: Newchannel", "garbage without colon", ": no key", "Channel: PJSIP/201-1"])
        self.assertEqual(message, {"Event": "Newchannel", "Channel": "PJSIP/201-1"})

    def test_an_action_cannot_smuggle_a_second_line(self):
        wire = ami.format_action("Originate", {"CallerID": "x\r\nAction: Logoff"}, "1").decode()
        self.assertNotIn("\r\nAction: Logoff", wire)

    def test_the_peer_of_a_channel(self):
        self.assertEqual(channel_peer("PJSIP/201-0000002a"), "201")
        self.assertEqual(channel_peer("Local/201@from-internal-0001;1"), "201")
        self.assertEqual(channel_peer("PJSIP/trunk-00000005"), "trunk")


class AMIClientTests(SimpleTestCase):
    def setUp(self):
        self.server = FakeAMIServer().start()

    def tearDown(self):
        self.server.stop()

    def test_login_ping_and_a_refused_password(self):
        async def scenario():
            connection = await ami.AMIConnection.open("127.0.0.1", self.server.port)
            await connection.login("dolphin", "amipass")
            self.assertEqual((await connection.ping())["Ping"], "Pong")
            await connection.close()
            wrong = await ami.AMIConnection.open("127.0.0.1", self.server.port)
            with self.assertRaises(ami.AuthenticationFailed):
                await wrong.login("dolphin", "not-it")
            await wrong.close()

        asyncio.run(scenario())
        self.assertEqual(self.server.logins, [True, False])

    def test_the_session_survives_garbage_heartbeats_and_reconnects(self):
        received, statuses = [], []

        async def scenario():
            stop = asyncio.Event()

            async def loader():
                return "127.0.0.1", self.server.port, "dolphin", "amipass"

            async def on_event(event):
                received.append(event["Event"])

            async def on_status(ok, message):
                statuses.append(ok)

            task = asyncio.create_task(ami.run_forever(
                loader, on_event, stop=stop, on_status=on_status, heartbeat=0.2,
                backoff=iter([0.05] * 50),
            ))
            await asyncio.get_running_loop().run_in_executor(None, self.server.logged_in.wait, 5)
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self.server.push([{"Event": "Newchannel", "Linkedid": "1"}], garbage=True)
            )
            await asyncio.sleep(0.5)
            await asyncio.get_running_loop().run_in_executor(None, self.server.drop_clients)
            await asyncio.get_running_loop().run_in_executor(None, self.server.logged_in.wait, 5)
            stop.set()
            await asyncio.wait_for(task, 5)

        asyncio.run(scenario())
        self.assertIn("Newchannel", received)
        self.assertIn("Ping", self.server.actions)
        self.assertGreaterEqual(self.server.connections, 2)
        self.assertTrue(statuses[0])


class TrackerTests(Fixtures):
    def test_an_answered_inbound_call(self):
        call = self.play("inbound_answered")
        self.assertEqual((call.direction, call.status), ("inbound", "completed"))
        self.assertEqual(call.external_number, "+989151234567")
        self.assertEqual((call.person_type, call.person_id), ("customer", self.customer.pk))
        self.assertEqual((call.extension, call.user_id), ("201", self.agent.pk))
        self.assertGreater(call.billsec, 0)
        self.assertGreater(call.duration, call.billsec)
        kinds = set(DomainEvent.objects.values_list("event_type", flat=True))
        self.assertEqual(kinds, {"call.started", "call.answered", "call.ended"})

    def test_a_missed_inbound_call_names_everyone_who_was_rung(self):
        call = self.play("inbound_missed")
        self.assertEqual(call.status, "missed")
        self.assertEqual(call.billsec, 0)
        missed = DomainEvent.objects.get(event_type="call.missed")
        self.assertEqual(missed.payload["rung_extensions"], ["201", "202"])
        self.assertEqual(missed.person_id, self.customer.pk)

    def test_an_answered_outbound_call_strips_the_line_prefix(self):
        call = self.play("outbound_answered")
        self.assertEqual((call.direction, call.status, call.extension), ("outbound", "completed", "201"))
        self.assertEqual(call.external_number, "+989151234567")
        self.assertEqual(call.user_id, self.agent.pk)

    def test_a_busy_outbound_call(self):
        call = self.play("outbound_busy")
        self.assertEqual(call.status, "busy")
        self.assertEqual(call.person_type, "")

    def test_a_transferred_call_stays_one_call(self):
        call = self.play("transfer")
        self.assertEqual(Call.objects.count(), 1)
        self.assertEqual((call.status, call.extension), ("completed", "201"))

    def test_a_queue_member_answering(self):
        call = self.play("queue")
        self.assertEqual((call.status, call.extension, call.user_id), ("completed", "203", None))

    def test_events_replayed_do_not_duplicate(self):
        self.play("inbound_answered")
        self.play("inbound_answered")
        self.assertEqual(Call.objects.count(), 1)
        self.assertEqual(DomainEvent.objects.filter(event_type="call.ended").count(), 1)

    def test_an_unknown_or_broken_event_is_ignored(self):
        tracker = CallTracker(self.pbx)
        self.assertIsNone(tracker.handle({"Event": "VarSet"}))
        self.assertIsNone(tracker.handle({"Linkedid": "x"}))
        self.assertIsNone(tracker.handle({"Event": "Hangup", "Linkedid": "nope"}))


class CdrTests(Fixtures):
    def rows(self):
        base = datetime(2026, 9, 27, 10, 0, 0)
        return [
            # A call the listener never saw: answered, recorded.
            {"calldate": base, "src": "09151234567", "dst": "201", "dstchannel": "PJSIP/201-00000001",
             "disposition": "ANSWERED", "duration": 95, "billsec": 80, "uniqueid": "c1", "linkedid": "c1",
             "recordingfile": "in-09151234567-201-20260927-100000-c1.wav", "clid": "", "dcontext": "from-trunk"},
            # The same call's second leg (a duplicate row).
            {"calldate": base, "src": "09151234567", "dst": "201", "dstchannel": "PJSIP/201-00000001",
             "disposition": "ANSWERED", "duration": 95, "billsec": 80, "uniqueid": "c1b", "linkedid": "c1",
             "recordingfile": "", "clid": "", "dcontext": "from-trunk"},
            # A missed inbound.
            {"calldate": base + timedelta(minutes=5), "src": "09129990000", "dst": "202", "disposition": "NO ANSWER",
             "duration": 20, "billsec": 0, "uniqueid": "c2", "linkedid": "c2", "recordingfile": "", "clid": "", "dcontext": ""},
        ]

    def fetch(self, rows):
        def fake(config, secrets, since, until, limit=2000):
            return [row for row in rows if since.replace(tzinfo=None) <= row["calldate"] < until.replace(tzinfo=None)]

        return fake

    def test_gaps_are_filled_and_a_rerun_changes_nothing(self):
        now = datetime(2026, 9, 27, 12, 0, tzinfo=TEHRAN)
        with self.captureOnCommitCallbacks(execute=True):
            first = sync(self.pbx, now=now, fetch=self.fetch(self.rows()))
        self.assertEqual((first["calls"], first["created"]), (2, 2))
        answered = Call.objects.get(linkedid="c1")
        self.assertEqual((answered.status, answered.duration, answered.billsec), ("completed", 95, 80))
        self.assertEqual(answered.recording, "in-09151234567-201-20260927-100000-c1.wav")
        self.assertEqual((answered.person_id, answered.user_id), (self.customer.pk, self.agent.pk))
        self.assertEqual(Call.objects.get(linkedid="c2").status, "missed")
        self.assertIsNotNone(CdrSyncState.objects.get(integration=self.pbx).cursor)
        second = sync(self.pbx, now=now, fetch=self.fetch(self.rows()))
        self.assertEqual((second["created"], second["changed"]), (0, 0))
        self.assertEqual(DomainEvent.objects.filter(event_type="call.ended").count(), 2)

    def test_the_cdr_corrects_a_call_the_listener_left_open(self):
        call = Call.objects.create(
            integration=self.pbx, linkedid="c1", direction="inbound", status="answered",
            started_at=datetime(2026, 9, 27, 10, 0, tzinfo=TEHRAN), answered_at=datetime(2026, 9, 27, 10, 0, 15, tzinfo=TEHRAN),
        )
        sync(self.pbx, now=datetime(2026, 9, 27, 12, 0, tzinfo=TEHRAN), fetch=self.fetch(self.rows()))
        call.refresh_from_db()
        self.assertEqual((call.status, call.billsec, call.seen_in_cdr), ("completed", 80, True))

    def test_a_range_rerun_leaves_the_cursor_alone(self):
        sync(self.pbx, now=datetime(2026, 9, 27, 12, 0, tzinfo=TEHRAN), fetch=self.fetch(self.rows()))
        cursor = CdrSyncState.objects.get(integration=self.pbx).cursor
        sync(self.pbx, since=datetime(2026, 9, 1, tzinfo=TEHRAN), until=datetime(2026, 9, 2, tzinfo=TEHRAN), fetch=self.fetch(self.rows()))
        self.assertEqual(CdrSyncState.objects.get(integration=self.pbx).cursor, cursor)


class RecordingTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp())
        day = self.root / "2026" / "09" / "27"
        day.mkdir(parents=True)
        (day / "rec.wav").write_bytes(bytes(range(256)) * 4)
        (self.root / "secret.txt").write_text("nope")
        self.pbx.config = {**self.pbx.config, "recordings_mode": "mount", "recordings_path": str(self.root)}
        self.pbx.save()
        self.call = Call.objects.create(
            integration=self.pbx, linkedid="r1", direction="inbound", status="completed", user=self.agent,
            started_at=datetime(2026, 9, 27, 10, 0, tzinfo=TEHRAN), recording="rec.wav",
        )

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_the_whole_file_and_a_range(self):
        whole = self.api(self.manager).get(f"/api/v1/calls/{self.call.pk}/recording/")
        self.assertEqual(whole.status_code, 200)
        self.assertEqual(len(b"".join(whole.streaming_content)), 1024)
        part = self.api(self.manager).get(f"/api/v1/calls/{self.call.pk}/recording/", HTTP_RANGE="bytes=10-19")
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part["Content-Range"], "bytes 10-19/1024")
        self.assertEqual(b"".join(part.streaming_content), bytes(range(10, 20)))
        self.assertEqual(self.api(self.manager).get(f"/api/v1/calls/{self.call.pk}/recording/", HTTP_RANGE="bytes=5000-").status_code, 416)
        self.assertEqual(ActivityLog.objects.filter(operation="call.recording_played").count(), 1)

    def test_a_path_out_of_the_root_or_a_non_audio_file_is_refused(self):
        for reference in ("../../../etc/passwd.wav", "secret.txt", "/etc/shadow.wav"):
            with self.subTest(reference=reference):
                Call.objects.filter(pk=self.call.pk).update(recording=reference)
                self.assertEqual(self.api(self.manager).get(f"/api/v1/calls/{self.call.pk}/recording/").status_code, 404)

    def test_the_permission_and_the_scope(self):
        # An agent's default rights include their own calls but not recordings.
        self.assertEqual(self.api(self.agent).get(f"/api/v1/calls/{self.call.pk}/recording/").status_code, 403)
        UserCapabilityOverride.objects.create(user=self.other, capability="calls.recordings", granted=True)
        self.assertEqual(self.api(self.other).get(f"/api/v1/calls/{self.call.pk}/recording/").status_code, 404)


class CallApiTests(Fixtures):
    def test_calls_are_scoped(self):
        self.play("inbound_answered")
        self.play("outbound_busy")
        agent = APIClient()
        agent.force_authenticate(self.other)
        self.assertEqual(agent.get("/api/v1/calls/").data["count"], 0)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        rows = manager.get(f"/api/v1/calls/?person_type=customer&person_id={self.customer.pk}").data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["person_url"], f"/customers/{self.customer.pk}/")

    def test_extensions_are_the_platform_admins(self):
        admin = APIClient()
        admin.force_authenticate(self.admin)
        created = admin.post("/api/v1/telephony/extensions/", {"integration": self.pbx.pk, "number": "205", "user": self.manager.pk}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(admin.post("/api/v1/telephony/extensions/", {"integration": self.pbx.pk, "number": "205"}, format="json").status_code, 409)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        self.assertEqual(manager.get("/api/v1/telephony/extensions/").status_code, 403)

    def test_a_connection_with_calls_cannot_be_deleted(self):
        self.play("inbound_answered")
        admin = APIClient()
        admin.force_authenticate(self.admin)
        self.assertEqual(admin.delete(f"/api/v1/integrations/{self.pbx.pk}/").status_code, 409)

    def test_the_integrations_page_maps_extensions_for_the_platform_admin(self):
        self.client.force_login(self.admin)
        page = self.client.get("/settings/integrations/").content.decode()
        self.assertIn('id="integration-extensions"', page)
        self.assertIn(f'<option value="{self.manager.pk}">', page)
        from common.deployment.profile import DeploymentProfile, override_active_profile
        from common.deployment.registry import ALL_FEATURES

        without = DeploymentProfile(
            profile_id="client-1", features=frozenset(ALL_FEATURES) - {"telephony"}, source="signed-manifest",
        )
        with override_active_profile(without):
            self.assertNotIn('id="integration-extensions"', self.client.get("/settings/integrations/").content.decode())
        self.client.force_login(self.manager)
        self.assertNotIn('id="integration-extensions"', self.client.get("/settings/integrations/").content.decode())

    def test_technical_fields_are_typed_left_to_right(self):
        from integrations.providers import provider_for

        fields = {field["key"]: field for field in provider_for("asterisk").describe()["fields"]}
        self.assertTrue(fields["originate_channel"]["ltr"])
        self.assertTrue(fields["ami_host"]["ltr"])
        self.assertFalse(fields["missed_call_task"]["ltr"])


@override_settings(DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS=True)
class ListenerEndToEndTests(TransactionTestCase):
    """The fake PBX, the real listener, the real database."""

    def setUp(self):
        cache.clear()
        self.server = FakeAMIServer().start()
        self.admin = User.objects.create_user(username="e2e.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="e2e.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.admin, full_name="مشتری سرتاسری", phone={"raw_phone": "09151234567", "is_primary": True}
        )
        self.pbx = create_integration(
            actor=self.admin, provider_key="asterisk", name="PBX آزمایشی",
            config=asterisk_config(port=self.server.port), secrets={"ami_password": "amipass"}, enabled=True,
        )
        Extension.objects.create(integration=self.pbx, number="201", user=self.agent)

    def tearDown(self):
        self.server.stop()
        cache.clear()

    def test_a_call_travels_from_the_pbx_to_a_row(self):
        from concurrent.futures import ThreadPoolExecutor

        from telephony.worker import _close_connections, _listen

        async def scenario():
            stop = asyncio.Event()
            probe = ThreadPoolExecutor(max_workers=1)
            task = asyncio.create_task(_listen(self.pbx, stop))
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.server.logged_in.wait, 5)
            await loop.run_in_executor(None, self.server.push, load_fixture("inbound_answered"))
            for _ in range(50):
                done = await loop.run_in_executor(probe, lambda: Call.objects.filter(status="completed").exists())
                if done:
                    break
                await asyncio.sleep(0.1)
            stop.set()
            await asyncio.wait_for(task, 10)
            await loop.run_in_executor(probe, _close_connections)
            probe.shutdown(wait=True)

        asyncio.run(scenario())
        call = Call.objects.get()
        self.assertEqual((call.status, call.person_id, call.user_id), ("completed", self.customer.pk, self.agent.pk))
        self.pbx.refresh_from_db()
        self.assertEqual(self.pbx.status, Integration.Status.OK)

    def test_the_connection_test_reaches_the_fake_pbx(self):
        from integrations.services import test_integration

        self.assertTrue(test_integration(actor=self.admin, integration=self.pbx).ok)
        self.pbx.config = {**self.pbx.config, "ami_username": "nobody"}
        self.pbx.save()
        self.assertFalse(test_integration(actor=self.admin, integration=self.pbx).ok)
