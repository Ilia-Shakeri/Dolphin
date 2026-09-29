"""What each PBX family sends, turned into one shape (2.30.0).

A PBX that can push call events over HTTP (a webhook, a CDR export, a script)
reaches Dolphin through the `pbx_webhook` connection. Each family words its
events differently, so a *vendor* here is one small function that reads that
family's JSON and returns `CallEvent`s; `telephony.ingest` then writes them
with the same rules the Asterisk listener uses (matching, popups, missed-call
tasks, domain events).

Formats follow the vendors' public documentation. `VERIFIED` names the ones
checked against a real system; the rest are documented-format only and the
connection guide says so.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as dt_timezone

STAGES = ("ringing", "answered", "ended")
DISPOSITIONS = ("answered", "no_answer", "busy", "failed", "voicemail", "abandoned")
VERIFIED = frozenset()


@dataclass
class CallEvent:
    call_id: str
    stage: str
    direction: str = ""  # inbound | outbound | internal | "" (decided from the numbers)
    caller: str = ""
    callee: str = ""
    extension: str = ""
    rung: list = field(default_factory=list)
    started_at: datetime = None
    answered_at: datetime = None
    ended_at: datetime = None
    duration: int = 0
    billsec: int = 0
    disposition: str = ""
    recording: str = ""
    cause: str = ""


class PayloadError(ValueError):
    pass


def parse_time(value, zone):
    """A PBX timestamp (`YYYY-MM-DD HH:MM:SS` in the PBX's own zone, ISO 8601
    with an offset, or epoch seconds) as an aware datetime; `None` if empty."""
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        seconds = int(value)
        if seconds <= 0:
            return None
        return datetime.fromtimestamp(seconds, dt_timezone.utc)
    text = str(value).strip()
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise PayloadError(f"زمان نامعتبر: {text[:40]}") from error
    return moment if moment.tzinfo else moment.replace(tzinfo=zone)


def _int(value):
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value, limit=64):
    return "" if value is None else str(value).strip()[:limit]


def _finish(started, duration, billsec):
    """`(answered_at, ended_at)` from a start, total seconds and talk seconds."""
    if started is None:
        return None, None
    ended = started + timedelta(seconds=duration)
    answered = ended - timedelta(seconds=billsec) if billsec else None
    return answered, ended


# --- Dolphin's own format ------------------------------------------------------------

def parse_generic(payload, zone):
    """The format any PBX, script or relay can produce:

        {"call_id": "abc-1", "stage": "ringing|answered|ended", "direction": "inbound",
         "from": "09121234567", "to": "201", "extension": "201",
         "started_at": "2026-09-29 10:00:00", "duration": 42, "billsec": 30,
         "status": "answered|no_answer|busy|failed|voicemail|abandoned",
         "recording": "file.wav"}
    """
    call_id = _text(payload.get("call_id"), 64)
    stage = _text(payload.get("stage") or "ended", 12).lower()
    if not call_id:
        raise PayloadError("شناسهٔ تماس (call_id) لازم است.")
    if stage not in STAGES:
        raise PayloadError("stage باید ringing، answered یا ended باشد.")
    direction = _text(payload.get("direction"), 10).lower()
    if direction not in ("inbound", "outbound", "internal", ""):
        raise PayloadError("direction نامعتبر است.")
    started = parse_time(payload.get("started_at"), zone)
    duration, billsec = _int(payload.get("duration")), _int(payload.get("billsec"))
    answered = parse_time(payload.get("answered_at"), zone)
    ended = parse_time(payload.get("ended_at"), zone)
    if stage == "ended":
        derived_answered, derived_ended = _finish(started, duration, billsec)
        answered, ended = answered or derived_answered, ended or derived_ended
    status = _text(payload.get("status"), 12).lower().replace(" ", "_")
    if stage == "ended" and status not in DISPOSITIONS:
        status = "answered" if billsec else "no_answer"
    rung = payload.get("rung")
    rung = [_text(item, 20) for item in rung if item][:10] if isinstance(rung, list) else []
    return [CallEvent(
        call_id, stage, direction, _text(payload.get("from")), _text(payload.get("to")),
        _text(payload.get("extension"), 20), rung,
        started, answered, ended, duration, billsec, status if stage == "ended" else "",
        _text(payload.get("recording"), 500), _text(payload.get("cause"), 80),
    )]


# --- Yeastar P-Series (webhook events 30011 and 30012) ------------------------------

YEASTAR_STATUS = {
    "ANSWERED": "answered", "NO ANSWER": "no_answer", "BUSY": "busy", "VOICEMAIL": "voicemail",
    "ABANDONED": "abandoned", "FAILED": "failed",
}


def _yeastar_message(payload):
    message = payload.get("msg")
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError as error:
            raise PayloadError("msg یستار JSON معتبر نیست.") from error
    return message if isinstance(message, dict) else {}


def parse_yeastar(payload, zone):
    kind = _text(payload.get("type"), 8)
    message = _yeastar_message(payload)
    if kind == "30012":
        started = parse_time(message.get("time_start"), zone)
        duration, billsec = _int(message.get("call_duration")), _int(message.get("talk_duration"))
        answered, ended = _finish(started, duration, billsec)
        direction = _text(message.get("type"), 10).lower()
        return [CallEvent(
            _text(message.get("call_id")), "ended", direction if direction in ("inbound", "outbound", "internal") else "",
            _text(message.get("call_from")), _text(message.get("call_to")), "", [],
            started, answered, ended, duration, billsec,
            YEASTAR_STATUS.get(_text(message.get("status"), 20).upper(), "no_answer"),
            _text(message.get("recording"), 500),
        )]
    if kind == "30011":
        call_id = _text(message.get("call_id"))
        members = {}
        for member in message.get("members") or []:
            if isinstance(member, dict):
                for role, info in member.items():
                    if isinstance(info, dict):
                        members.setdefault(role, []).append(info)
        states = [_text(info.get("member_status"), 12).upper() for infos in members.values() for info in infos]
        if not call_id or not states or all(state == "BYE" for state in states):
            return []  # the CDR event (30012) closes the call
        direction = "inbound" if "inbound" in members else "outbound" if "outbound" in members else "internal"
        leg = (members.get("inbound") or members.get("outbound") or members.get("internal") or [{}])[0]
        extensions = members.get("extension") or []
        talking = [info for info in extensions if _text(info.get("member_status"), 12).upper() == "ANSWER"]
        rung = [
            _text(info.get("number"), 20) for info in extensions
            if _text(info.get("member_status"), 12).upper() in ("RING", "ALERT")
        ]
        return [CallEvent(
            call_id, "answered" if "ANSWER" in states else "ringing", direction,
            _text(leg.get("from")), _text(leg.get("to")),
            _text((talking or extensions or [{}])[0].get("number"), 20), rung,
        )]
    return []


# --- Grandstream UCM6xxx (CDR records) ---------------------------------------------

def _grandstream_rows(payload):
    for key in ("cdr_root", "cdr", "data", "records"):
        if isinstance(payload.get(key), list):
            return [row for row in payload[key] if isinstance(row, dict)]
    return [payload]


def parse_grandstream(payload, zone):
    events = []
    for row in _grandstream_rows(payload):
        call_id = _text(row.get("uniqueid") or row.get("AcctId"))
        if not call_id:
            continue
        started = parse_time(row.get("start"), zone)
        duration, billsec = _int(row.get("duration")), _int(row.get("billsec"))
        answered, ended = parse_time(row.get("answer"), zone), parse_time(row.get("end"), zone)
        derived_answered, derived_ended = _finish(started, duration, billsec)
        kind = _text(row.get("action_type"), 20).lower()
        direction = (
            "inbound" if "did" in kind or "inbound" in kind
            else "outbound" if "outbound" in kind else "internal" if "internal" in kind else ""
        )
        disposition = _text(row.get("disposition"), 20).upper()
        events.append(CallEvent(
            call_id, "ended", direction, _text(row.get("src")), _text(row.get("dst")), "", [],
            started, answered or derived_answered, ended or derived_ended, duration, billsec,
            {"ANSWERED": "answered", "BUSY": "busy", "FAILED": "failed"}.get(disposition, "no_answer"),
            _text(row.get("recordfiles"), 500).split("@", 1)[0],
        ))
    return events


# --- FreeSWITCH family: FusionPBX and others (mod_json_cdr) -------------------------

FS_CAUSE = {
    "USER_BUSY": "busy", "CALL_REJECTED": "busy", "NO_ANSWER": "no_answer", "NO_USER_RESPONSE": "no_answer",
    "ORIGINATOR_CANCEL": "no_answer", "NORMAL_TEMPORARY_FAILURE": "failed", "UNALLOCATED_NUMBER": "failed",
}


def parse_freeswitch(payload, zone):
    variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
    call_id = _text(variables.get("uuid") or payload.get("uuid"))
    if not call_id:
        raise PayloadError("uuid در CDR فری‌سوئیچ نیست.")
    profile = {}
    flow = payload.get("callflow")
    if isinstance(flow, list) and flow and isinstance(flow[0], dict):
        profile = flow[0].get("caller_profile") or {}
    started = parse_time(variables.get("start_epoch"), zone)
    answered, ended = parse_time(variables.get("answer_epoch"), zone), parse_time(variables.get("end_epoch"), zone)
    duration, billsec = _int(variables.get("duration")), _int(variables.get("billsec"))
    cause = _text(variables.get("hangup_cause"), 80)
    disposition = "answered" if answered or billsec else FS_CAUSE.get(cause, "no_answer")
    return [CallEvent(
        call_id, "ended", "", _text(profile.get("caller_id_number") or variables.get("sip_from_user")),
        _text(profile.get("destination_number") or variables.get("sip_to_user")), "", [],
        started, answered, ended, duration, billsec, disposition,
        _text(variables.get("record_name") or variables.get("recording_file"), 500), cause,
    )]


@dataclass(frozen=True)
class Vendor:
    key: str
    label: str
    parse: object
    note: str = ""


VENDORS = {
    vendor.key: vendor
    for vendor in (
        Vendor("generic", "قالب استاندارد دلفین (هر مرکز تلفن یا اسکریپت)", parse_generic,
               "برای هر سامانه‌ای که بتواند JSON بفرستد؛ قالب در راهنما آمده است."),
        Vendor("yeastar", "Yeastar سری P (رویدادهای Webhook با کد 30011 و 30012)", parse_yeastar,
               "امضای X-Signature یستار (HMAC-SHA256 در base64) با همان کلید امضا بررسی می‌شود."),
        Vendor("grandstream", "Grandstream UCM6xxx (رکوردهای CDR)", parse_grandstream,
               "ردیف‌های CDR با فیلدهای start و end و src و dst و disposition و uniqueid."),
        Vendor("freeswitch", "FreeSWITCH / FusionPBX (mod_json_cdr)", parse_freeswitch,
               "JSON خروجی mod_json_cdr؛ پارامتر encode باید false باشد."),
    )
}
