"""Popup, click-to-call and the CRM hooks (2.23.0), tested without a PBX.

* placing a call: every refusal, the queue, the worker sending `Originate`
  to the fake AMI server, and a request nobody claimed expiring;
* the tracker's two click-to-call rules (internal legs do not answer an
  outbound call; `OriginateResponse: Failure` closes it);
* the hooks: a popup when an extension rings, popups and a follow-up task
  when a call is missed, a fresh score when a call ends;
* the popup API, the timeline, per-user figures and the score factor, each
  for the reader's own scope;
* what the profile page offers.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from integrations.models import Integration
from integrations.services import create_integration
from sales.models import Lead
from sales.services import create_customer_with_phone
from scoring.models import PersonScore
from tasks.models import Task
from telephony.models import Call, CallNotification, Extension, OriginateRequest
from telephony.services import dial_string, expire_stale_originates
from telephony.tests.fake_ami import FakeAMIServer
from telephony.tests.test_telephony import PASSWORD, Fixtures, asterisk_config
from telephony.tracker import CallTracker


class DialStringTests(Fixtures):
    def test_numbers_are_dialled_the_way_a_phone_in_iran_dials_them(self):
        self.assertEqual(dial_string(self.pbx, "+989121234567"), ("909121234567", "+989121234567"))
        self.assertEqual(dial_string(self.pbx, "۰۹۱۲ ۱۲۳ ۴۵۶۷"), ("909121234567", "+989121234567"))
        self.assertEqual(dial_string(self.pbx, "+441632960000"), ("900441632960000", ""))
        self.assertEqual(dial_string(self.pbx, "202"), ("202", ""))

    def test_what_is_not_a_number_is_refused(self):
        from common.exceptions import BusinessRuleError

        for bad in ("", "12a4", "++98912", "9" * 30):
            with self.assertRaises(BusinessRuleError):
                dial_string(self.pbx, bad)


class OriginateApiTests(Fixtures):
    def setUp(self):
        super().setUp()
        Integration.objects.filter(pk=self.pbx.pk).update(status=Integration.Status.OK)
        self.api = APIClient()
        self.api.force_authenticate(self.agent)

    def post(self, client=None, **body):
        return (client or self.api).post("/api/v1/telephony/originate/", {"number": "09151234567", **body}, format="json")

    def test_a_call_is_queued_from_the_callers_own_extension(self):
        response = self.post()
        self.assertEqual(response.status_code, 202, response.data)
        request = OriginateRequest.objects.get(pk=response.data["id"])
        self.assertEqual((request.extension, request.dial, request.user_id), ("201", "909151234567", self.agent.pk))
        self.assertEqual(request.external_number, "+989151234567")
        self.assertTrue(ActivityLog.objects.filter(operation="call.originate_requested", actor=self.agent).exists())
        status = self.api.get(f"/api/v1/telephony/originate/{request.pk}/")
        self.assertEqual(status.data["status"], "pending")

    def test_one_call_at_a_time(self):
        self.assertEqual(self.post().status_code, 202)
        self.assertEqual(self.post().status_code, 409)

    def test_refusals_are_specific(self):
        # No extension of their own.
        manager = APIClient()
        manager.force_authenticate(self.manager)
        response = self.post(manager)
        self.assertEqual(response.status_code, 400)
        self.assertIn("extension", response.data)
        # No permission to place calls.
        from accounts.models import UserCapabilityOverride

        UserCapabilityOverride.objects.create(user=self.other, capability="calls.originate", granted=False)
        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(self.post(other).status_code, 403)
        # The PBX is not connected.
        Integration.objects.filter(pk=self.pbx.pk).update(status=Integration.Status.ERROR)
        self.assertEqual(self.post().status_code, 409)
        Integration.objects.filter(pk=self.pbx.pk).update(status=Integration.Status.OK)
        # Not a number; a person outside the caller's scope.
        self.assertEqual(self.post(number="abc").status_code, 400)
        self.assertEqual(self.post(person_type="customer", person_id=self.customer.pk).status_code, 400)
        self.assertFalse(OriginateRequest.objects.exists())

    def test_someone_elses_request_is_not_theirs_to_read(self):
        request_id = self.post().data["id"]
        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(other.get(f"/api/v1/telephony/originate/{request_id}/").status_code, 404)

    def test_a_request_nobody_claimed_expires(self):
        request_id = self.post().data["id"]
        OriginateRequest.objects.filter(pk=request_id).update(created_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(expire_stale_originates(), 1)
        body = self.api.get(f"/api/v1/telephony/originate/{request_id}/").data
        self.assertEqual(body["status"], "failed")
        self.assertTrue(body["error"])


class OriginateTrackerTests(Fixtures):
    def originated_call(self):
        return Call.objects.create(
            integration=self.pbx, linkedid="dolphin-abc", direction=Call.Direction.OUTBOUND,
            caller_raw="201", callee_raw="909151234567", external_number="+989151234567",
            extension="201", user=self.agent, started_at=timezone.now(),
        )

    def test_the_users_own_phone_answering_does_not_answer_the_call(self):
        call = self.originated_call()
        tracker = CallTracker(self.pbx)
        with self.captureOnCommitCallbacks(execute=True):
            for event in (
                {"Event": "Newchannel", "Linkedid": "dolphin-abc", "Uniqueid": "dolphin-abc", "Channel": "Local/201@from-internal-0001;1", "CallerIDNum": "909151234567", "Exten": "201"},
                {"Event": "DialEnd", "Linkedid": "dolphin-abc", "DestChannel": "PJSIP/201-00000031", "DestCallerIDNum": "201", "DialStatus": "ANSWER"},
                {"Event": "BridgeEnter", "Linkedid": "dolphin-abc", "Channel": "PJSIP/201-00000031", "BridgeNumChannels": "2"},
            ):
                tracker.handle(event)
        call.refresh_from_db()
        self.assertIsNone(call.answered_at)
        with self.captureOnCommitCallbacks(execute=True):
            tracker.handle({"Event": "DialEnd", "Linkedid": "dolphin-abc", "DestChannel": "PJSIP/trunk-00000032", "DestCallerIDNum": "09151234567", "DialStatus": "ANSWER"})
        call.refresh_from_db()
        self.assertEqual(call.status, Call.Status.ANSWERED)

    def test_a_refused_originate_closes_the_call(self):
        call = self.originated_call()
        with self.captureOnCommitCallbacks(execute=True):
            CallTracker(self.pbx).handle({"Event": "OriginateResponse", "Uniqueid": "dolphin-abc", "Response": "Failure", "Reason": "5"})
        call.refresh_from_db()
        self.assertEqual((call.status, call.hangup_cause), (Call.Status.BUSY, "originate:5"))


class HookTests(Fixtures):
    def test_a_ringing_extension_gets_a_popup(self):
        self.play("inbound_answered")
        self.assertTrue(CallNotification.objects.filter(user=self.agent, kind="ringing").exists())

    def test_no_popup_when_the_connection_turns_them_off(self):
        self.pbx.config = {**self.pbx.config, "call_popup": False}
        self.pbx.save()
        self.play("inbound_missed")
        self.assertFalse(CallNotification.objects.exists())

    def test_a_missed_call_raises_popups_and_one_follow_up_task(self):
        lead = Lead.objects.create(
            customer=self.customer, created_by=self.manager, assigned_to=self.other, assigned_by=self.manager,
            assigned_at=timezone.now(),
        )
        call = self.play("inbound_missed")
        self.assertEqual(call.status, Call.Status.MISSED)
        rung = set(CallNotification.objects.filter(kind="missed").values_list("user__username", flat=True))
        self.assertEqual(rung, {"tp.agent", "tp.other"})
        task = Task.objects.get(source=Task.Source.MISSED_CALL)
        self.assertEqual((task.assignee_id, task.person_id, task.source_ref), (lead.assigned_to_id, self.customer.pk, f"call:{call.pk}"))
        # The same call again (the CDR sync, a replay) never raises a second task.
        from integrations.events import emit

        with self.captureOnCommitCallbacks(execute=True):
            emit("call.missed", {"call": call.pk}, dedupe_key=f"call:{call.pk}:missed:again")
        self.assertEqual(Task.objects.filter(source=Task.Source.MISSED_CALL).count(), 1)

    def test_an_ended_call_refreshes_the_score(self):
        self.play("inbound_answered")
        self.assertTrue(PersonScore.objects.filter(person_type="customer", person_id=self.customer.pk).exists())


class PopupApiTests(Fixtures):
    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_the_inbox_is_the_readers_own_and_drops_a_ringing_call_that_ended(self):
        call = self.play("inbound_answered")
        agent = self.client_for(self.agent)
        # The call is over: its ringing popup is gone from the inbox.
        self.assertEqual(agent.get("/api/v1/telephony/notifications/").data["results"], [])
        Call.objects.filter(pk=call.pk).update(status=Call.Status.ANSWERED)
        items = agent.get("/api/v1/telephony/notifications/").data["results"]
        self.assertEqual([item["kind"] for item in items], ["ringing"])
        self.assertEqual(self.client_for(self.other).get("/api/v1/telephony/notifications/").data["results"], [])
        self.assertEqual(self.client_for(self.other).get(f"/api/v1/telephony/notifications/{items[0]['id']}/").status_code, 404)

    def test_details_follow_the_readers_scope(self):
        self.play("inbound_missed")
        notification = CallNotification.objects.get(user=self.agent, kind="missed")
        detail = self.client_for(self.agent).get(f"/api/v1/telephony/notifications/{notification.pk}/").data
        # The customer is the manager's, outside this marketer's book.
        self.assertIsNone(detail["person"])
        self.assertTrue(detail["known_elsewhere"])
        self.assertEqual(detail["create_customer_url"], "")
        self.assertTrue(detail["can_call_back"])
        # A manager with an extension sees who it is, with the figures they may see.
        Extension.objects.create(integration=self.pbx, number="210", user=self.manager)
        notification.user = self.manager
        notification.save()
        detail = self.client_for(self.manager).get(f"/api/v1/telephony/notifications/{notification.pk}/").data
        self.assertEqual(detail["person"]["name"], "مشتری تلفنی")
        self.assertIn("score", {figure["key"] for figure in detail["person"]["figures"]})

    def test_an_unknown_number_offers_a_new_customer(self):
        call = self.play("inbound_missed")
        Call.objects.filter(pk=call.pk).update(person_type="", person_id=None, external_number="+989127654321")
        Extension.objects.create(integration=self.pbx, number="210", user=self.manager)
        notification = CallNotification.objects.create(user=self.manager, call=call, kind="missed")
        detail = self.client_for(self.manager).get(f"/api/v1/telephony/notifications/{notification.pk}/").data
        self.assertEqual(detail["create_customer_url"], "/customers/?new_phone=%2B989127654321")

    def test_dismissing(self):
        self.play("inbound_missed")
        notification = CallNotification.objects.get(user=self.agent, kind="missed")
        agent = self.client_for(self.agent)
        self.assertEqual(agent.post(f"/api/v1/telephony/notifications/{notification.pk}/dismiss/").status_code, 204)
        self.assertEqual(agent.get("/api/v1/telephony/notifications/").data["results"], [])


class ProfileTests(Fixtures):
    def test_the_customer_timeline_shows_calls_to_whoever_may_see_them(self):
        from profiles.registry import adapter_for

        self.play("inbound_answered")
        kinds = [event["kind"] for event in adapter_for("customer").timeline(self.manager, self.customer)["events"]]
        self.assertIn("pbx_call", kinds)
        self.assertNotIn("pbx_call", [
            event["kind"] for event in adapter_for("customer").timeline(self.other, self.customer)["events"]
        ])

    def test_call_figures_are_the_users_own_or_a_managers(self):
        self.play("inbound_answered")
        self.play("inbound_missed")
        query = {
            "user": self.agent.pk,
            "period_start": (timezone.now() - timedelta(days=1)).isoformat(),
            "period_end": (timezone.now() + timedelta(days=1)).isoformat(),
        }
        own = APIClient()
        own.force_authenticate(self.agent)
        figures = own.get("/api/v1/telephony/stats/", query).data
        self.assertEqual((figures["inbound"], figures["inbound_answered"], figures["missed"]), (2, 1, 1))
        self.assertGreater(figures["talk_seconds"], 0)
        other = APIClient()
        other.force_authenticate(self.other)
        self.assertEqual(other.get("/api/v1/telephony/stats/", query).status_code, 403)
        manager = APIClient()
        manager.force_authenticate(self.manager)
        self.assertEqual(manager.get("/api/v1/telephony/stats/", query).status_code, 200)

    def test_a_missed_call_called_back_counts_as_followed_up(self):
        from telephony.profile import missed_follow_up

        missed = self.play("inbound_missed")
        now = timezone.now()
        Call.objects.filter(pk=missed.pk).update(started_at=now - timedelta(days=2))
        self.assertEqual(missed_follow_up([self.agent.pk], now - timedelta(days=90), now), {self.agent.pk: (0, 1)})
        Call.objects.create(
            integration=self.pbx, linkedid="back-1", direction=Call.Direction.OUTBOUND, status=Call.Status.COMPLETED,
            external_number=missed.external_number, extension="201", user=self.agent,
            started_at=now - timedelta(days=2) + timedelta(hours=1),
        )
        self.assertEqual(missed_follow_up([self.agent.pk], now - timedelta(days=90), now), {self.agent.pk: (1, 1)})
        from scoring.strategies import UserRuleStrategy

        strategy = UserRuleStrategy()
        results = {
            result.key: result
            for result in strategy.evaluate(self.agent, strategy.prepare([self.agent], now=now), now=now)
        }
        self.assertEqual(results["missed_call_follow_up"].ratio, 1.0)

    def test_the_profile_offers_click_to_call_only_from_an_extension(self):
        Integration.objects.filter(pk=self.pbx.pk).update(status=Integration.Status.OK)
        self.client.force_login(self.manager)
        page = self.client.get(f"/customers/{self.customer.pk}/").content.decode()
        self.assertNotIn('data-profile-action="originate"', page)
        self.assertIn('href="tel:+989151234567"', page)
        self.assertNotIn('data-call-popup="1"', page)
        Extension.objects.create(integration=self.pbx, number="210", user=self.manager)
        page = self.client.get(f"/customers/{self.customer.pk}/").content.decode()
        self.assertIn('data-profile-action="originate"', page)
        self.assertIn('data-originate-number="+989151234567"', page)
        self.assertIn('data-call-popup="1"', page)
        # 2.27.0 (product owner): the customer profile's calls tab lists the
        # call-centre records only; the PBX box left it. Click-to-call stays.
        self.assertNotIn('data-pbx-calls="customer"', page)

    def test_a_call_names_its_contact_only_inside_the_readers_scope(self):
        self.play("inbound_answered")
        manager = APIClient()
        manager.force_authenticate(self.manager)
        row = manager.get("/api/v1/calls/").data["results"][0]
        self.assertEqual((row["person_display"], row["person_url"]), ("مشتری تلفنی", f"/customers/{self.customer.pk}/"))
        agent = APIClient()
        agent.force_authenticate(self.agent)
        row = agent.get("/api/v1/calls/").data["results"][0]
        self.assertEqual((row["person_display"], row["person_url"]), ("", ""))

    def test_row_call_buttons_follow_the_readers_own_extension(self):
        Integration.objects.filter(pk=self.pbx.pk).update(status=Integration.Status.OK)
        self.client.force_login(self.agent)
        # The marketer's own profile has no «تماس» of its own, yet their
        # calls list still offers to call each number back.
        self.assertIn('data-can-originate="1"', self.client.get(f"/users/{self.agent.pk}/?tab=calls").content.decode())

    def test_the_user_calls_tab_is_their_own_or_a_managers(self):
        self.client.force_login(self.agent)
        own = self.client.get(f"/users/{self.agent.pk}/?tab=calls").content.decode()
        self.assertIn('data-pbx-calls="user"', own)
        self.assertIn("داخلی ۲۰۱", own)
        self.client.force_login(self.manager)
        self.assertIn('data-pbx-calls="user"', self.client.get(f"/users/{self.agent.pk}/?tab=calls").content.decode())


@override_settings(DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS=True)
class OriginateEndToEndTests(TransactionTestCase):
    """The web queues a call, the listener sends it to the fake PBX."""

    def setUp(self):
        cache.clear()
        self.server = FakeAMIServer().start()
        self.admin = User.objects.create_user(username="oe.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="oe.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.agent, full_name="مشتری کلیک", phone={"raw_phone": "09151234567", "is_primary": True}
        )
        self.pbx = create_integration(
            actor=self.admin, provider_key="asterisk", name="PBX",
            config=asterisk_config(port=self.server.port, originate_caller_id="Dolphin <201>"),
            secrets={"ami_password": "amipass"}, enabled=True,
        )
        Extension.objects.create(integration=self.pbx, number="201", user=self.agent)

    def tearDown(self):
        self.server.stop()
        cache.clear()

    def test_a_queued_call_is_sent_on_the_live_session(self):
        from telephony.services import request_originate
        from telephony.worker import _close_connections, _listen

        # Queued before the listener starts, as the web would: the test then
        # only reads while the listener writes (SQLite, unlike PostgreSQL,
        # refuses a second concurrent writer outright).
        Integration.objects.filter(pk=self.pbx.pk).update(status=Integration.Status.OK)
        request_id = request_originate(
            actor=self.agent, number="09151234567", person_type="customer", person_id=self.customer.pk
        ).pk

        async def scenario():
            stop = asyncio.Event()
            probe = ThreadPoolExecutor(max_workers=1)
            loop = asyncio.get_running_loop()
            task = asyncio.create_task(_listen(self.pbx, stop))
            await loop.run_in_executor(None, self.server.logged_in.wait, 5)
            for _ in range(60):
                status = await loop.run_in_executor(
                    probe, lambda: OriginateRequest.objects.values_list("status", flat=True).get(pk=request_id)
                )
                if status == "sent":
                    break
                await asyncio.sleep(0.1)
            stop.set()
            await asyncio.wait_for(task, 10)
            await loop.run_in_executor(probe, _close_connections)
            probe.shutdown(wait=True)

        asyncio.run(scenario())
        request = OriginateRequest.objects.select_related("call").get(pk=request_id)
        self.assertEqual(request.status, "sent")
        sent = self.server.originates[0]
        self.assertEqual(sent["Channel"], "Local/201@from-internal")
        self.assertEqual((sent["Exten"], sent["Context"], sent["CallerID"]), ("909151234567", "from-internal", "Dolphin <201>"))
        self.assertEqual(sent["ChannelId"], request.call.linkedid)
        self.assertEqual((request.call.direction, request.call.person_id), ("outbound", self.customer.pk))
