"""What telephony adds to a person's profile (2.23.0).

The profile adapters (`profiles/adapters.py`) ask this module — only when
the `telephony` feature is on — for:

* the PBX calls in a person's timeline, read through the *viewer's* own
  `calls_for`, so nobody's timeline shows a call its reader may not see;
* whether the calls tab and click-to-call belong on the page;
* per-user call figures for the «عملکرد» tab, and the missed-call follow-up
  measure the user score uses (`scoring.strategies`).

A missed call counts as **followed up** when, within `FOLLOW_UP_WINDOW` of
it, the user it rang called that number back from Dolphin's PBX, or the
missed-call task raised for it was completed. A missed call younger than the
window with no follow-up yet has no verdict.
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum

from accounts.access import capabilities_for
from common.customer_timeline import PER_SOURCE_LIMIT, _event
from common.deployment.profile import feature_enabled
from common.jalali import to_persian_digits
from telephony.models import Call
from telephony.selectors import calls_for

FOLLOW_UP_WINDOW = timedelta(hours=24)

STATUS_ACCENT = {
    Call.Status.COMPLETED: "success",
    Call.Status.MISSED: "danger",
    Call.Status.FAILED: "danger",
    Call.Status.NO_ANSWER: "warning",
    Call.Status.BUSY: "warning",
    Call.Status.RINGING: "info",
    Call.Status.ANSWERED: "info",
}


def sees_calls(viewer):
    return feature_enabled("telephony") and bool(capabilities_for(viewer) & {"calls.own", "calls.company"})


def sees_calls_of(viewer, user):
    """Whether the calls a colleague handled belong on `viewer`'s view of
    their profile: their own, or everyone's for a `calls.company` holder."""
    if not feature_enabled("telephony"):
        return False
    capabilities = capabilities_for(viewer)
    return "calls.company" in capabilities or ("calls.own" in capabilities and viewer.pk == user.pk)


def talk_time(seconds):
    """`155` → `۲:۳۵`; an hour or more → `۱:۰۲:۳۵`."""
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    text = f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
    return to_persian_digits(text)


def display_number(call):
    """The other party's number as written here: `۰۹۱۲…` for an Iranian one."""
    if call.external_number.startswith("+98"):
        return to_persian_digits("0" + call.external_number[3:])
    raw = call.external_number or (call.caller_raw if call.direction == Call.Direction.INBOUND else call.callee_raw)
    return to_persian_digits(raw or "")


def _events(calls, url):
    events = []
    for call in calls:
        parts = [display_number(call)]
        if call.billsec:
            parts.append(f"مکالمه {talk_time(call.billsec)}")
        if call.extension:
            who = (call.user.get_full_name() or call.user.username) if call.user_id else ""
            parts.append(f"داخلی {to_persian_digits(call.extension)}" + (f" — {who}" if who else ""))
        events.append(_event(
            "pbx_call", "تماس تلفنی", "di-phone", STATUS_ACCENT.get(call.status, "primary"),
            at=call.started_at,
            title=f"{call.get_direction_display()} — {call.get_status_display()}",
            subtitle=" · ".join(part for part in parts if part),
            url=url,
        ))
    return events


def customer_call_events(viewer, customer):
    if not feature_enabled("telephony"):
        return []
    calls = (
        calls_for(viewer).filter(person_type="customer", person_id=customer.pk)
        .select_related("user").order_by("-started_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return _events(calls, f"/customers/{customer.pk}/?tab=calls")


def user_call_events(viewer, user):
    if not sees_calls_of(viewer, user):
        return []
    calls = calls_for(viewer).filter(user=user).select_related("user").order_by("-started_at", "-id")[:PER_SOURCE_LIMIT]
    return _events(calls, f"/users/{user.pk}/?tab=calls")


def missed_follow_up(user_ids, since, now):
    """`{user id: (followed_up, decided)}` for the missed inbound calls that
    rang each user between `since` and `now`."""
    from tasks.models import Task

    missed = list(
        Call.objects.filter(
            user_id__in=user_ids, direction=Call.Direction.INBOUND, status=Call.Status.MISSED,
            started_at__gte=since, started_at__lte=now,
        ).values("id", "user_id", "external_number", "started_at")
    )
    if not missed:
        return {}
    callbacks = {}
    for row in Call.objects.filter(
        user_id__in=user_ids, direction=Call.Direction.OUTBOUND, started_at__gte=since,
        external_number__in={row["external_number"] for row in missed if row["external_number"]},
    ).values("user_id", "external_number", "started_at"):
        callbacks.setdefault((row["user_id"], row["external_number"]), []).append(row["started_at"])
    done_tasks = {}
    if feature_enabled("tasks"):
        done_tasks = {
            row["source_ref"]: row["completed_at"]
            for row in Task.objects.filter(
                source=Task.Source.MISSED_CALL, status=Task.Status.DONE,
                source_ref__in=[f"call:{row['id']}" for row in missed],
            ).values("source_ref", "completed_at")
        }
    result = {}
    for row in missed:
        deadline = row["started_at"] + FOLLOW_UP_WINDOW
        called_back = any(
            row["started_at"] < moment <= deadline
            for moment in callbacks.get((row["user_id"], row["external_number"]), [])
        ) if row["external_number"] else False
        completed = done_tasks.get(f"call:{row['id']}")
        followed = called_back or (completed is not None and completed <= deadline)
        if not followed and deadline > now:
            continue  # still inside its window: no verdict yet
        bucket = result.setdefault(row["user_id"], [0, 0])
        bucket[1] += 1
        if followed:
            bucket[0] += 1
    return {user_id: tuple(values) for user_id, values in result.items()}


def call_stats(user, since, until, *, now):
    """The «عملکرد» tab's call figures for one user and period."""
    rows = Call.objects.filter(user=user, started_at__gte=since, started_at__lt=until)
    totals = rows.aggregate(
        inbound=Count("id", filter=Q(direction=Call.Direction.INBOUND)),
        inbound_answered=Count("id", filter=Q(direction=Call.Direction.INBOUND, status=Call.Status.COMPLETED)),
        missed=Count("id", filter=Q(direction=Call.Direction.INBOUND, status=Call.Status.MISSED)),
        outbound=Count("id", filter=Q(direction=Call.Direction.OUTBOUND)),
        outbound_answered=Count("id", filter=Q(direction=Call.Direction.OUTBOUND, status=Call.Status.COMPLETED)),
        talk_seconds=Sum("billsec", filter=Q(status=Call.Status.COMPLETED)),
        conversations=Count("id", filter=Q(status=Call.Status.COMPLETED)),
    )
    talk = totals["talk_seconds"] or 0
    conversations = totals["conversations"] or 0
    followed, decided = missed_follow_up([user.pk], since, min(until, now)).get(user.pk, (0, 0))
    return {
        "inbound": totals["inbound"],
        "inbound_answered": totals["inbound_answered"],
        "missed": totals["missed"],
        "outbound": totals["outbound"],
        "outbound_answered": totals["outbound_answered"],
        "talk_seconds": talk,
        "average_talk_seconds": round(talk / conversations) if conversations else 0,
        "missed_followed_up": followed,
        "missed_decided": decided,
    }
