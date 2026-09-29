"""Writes `CallEvent`s from a webhook-connected PBX into `Call` rows (2.30.0).

The same rules as the Asterisk listener: a call is keyed by (connection, PBX
call id), the party outside the PBX is matched to a customer or colleague,
domain events are emitted once per stage, and the popup signal fires for the
extension that rings. A call that already finished never goes back to an open
state, and a repeated event is harmless.
"""

import re

from django.db import transaction
from django.utils import timezone

from integrations.events import emit
from integrations.matching import best_match, normalize_caller
from telephony.models import Call
from telephony.tracker import CallTracker

_NUMBER = re.compile(r"<([0-9+*#]+)>|([0-9+*#]{2,})")
_STATUS = {
    "busy": Call.Status.BUSY,
    "failed": Call.Status.FAILED,
    "no_answer": Call.Status.NO_ANSWER,
    "voicemail": Call.Status.NO_ANSWER,
    "abandoned": Call.Status.MISSED,
}


def clean_number(text):
    """`Ali <201>` or `201 Ali` -> `201`; a bare number is returned as is."""
    text = str(text or "").strip()
    match = _NUMBER.search(text)
    return (match.group(1) or match.group(2)) if match else text[:64]


def _parties(tracker, ev):
    caller, callee = clean_number(ev.caller), tracker.strip_prefix(clean_number(ev.callee))
    direction = ev.direction
    if not direction:
        if tracker.is_internal(caller) and tracker.is_internal(callee):
            direction = Call.Direction.INTERNAL
        elif tracker.is_internal(caller):
            direction = Call.Direction.OUTBOUND
        else:
            direction = Call.Direction.INBOUND
    if direction == Call.Direction.OUTBOUND:
        external_raw, extension = callee, ev.extension or caller
    elif direction == Call.Direction.INBOUND:
        external_raw = caller
        extension = ev.extension or (callee if tracker.is_internal(callee) else "")
    else:
        external_raw, extension = "", ev.extension or caller
    return direction, caller, callee, external_raw, extension


def _open(integration, tracker, ev):
    direction, caller, callee, external_raw, extension = _parties(tracker, ev)
    external = normalize_caller(external_raw) if external_raw else ""
    match = best_match(external_raw) if external_raw else None
    call = Call(
        integration=integration, linkedid=ev.call_id[:64], direction=direction,
        caller_raw=caller[:64], callee_raw=callee[:64], external_number=external,
        extension=extension[:20], user_id=tracker.extensions().get(extension) if extension else None,
        person_type=match.person_type if match else "", person_id=match.person_id if match else None,
        started_at=ev.started_at or timezone.now(),
    )
    call.save()
    emit("call.started", CallTracker.payload(call), person_type=call.person_type, person_id=call.person_id,
         dedupe_key=f"call:{call.pk}:started")
    return call


def _ring(call, tracker, ev):
    from telephony.signals import call_ringing

    if call.direction != Call.Direction.INBOUND:
        return
    targets = list(ev.rung) or ([ev.extension] if ev.extension else [])
    for number in targets:
        user_id = tracker.extensions().get(number)
        if user_id:
            transaction.on_commit(lambda uid=user_id: call_ringing.send(sender=CallTracker, call=call, user_id=uid))
    if targets and not call.extension:
        call.extension = targets[0][:20]
        call.user_id = tracker.extensions().get(targets[0])
        call.save(update_fields=["extension", "user", "updated_at"])


def _remember(call, ev):
    entries = list((call.raw or {}).get("events", []))
    entries.append({"stage": ev.stage, "status": ev.disposition, "cause": ev.cause})
    call.raw = {"events": entries[-12:]}


def apply_event(integration, tracker, ev):
    """Apply one event; returns the `Call`."""
    with transaction.atomic():
        call = Call.objects.select_for_update().filter(integration=integration, linkedid=ev.call_id[:64]).first()
        if call is None:
            call = _open(integration, tracker, ev)
        finished = call.status not in Call.OPEN_STATUSES
        if ev.stage == "ringing":
            if not finished:
                _ring(call, tracker, ev)
        elif ev.stage == "answered":
            if not finished and not call.answered_at:
                call.answered_at = timezone.now()
                call.status = Call.Status.ANSWERED
                if ev.extension and call.direction == Call.Direction.INBOUND:
                    call.extension = ev.extension[:20]
                    call.user_id = tracker.extensions().get(ev.extension) or call.user_id
                _remember(call, ev)
                call.save()
                emit("call.answered", CallTracker.payload(call), person_type=call.person_type,
                     person_id=call.person_id, dedupe_key=f"call:{call.pk}:answered")
        else:
            _finish(call, ev, finished)
        return call


def _finish(call, ev, was_finished):
    if ev.started_at and (call.started_at is None or ev.started_at < call.started_at):
        call.started_at = ev.started_at
    if ev.disposition == "answered" or ev.billsec > 0:
        status = Call.Status.COMPLETED
    elif call.direction == Call.Direction.INBOUND:
        status = Call.Status.MISSED
    else:
        status = _STATUS.get(ev.disposition, Call.Status.NO_ANSWER)
        if status == Call.Status.MISSED:
            status = Call.Status.NO_ANSWER
    call.status = status
    call.answered_at = ev.answered_at or call.answered_at
    call.ended_at = ev.ended_at or call.ended_at or timezone.now()
    call.duration, call.billsec = ev.duration, ev.billsec
    call.hangup_cause = (ev.cause or ev.disposition)[:80]
    if ev.recording:
        call.recording = ev.recording[:500]
    call.seen_in_cdr = True
    _remember(call, ev)
    call.save()
    if was_finished:
        return
    payload = CallTracker.payload(call)
    emit("call.ended", payload, person_type=call.person_type, person_id=call.person_id, dedupe_key=f"call:{call.pk}:ended")
    if call.status == Call.Status.MISSED:
        rung = list(ev.rung) or ([call.extension] if call.extension else [])
        emit("call.missed", {**payload, "rung_extensions": rung}, person_type=call.person_type,
             person_id=call.person_id, dedupe_key=f"call:{call.pk}:missed")
