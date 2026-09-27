"""From AMI events to `Call` rows (2.22.0).

Asterisk describes one call as several channels that share a `Linkedid` (the
`Uniqueid` of the call's first channel). The tracker keeps, per `Linkedid`,
which channels are still up, who was rung, whether the far party answered —
and writes the `Call` row as that changes:

* `Newchannel` — the first channel of a new `Linkedid` opens a call
  (`ringing`); its caller and dialled number decide the direction.
* `DialBegin` / `AgentCalled` — an extension is being rung (inbound, queues).
* `DialEnd` with `DialStatus: ANSWER`, or a two-party `BridgeEnter` — the far
  party answered (for inbound, an extension; for outbound, the outside line).
* `Hangup` of the last channel — the call ended; its final status follows
  from what happened (`completed`, `missed`, `no_answer`, `busy`, `failed`).

A call placed from Dolphin (click-to-call) is created first, with the
`ChannelId` Dolphin gives the originate action as its `Linkedid`, so every
event of it lands on that row.

Unknown or malformed events are ignored; a restart loses only in-memory
channel bookkeeping — the CDR sync corrects any call the listener could not
finish.
"""

import logging
import re

from django.db import transaction
from django.utils import timezone

from integrations.events import emit
from integrations.matching import best_match, normalize_caller
from telephony.models import Call, Extension

logger = logging.getLogger("dolphin.telephony.tracker")

_CHANNEL_PEER = re.compile(r"^(?:PJSIP|SIP|IAX2|DAHDI|Local)/([^@;/-]+)")
FAR_DIAL_STATUS = {
    "BUSY": Call.Status.BUSY,
    "CONGESTION": Call.Status.FAILED,
    "CHANUNAVAIL": Call.Status.FAILED,
}
RAW_EVENT_KEYS = ("Event", "Channel", "DestChannel", "CallerIDNum", "ConnectedLineNum", "Exten", "DialStatus", "Cause", "Cause-txt")
RAW_LIMIT = 12


def channel_peer(channel):
    """`PJSIP/201-0000002a` → `201`; `PJSIP/trunk-00000005` → `trunk`."""
    match = _CHANNEL_PEER.match(channel or "")
    return match.group(1) if match else ""


class CallTracker:
    def __init__(self, integration, *, clock=None):
        self.integration_id = integration.pk
        config = integration.config or {}
        self.max_internal = int(config.get("internal_extension_max_length") or 5)
        self.outbound_prefix = str(config.get("outbound_prefix") or "")
        self.clock = clock or timezone.now
        self.calls = {}  # linkedid -> in-memory state
        self._extensions = None

    # --- lookups ---------------------------------------------------------------

    def extensions(self):
        if self._extensions is None:
            self._extensions = {
                row.number: row.user_id
                for row in Extension.objects.filter(integration_id=self.integration_id, active=True)
            }
        return self._extensions

    def refresh_extensions(self):
        self._extensions = None

    def is_internal(self, number):
        number = str(number or "")
        if number in self.extensions():
            return True
        return number.isdigit() and 0 < len(number) <= self.max_internal

    def strip_prefix(self, number):
        number = str(number or "")
        if self.outbound_prefix and number.startswith(self.outbound_prefix) and not self.is_internal(number):
            return number[len(self.outbound_prefix):]
        return number

    # --- event entry point -------------------------------------------------------

    def handle(self, event):
        name = event.get("Event")
        linkedid = event.get("Linkedid") or event.get("Uniqueid")
        if not name or not linkedid:
            return None
        handler = {
            "Newchannel": self._new_channel,
            "DialBegin": self._dial_begin,
            "AgentCalled": self._dial_begin,
            "DialEnd": self._dial_end,
            "BridgeEnter": self._bridge_enter,
            "Hangup": self._hangup,
        }.get(name)
        if handler is None:
            return None
        try:
            with transaction.atomic():
                return handler(linkedid, event)
        except Exception:  # noqa: BLE001 — one bad event never stops the listener
            logger.exception("telephony tracker failed on %s", name)
            return None

    def _state(self, linkedid):
        return self.calls.setdefault(linkedid, {"live": set(), "answered": False, "dial_status": "", "rung": []})

    def _remember(self, call, event):
        entries = list((call.raw or {}).get("events", []))
        entries.append({key: event[key] for key in RAW_EVENT_KEYS if key in event})
        call.raw = {"events": entries[-RAW_LIMIT:]}

    def _call(self, linkedid):
        return (
            Call.objects.select_for_update()
            .filter(integration_id=self.integration_id, linkedid=linkedid)
            .first()
        )

    # --- handlers ------------------------------------------------------------------

    def _new_channel(self, linkedid, event):
        state = self._state(linkedid)
        state["live"].add(event.get("Uniqueid") or linkedid)
        call = self._call(linkedid)
        if call is not None:
            if not call.seen_by_ami:
                call.seen_by_ami = True
                self._remember(call, event)
                call.save(update_fields=["seen_by_ami", "raw", "updated_at"])
            return call
        caller = event.get("CallerIDNum") or ""
        dialled = self.strip_prefix(event.get("Exten") or "")
        caller_internal = self.is_internal(caller)
        if caller_internal and self.is_internal(dialled):
            direction, external_raw, extension = Call.Direction.INTERNAL, "", caller
        elif caller_internal:
            direction, external_raw, extension = Call.Direction.OUTBOUND, dialled, caller
        else:
            direction, external_raw, extension = Call.Direction.INBOUND, caller, ""
        external = normalize_caller(external_raw) if external_raw else ""
        match = best_match(external_raw) if external_raw else None
        call = Call(
            integration_id=self.integration_id,
            linkedid=linkedid,
            direction=direction,
            caller_raw=caller[:64],
            callee_raw=dialled[:64],
            external_number=external,
            extension=extension[:20],
            user_id=self.extensions().get(extension) if extension else None,
            person_type=match.person_type if match else "",
            person_id=match.person_id if match else None,
            started_at=self.clock(),
            seen_by_ami=True,
        )
        self._remember(call, event)
        call.save()
        emit("call.started", self.payload(call), person_type=call.person_type, person_id=call.person_id, dedupe_key=f"call:{call.pk}:started")
        return call

    def _dial_begin(self, linkedid, event):
        call = self._call(linkedid)
        if call is None:
            return None
        state = self._state(linkedid)
        target = event.get("DestCallerIDNum") or channel_peer(event.get("DestChannel") or event.get("Interface") or "")
        if self.is_internal(target):
            if target not in state["rung"]:
                state["rung"].append(target)
            if call.direction == Call.Direction.INBOUND and not call.extension:
                call.extension = target[:20]
                call.user_id = self.extensions().get(target)
            self._remember(call, event)
            call.save(update_fields=["extension", "user", "raw", "updated_at"])
            from telephony.signals import call_ringing

            user_id = self.extensions().get(target)
            if user_id and call.direction == Call.Direction.INBOUND:
                transaction.on_commit(lambda: call_ringing.send(sender=CallTracker, call=call, user_id=user_id))
        return call

    def _is_far_party(self, call, destination):
        internal = self.is_internal(destination)
        if call.direction == Call.Direction.OUTBOUND:
            return not internal
        return internal

    def _answer(self, call, event, extension=""):
        state = self._state(call.linkedid)
        if state["answered"] or call.answered_at:
            state["answered"] = True
            return
        state["answered"] = True
        call.answered_at = self.clock()
        call.status = Call.Status.ANSWERED
        if extension and call.direction == Call.Direction.INBOUND:
            call.extension = extension[:20]
            call.user_id = self.extensions().get(extension) or call.user_id
        self._remember(call, event)
        call.save()
        emit("call.answered", self.payload(call), person_type=call.person_type, person_id=call.person_id, dedupe_key=f"call:{call.pk}:answered")

    def _dial_end(self, linkedid, event):
        call = self._call(linkedid)
        if call is None:
            return None
        destination = event.get("DestCallerIDNum") or channel_peer(event.get("DestChannel") or "")
        status = (event.get("DialStatus") or "").upper()
        if status == "ANSWER" and self._is_far_party(call, destination):
            self._answer(call, event, destination if self.is_internal(destination) else "")
        elif status:
            self._state(linkedid)["dial_status"] = status
        return call

    def _bridge_enter(self, linkedid, event):
        call = self._call(linkedid)
        if call is None:
            return None
        try:
            members = int(event.get("BridgeNumChannels") or 0)
        except ValueError:
            members = 0
        if members >= 2:
            peer = channel_peer(event.get("Channel") or "")
            self._answer(call, event, peer if self.is_internal(peer) else "")
        return call

    def _hangup(self, linkedid, event):
        state = self._state(linkedid)
        state["live"].discard(event.get("Uniqueid") or linkedid)
        call = self._call(linkedid)
        if call is None:
            if not state["live"]:
                self.calls.pop(linkedid, None)
            return None
        self._remember(call, event)
        if state["live"]:
            call.save(update_fields=["raw", "updated_at"])
            return call
        # The last channel went: the call is over.
        now = self.clock()
        call.ended_at = now
        call.duration = max(0, int((now - call.started_at).total_seconds()))
        call.hangup_cause = (event.get("Cause-txt") or event.get("Cause") or "")[:80]
        if call.answered_at:
            call.status = Call.Status.COMPLETED
            call.billsec = max(0, int((now - call.answered_at).total_seconds()))
        elif call.direction == Call.Direction.INBOUND:
            call.status = Call.Status.MISSED
        else:
            call.status = FAR_DIAL_STATUS.get(state["dial_status"], Call.Status.NO_ANSWER)
        call.save()
        self.calls.pop(linkedid, None)
        payload = self.payload(call)
        emit("call.ended", payload, person_type=call.person_type, person_id=call.person_id, dedupe_key=f"call:{call.pk}:ended")
        if call.status == Call.Status.MISSED:
            emit(
                "call.missed", {**payload, "rung_extensions": state["rung"]},
                person_type=call.person_type, person_id=call.person_id, dedupe_key=f"call:{call.pk}:missed",
            )
        return call

    @staticmethod
    def payload(call):
        return {
            "call": call.pk,
            "integration": call.integration_id,
            "direction": call.direction,
            "status": call.status,
            "external_number": call.external_number,
            "extension": call.extension,
            "user": call.user_id,
            "started_at": call.started_at.isoformat() if call.started_at else None,
            "answered_at": call.answered_at.isoformat() if call.answered_at else None,
            "ended_at": call.ended_at.isoformat() if call.ended_at else None,
            "duration": call.duration,
            "billsec": call.billsec,
        }
