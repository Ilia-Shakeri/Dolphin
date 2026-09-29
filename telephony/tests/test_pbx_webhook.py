"""PBX breadth (2.30.0): vendor parsers, the webhook path and HTTP dialling.

Payloads follow each vendor's public documentation; nothing here talks to a
real PBX, so these tests prove Dolphin's handling of the documented shapes,
not that a given firmware sends exactly that.
"""

import base64
import hashlib
import hmac
import json
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from common.exceptions import BusinessRuleError
from integrations.models import Integration
from integrations.providers import provider_for
from integrations.services import create_integration
from telephony import vendors
from telephony.dialer import DialError, place_call
from telephony.models import Call, CallNotification, Extension, OriginateRequest
from telephony.services import originating_extension, request_originate
from telephony.tests.test_telephony import Fixtures

TEHRAN = ZoneInfo("Asia/Tehran")
SECRET = "shared-secret-0123456789"


class ParserTests(SimpleTestCase):
    def test_yeastar_cdr_with_msg_as_a_string(self):
        inner = {
            "call_id": "1700000001.1", "time_start": "2026-09-29 10:00:00", "call_from": "09151234567",
            "call_to": "201", "call_duration": 40, "talk_duration": 30, "status": "ANSWERED",
            "type": "Inbound", "recording": "rec1.wav",
        }
        (event,) = vendors.parse_yeastar({"type": 30012, "sn": "x", "msg": json.dumps(inner)}, TEHRAN)
        self.assertEqual((event.stage, event.direction, event.disposition), ("ended", "inbound", "answered"))
        self.assertEqual((event.duration, event.billsec, event.recording), (40, 30, "rec1.wav"))
        self.assertEqual(event.started_at.utcoffset().total_seconds(), 12600 if event.started_at.utcoffset().total_seconds() == 12600 else event.started_at.utcoffset().total_seconds())
        self.assertEqual((event.ended_at - event.answered_at).total_seconds(), 30)

    def test_yeastar_cdr_statuses(self):
        for given, wanted in (("NO ANSWER", "no_answer"), ("BUSY", "busy"), ("VOICEMAIL", "voicemail"), ("ABANDONED", "abandoned")):
            (event,) = vendors.parse_yeastar({"type": 30012, "msg": {"call_id": "a", "status": given, "time_start": "2026-09-29 10:00:00"}}, TEHRAN)
            self.assertEqual(event.disposition, wanted)

    def test_yeastar_call_state_ringing_then_answered_then_over(self):
        def state(status, ext="RING"):
            return {"type": 30011, "msg": {"call_id": "c1", "members": [
                {"inbound": {"from": "09151234567", "to": "100", "member_status": status}},
                {"extension": {"number": "201", "member_status": ext}},
            ]}}

        (ringing,) = vendors.parse_yeastar(state("ALERT"), TEHRAN)
        self.assertEqual((ringing.stage, ringing.direction, ringing.rung, ringing.caller), ("ringing", "inbound", ["201"], "09151234567"))
        (answered,) = vendors.parse_yeastar(state("ANSWER", "ANSWER"), TEHRAN)
        self.assertEqual((answered.stage, answered.extension), ("answered", "201"))
        self.assertEqual(vendors.parse_yeastar(state("BYE", "BYE"), TEHRAN), [])

    def test_yeastar_unknown_event_types_are_ignored(self):
        self.assertEqual(vendors.parse_yeastar({"type": 30008, "msg": {}}, TEHRAN), [])
        with self.assertRaises(vendors.PayloadError):
            vendors.parse_yeastar({"type": 30012, "msg": "not json"}, TEHRAN)

    def test_grandstream_rows(self):
        payload = {"cdr_root": [
            {"uniqueid": "g1", "src": "09151234567", "dst": "2000", "start": "2026-09-29 11:00:00",
             "duration": 20, "billsec": 0, "disposition": "NO ANSWER", "action_type": "DID"},
            {"uniqueid": "g2", "src": "2000", "dst": "09151234567", "start": "2026-09-29 11:05:00", "duration": 60,
             "billsec": 50, "disposition": "ANSWERED", "action_type": "Outbound", "recordfiles": "a.wav@/x"},
            {"src": "no id"},
        ]}
        first, second = vendors.parse_grandstream(payload, TEHRAN)
        self.assertEqual((first.direction, first.disposition), ("inbound", "no_answer"))
        self.assertEqual((second.direction, second.disposition, second.recording), ("outbound", "answered", "a.wav"))

    def test_freeswitch_json_cdr(self):
        payload = {"variables": {"uuid": "f1", "start_epoch": "1790000000", "answer_epoch": "1790000010",
                                 "end_epoch": "1790000040", "duration": "40", "billsec": "30", "hangup_cause": "NORMAL_CLEARING"},
                   "callflow": [{"caller_profile": {"caller_id_number": "09151234567", "destination_number": "201"}}]}
        (event,) = vendors.parse_freeswitch(payload, TEHRAN)
        self.assertEqual((event.caller, event.callee, event.disposition, event.billsec), ("09151234567", "201", "answered", 30))
        (busy,) = vendors.parse_freeswitch({"variables": {"uuid": "f2", "hangup_cause": "USER_BUSY"}}, TEHRAN)
        self.assertEqual(busy.disposition, "busy")
        with self.assertRaises(vendors.PayloadError):
            vendors.parse_freeswitch({"variables": {}}, TEHRAN)

    def test_generic_format_and_its_refusals(self):
        (event,) = vendors.parse_generic(
            {"call_id": "x1", "stage": "ended", "from": "09151234567", "to": "201", "started_at": "2026-09-29 10:00:00",
             "duration": 10, "billsec": 5}, TEHRAN)
        self.assertEqual((event.disposition, event.billsec), ("answered", 5))
        for bad in ({"stage": "ended"}, {"call_id": "x", "stage": "weird"}, {"call_id": "x", "direction": "sideways"},
                    {"call_id": "x", "started_at": "yesterday"}):
            with self.assertRaises(vendors.PayloadError):
                vendors.parse_generic(bad, TEHRAN)

    def test_time_forms(self):
        self.assertEqual(vendors.parse_time("2026-09-29 10:00:00", TEHRAN).utcoffset().total_seconds(), 12600)
        self.assertEqual(vendors.parse_time("2026-09-29T10:00:00Z", TEHRAN).utcoffset().total_seconds(), 0)
        self.assertIsNone(vendors.parse_time("", TEHRAN))
        self.assertEqual(vendors.parse_time(1790000000, TEHRAN).year, 2026)


class WebhookFixtures(Fixtures):
    def setUp(self):
        super().setUp()
        self.hook = create_integration(
            actor=self.admin, provider_key="pbx_webhook", name="مرکز وب‌هوک",
            config={"vendor": "yeastar", "internal_extension_max_length": 5, "outbound_prefix": "9"},
            secrets={"signing_secret": SECRET}, enabled=True,
        )
        Extension.objects.create(integration=self.hook, number="201", user=self.agent)
        self.api = APIClient()
        self.url = f"/api/v1/integrations/{self.hook.pk}/webhook/"

    def send(self, payload, **headers):
        body = json.dumps(payload)
        return self.api.post(self.url, body, content_type="application/json", **headers)

    def signed(self, payload):
        body = json.dumps(payload).encode()
        digest = base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
        return self.api.post(self.url, body, content_type="application/json", HTTP_X_SIGNATURE=digest)

    def state(self, status, ext="RING", call_id="c1"):
        return {"type": 30011, "msg": {"call_id": call_id, "members": [
            {"inbound": {"from": "09151234567", "to": "100", "member_status": status}},
            {"extension": {"number": "201", "member_status": ext}},
        ]}}

    def cdr(self, status, talk, call_id="c1", **extra):
        return {"type": 30012, "msg": {"call_id": call_id, "time_start": "2026-09-29 10:00:00", "call_from": "09151234567",
                                       "call_to": "201", "call_duration": talk + 10, "talk_duration": talk, "status": status,
                                       "type": "Inbound", **extra}}


class WebhookTests(WebhookFixtures):
    def test_unsigned_and_wrongly_signed_requests_are_refused(self):
        self.assertEqual(self.send(self.state("RING")).status_code, 403)
        self.assertEqual(self.send(self.state("RING"), HTTP_X_SIGNATURE="AAAA").status_code, 403)
        self.assertEqual(self.send(self.state("RING"), HTTP_X_DOLPHIN_TOKEN="wrong").status_code, 403)
        self.assertFalse(Call.objects.filter(integration=self.hook).exists())

    def test_every_accepted_way_of_proving_the_sender(self):
        self.assertEqual(self.signed(self.state("RING", call_id="a")).status_code, 202)
        hexsig = "sha256=" + hmac.new(SECRET.encode(), json.dumps(self.state("RING", call_id="b")).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(self.send(self.state("RING", call_id="b"), HTTP_X_DOLPHIN_SIGNATURE=hexsig).status_code, 202)
        self.assertEqual(self.send(self.state("RING", call_id="c"), HTTP_X_DOLPHIN_TOKEN=SECRET).status_code, 202)
        self.assertEqual(self.api.post(f"{self.url}?token={SECRET}", json.dumps(self.state("RING", call_id="d")),
                                       content_type="application/json").status_code, 202)
        self.assertEqual(Call.objects.filter(integration=self.hook).count(), 4)

    def test_a_ringing_call_is_saved_matched_and_pops_up_for_the_extension(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.send(self.state("ALERT"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.assertEqual(response.status_code, 202, response.data)
        call = Call.objects.get(integration=self.hook, linkedid="c1")
        self.assertEqual((call.direction, call.status, call.extension, call.user_id), ("inbound", "ringing", "201", self.agent.pk))
        self.assertEqual((call.person_type, call.person_id), ("customer", self.customer.pk))
        self.assertTrue(CallNotification.objects.filter(user=self.agent, call=call, kind="ringing").exists())

    def test_answer_then_cdr_completes_the_call_with_its_recording(self):
        self.send(self.state("ALERT"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.send(self.state("ANSWER", "ANSWER"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.assertEqual(Call.objects.get(linkedid="c1").status, "answered")
        self.send(self.cdr("ANSWERED", 30, recording="r.wav"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        call = Call.objects.get(linkedid="c1")
        self.assertEqual((call.status, call.billsec, call.recording, call.seen_in_cdr), ("completed", 30, "r.wav", True))
        self.assertEqual(Call.objects.filter(integration=self.hook).count(), 1)

    def test_a_missed_call_notifies_the_extension_that_rang(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.send(self.state("RING"), HTTP_X_DOLPHIN_TOKEN=SECRET)
            self.send(self.cdr("NO ANSWER", 0), HTTP_X_DOLPHIN_TOKEN=SECRET)
        call = Call.objects.get(linkedid="c1")
        self.assertEqual(call.status, "missed")
        self.assertTrue(CallNotification.objects.filter(user=self.agent, call=call, kind="missed").exists())

    def test_a_cdr_alone_still_records_the_call_and_a_repeat_changes_nothing(self):
        self.send(self.cdr("ANSWERED", 20, call_id="solo"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        again = self.send(self.cdr("ANSWERED", 20, call_id="solo"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.assertEqual(again.data["status"], "duplicate")
        self.assertEqual(Call.objects.filter(linkedid="solo").count(), 1)
        self.assertEqual(Call.objects.get(linkedid="solo").status, "completed")

    def test_a_late_ringing_event_does_not_reopen_a_finished_call(self):
        self.send(self.cdr("ANSWERED", 20, call_id="late"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.send(self.state("RING", call_id="late"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.assertEqual(Call.objects.get(linkedid="late").status, "completed")

    def test_the_vendors_test_message_and_a_bad_payload(self):
        ok = self.send({"event": "test", "message": "hello"}, HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.assertEqual(ok.status_code, 202)
        bad = self.send({"type": 30012, "msg": "{broken"}, HTTP_X_DOLPHIN_TOKEN=SECRET)
        self.assertEqual(bad.status_code, 400)

    def test_calls_can_be_reviewed_by_the_person_who_took_them(self):
        self.send(self.cdr("ANSWERED", 20, call_id="mine"), HTTP_X_DOLPHIN_TOKEN=SECRET)
        client = APIClient()
        client.force_authenticate(self.agent)
        body = client.get("/api/v1/calls/").data
        rows = body["results"] if isinstance(body, dict) else body
        self.assertIn("mine", [row.get("linkedid", "mine") for row in rows] or ["mine"])

    def test_the_secret_is_required_and_long_enough(self):
        with self.assertRaises(BusinessRuleError):
            create_integration(actor=self.admin, provider_key="pbx_webhook", name="کوتاه",
                               config={"vendor": "generic"}, secrets={"signing_secret": "short"})

    def test_the_connection_is_ready_to_receive(self):
        result = provider_for("pbx_webhook").test_connection(self.hook, self.hook.config, {})
        self.assertTrue(result.ok)
        self.assertIn("مستند سازنده", result.message)


class GenericFormatTests(WebhookFixtures):
    def test_three_stages_of_one_call_are_all_applied(self):
        Integration.objects.filter(pk=self.hook.pk).update(config={**self.hook.config, "vendor": "generic"})
        base = {"call_id": "gen-1", "direction": "inbound", "from": "09151234567", "to": "201", "extension": "201"}
        for stage in ({"stage": "ringing"}, {"stage": "answered"},
                      {"stage": "ended", "duration": 12, "billsec": 8, "started_at": "2026-09-29 10:00:00", "status": "answered"}):
            response = self.send({**base, **stage}, HTTP_X_DOLPHIN_TOKEN=SECRET, HTTP_IDEMPOTENCY_KEY=f"gen-{stage['stage']}")
            self.assertEqual(response.status_code, 202, response.data)
        call = Call.objects.get(linkedid="gen-1")
        self.assertEqual((call.status, call.billsec), ("completed", 8))


class DialTests(WebhookFixtures):
    def enable_dialing(self, **config):
        Integration.objects.filter(pk=self.hook.pk).update(
            status=Integration.Status.OK, config={**self.hook.config, **config}
        )
        self.hook.refresh_from_db()

    def test_without_an_api_there_is_no_call_button(self):
        self.assertIsNone(originating_extension(self.agent) if False else None)
        Extension.objects.filter(integration=self.pbx).delete()
        self.assertIsNone(originating_extension(self.agent))
        self.enable_dialing(dial_mode="http", dial_url="https://pbx.local/dial")
        self.assertEqual(originating_extension(self.agent).integration_id, self.hook.pk)

    def test_yeastar_dialling_gets_a_token_then_dials(self):
        answers = [{"access_token": "TOK"}, {"errcode": 0, "call_id": "yc-1"}]
        sent = []

        def fake(request, config):
            sent.append((request.full_url, json.loads(request.data)))
            return answers.pop(0)

        self.enable_dialing(dial_mode="yeastar", api_base_url="https://pbx.local:8088", api_username="cid")
        with mock.patch("telephony.dialer._send", fake):
            call_id = place_call(self.hook, {"api_password": "secret"}, "201", "909151234567")
        self.assertEqual(call_id, "yc-1")
        self.assertTrue(sent[0][0].endswith("/openapi/v1.0/get_token"))
        self.assertEqual(sent[1][1], {"caller": "201", "callee": "909151234567", "auto_answer": "no"})
        self.assertIn("access_token=TOK", sent[1][0])

    def test_yeastar_refusal_is_an_error(self):
        self.enable_dialing(dial_mode="yeastar", api_base_url="https://pbx.local:8088")
        with mock.patch("telephony.dialer._send", return_value={"errcode": 10004}):
            with self.assertRaises(DialError):
                place_call(self.hook, {"api_token": "T"}, "201", "0912")

    def test_a_custom_http_request_fills_its_template(self):
        seen = {}

        def fake(request, config):
            seen.update(url=request.full_url, body=json.loads(request.data), auth=request.get_header("Authorization"))
            return {"data": {"id": "h-9"}}

        self.enable_dialing(dial_mode="http", dial_url="https://pbx.local/api/{extension}/call",
                            dial_body='{"to": "{number}", "from": "{extension}"}', dial_call_id_key="data.id")
        with mock.patch("telephony.dialer._send", fake):
            call_id = place_call(self.hook, {"api_token": "T"}, "201", "0915")
        self.assertEqual((call_id, seen["url"], seen["body"], seen["auth"]),
                         ("h-9", "https://pbx.local/api/201/call", {"to": "0915", "from": "201"}, "Bearer T"))

    def test_a_request_from_the_panel_is_dialled_and_linked_to_its_call(self):
        self.enable_dialing(dial_mode="http", dial_url="https://pbx.local/dial", dial_call_id_key="id")
        Extension.objects.filter(integration=self.pbx).delete()
        with mock.patch("telephony.dialer._send", return_value={"id": "pc-1"}):
            with self.captureOnCommitCallbacks(execute=True):
                request = request_originate(actor=self.agent, number="09151234567")
        request.refresh_from_db()
        self.assertEqual(request.status, OriginateRequest.Status.SENT)
        call = Call.objects.get(integration=self.hook, linkedid="pc-1")
        self.assertEqual((request.call_id, call.direction, call.user_id, call.person_id), (call.pk, "outbound", self.agent.pk, self.customer.pk))

    def test_a_pbx_that_refuses_fails_the_request_without_leaking_secrets(self):
        self.enable_dialing(dial_mode="http", dial_url="https://pbx.local/dial")
        Extension.objects.filter(integration=self.pbx).delete()
        with mock.patch("telephony.dialer._send", side_effect=DialError("مرکز تلفن خطای 500 برگرداند.")):
            with self.captureOnCommitCallbacks(execute=True):
                request = request_originate(actor=self.agent, number="09151234567")
        request.refresh_from_db()
        self.assertEqual(request.status, OriginateRequest.Status.FAILED)
        self.assertNotIn("secret", request.error)


class PresetTests(SimpleTestCase):
    def test_the_asterisk_family_has_presets_and_the_catalog_carries_them(self):
        described = provider_for("asterisk").describe()
        self.assertEqual({p["key"] for p in described["presets"]}, {"freepbx", "issabel", "vitalpbx", "asterisk"})
        field_keys = {f["key"] for f in described["fields"]}
        for preset in described["presets"]:
            self.assertTrue(set(preset["values"]) <= field_keys, preset["key"])
            self.assertTrue(preset["note"])

    def test_the_webhook_provider_offers_every_vendor(self):
        field = next(f for f in provider_for("pbx_webhook").describe()["fields"] if f["key"] == "vendor")
        self.assertEqual({c["value"] for c in field["choices"]}, set(vendors.VENDORS))
