"""CDR sync — the PBX's own record of every call (2.22.0, decision D11).

The live listener can miss calls (Dolphin restarting, the network dropping);
Asterisk's CDR table cannot. Every few minutes the worker reads CDR rows newer
than the last run (minus `OVERLAP`, so a row written late is not skipped) from
FreePBX's `asteriskcdrdb.cdr` over MySQL/MariaDB and, per `linkedid`:

* creates the call if the listener never saw it,
* corrects duration and talk time from the PBX's own count,
* finishes a call the listener left open,
* records the recording file name.

It is idempotent — running it twice, or over a range already synced, changes
nothing — and `manage.py sync_cdr --since … --until …` re-runs any range.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.utils import timezone

from integrations.events import emit
from integrations.matching import best_match, normalize_caller
from telephony.models import Call, CdrSyncState
from telephony.tracker import CallTracker

logger = logging.getLogger("dolphin.telephony.cdr")

OVERLAP = timedelta(minutes=10)
FIRST_RUN_WINDOW = timedelta(days=1)
BATCH = 2000
CONNECT_TIMEOUT = 10
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]{1,64}$")
COLUMNS = ("calldate", "clid", "src", "dst", "dcontext", "channel", "dstchannel", "disposition",
           "duration", "billsec", "uniqueid", "linkedid", "recordingfile")


class CdrUnavailable(Exception):
    pass


def configured(config):
    return bool(config.get("cdr_host") and config.get("cdr_database") and config.get("cdr_username"))


def fetch_rows(config, secrets, since, until, *, limit=BATCH):
    """Rows with `since <= calldate < until`, oldest first, as dicts. Naive
    `calldate` values are the PBX's local time. Isolated so tests replace it
    with fixtures instead of a database."""
    import pymysql

    table = config.get("cdr_table") or "cdr"
    if not _IDENTIFIER.match(table):
        raise CdrUnavailable("نام جدول CDR نامعتبر است.")
    try:
        connection = pymysql.connect(
            host=config["cdr_host"],
            port=int(config.get("cdr_port") or 3306),
            user=config["cdr_username"],
            password=secrets.get("cdr_password", ""),
            database=config["cdr_database"],
            connect_timeout=CONNECT_TIMEOUT,
            read_timeout=60,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )
    except pymysql.MySQLError as error:
        raise CdrUnavailable(f"اتصال به پایگاه CDR ممکن نشد ({error.args[0] if error.args else 'error'}).") from error
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SHOW COLUMNS FROM `{table}`")
            present = {row["Field"] for row in cursor.fetchall()}
            wanted = [column for column in COLUMNS if column in present]
            if "calldate" not in present:
                raise CdrUnavailable("جدول CDR ستون calldate ندارد.")
            cursor.execute(
                f"SELECT {', '.join(f'`{c}`' for c in wanted)} FROM `{table}` "
                "WHERE calldate >= %s AND calldate < %s ORDER BY calldate LIMIT %s",
                (since.replace(tzinfo=None), until.replace(tzinfo=None), limit),
            )
            return list(cursor.fetchall())
    except pymysql.MySQLError as error:
        raise CdrUnavailable(f"خواندن CDR ممکن نشد ({error.args[0] if error.args else 'error'}).") from error
    finally:
        connection.close()


def pbx_zone(config):
    try:
        return ZoneInfo(config.get("pbx_timezone") or "Asia/Tehran")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Tehran")


def _aware(value, zone):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if timezone.is_naive(value):
        value = value.replace(tzinfo=zone)
    return value


def _local(moment, zone):
    return timezone.localtime(moment, zone)


DISPOSITION_ORDER = ("ANSWERED", "BUSY", "FAILED", "CONGESTION", "NO ANSWER")


def apply_group(integration, tracker, linkedid, rows, zone):
    """Bring one call in line with its CDR rows; `(created, changed)`."""
    rows = sorted(rows, key=lambda row: _aware(row["calldate"], zone))
    first = rows[0]
    started = _aware(first["calldate"], zone)
    duration = max(int(row.get("duration") or 0) for row in rows)
    billsec = max(int(row.get("billsec") or 0) for row in rows)
    dispositions = {str(row.get("disposition") or "").upper() for row in rows}
    disposition = next((item for item in DISPOSITION_ORDER if item in dispositions), "NO ANSWER")
    recording = next((str(row.get("recordingfile") or "") for row in rows if row.get("recordingfile")), "")
    ended = started + timedelta(seconds=duration)

    src = str(first.get("src") or "")
    dst = tracker.strip_prefix(str(first.get("dst") or ""))
    src_internal, dst_internal = tracker.is_internal(src), tracker.is_internal(dst)
    if src_internal and dst_internal:
        direction, external_raw, extension = Call.Direction.INTERNAL, "", src
    elif src_internal:
        direction, external_raw, extension = Call.Direction.OUTBOUND, dst, src
    else:
        direction, external_raw, extension = Call.Direction.INBOUND, src, dst if dst_internal else ""
        if not extension:
            for row in rows:
                peer = str(row.get("dstchannel") or "")
                candidate = peer.split("/", 1)[-1].split("-", 1)[0] if "/" in peer else ""
                if tracker.is_internal(candidate) and str(row.get("disposition") or "").upper() == "ANSWERED":
                    extension = candidate
                    break

    if disposition == "ANSWERED":
        status = Call.Status.COMPLETED
    elif direction == Call.Direction.INBOUND:
        status = Call.Status.MISSED
    elif disposition == "BUSY":
        status = Call.Status.BUSY
    elif disposition in ("FAILED", "CONGESTION"):
        status = Call.Status.FAILED
    else:
        status = Call.Status.NO_ANSWER

    call = Call.objects.select_for_update().filter(integration=integration, linkedid=linkedid).first()
    created = call is None
    if created:
        match = best_match(external_raw) if external_raw else None
        call = Call(
            integration=integration,
            linkedid=linkedid,
            direction=direction,
            caller_raw=src[:64],
            callee_raw=dst[:64],
            external_number=normalize_caller(external_raw) if external_raw else "",
            extension=extension[:20],
            user_id=tracker.extensions().get(extension) if extension else None,
            person_type=match.person_type if match else "",
            person_id=match.person_id if match else None,
            started_at=started,
        )
    before = (call.status, call.duration, call.billsec, call.recording, call.ended_at, call.seen_in_cdr)
    was_open = call.status in Call.OPEN_STATUSES
    call.seen_in_cdr = True
    call.duration = duration
    call.billsec = billsec
    if recording:
        call.recording = recording[:500]
    if created or was_open:
        call.status = status
        call.ended_at = call.ended_at or ended
        if status == Call.Status.COMPLETED and not call.answered_at:
            call.answered_at = ended - timedelta(seconds=billsec)
    call.raw = {**(call.raw or {}), "cdr": {key: str(first.get(key, "")) for key in ("clid", "src", "dst", "dcontext", "disposition")}}
    changed = created or before != (call.status, call.duration, call.billsec, call.recording, call.ended_at, call.seen_in_cdr)
    if changed:
        call.save()
    if created or was_open:
        payload = CallTracker.payload(call)
        emit("call.ended", payload, person_type=call.person_type, person_id=call.person_id, dedupe_key=f"call:{call.pk}:ended")
        if call.status == Call.Status.MISSED:
            emit("call.missed", {**payload, "rung_extensions": [call.extension] if call.extension else []},
                 person_type=call.person_type, person_id=call.person_id, dedupe_key=f"call:{call.pk}:missed")
    return created, changed


def sync(integration, *, since=None, until=None, now=None, fetch=None):
    """One pass over the CDR; `{"rows", "calls", "created", "changed"}`.

    Without `since` it resumes from the saved cursor; with it (a range re-run)
    the cursor is left alone.
    """
    from integrations.services import secrets_of

    fetch = fetch or fetch_rows
    now = now or timezone.now()
    config = integration.config or {}
    zone = pbx_zone(config)
    state, _ = CdrSyncState.objects.get_or_create(integration=integration)
    resume = since is None
    if resume:
        since = (state.cursor - OVERLAP) if state.cursor else now - FIRST_RUN_WINDOW
    until = until or now
    tracker = CallTracker(integration)
    rows = fetch(config, secrets_of(integration), since, until)
    groups = defaultdict(list)
    newest = None
    for row in rows:
        key = str(row.get("linkedid") or row.get("uniqueid") or "")
        if not key:
            continue
        groups[key].append(row)
        moment = _aware(row["calldate"], zone)
        newest = moment if newest is None or moment > newest else newest
    created = changed = 0
    for linkedid, group in groups.items():
        with transaction.atomic():
            was_created, was_changed = apply_group(integration, tracker, linkedid, group, zone)
        created += int(was_created)
        changed += int(was_changed)
    state.last_run_at = now
    state.last_error = ""
    if resume and newest is not None:
        state.cursor = max(newest, state.cursor) if state.cursor else newest
    state.save()
    return {"rows": len(rows), "calls": len(groups), "created": created, "changed": changed}
