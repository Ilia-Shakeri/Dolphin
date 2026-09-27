"""The incoming-call popup (2.23.0, decision D12).

A `CallNotification` row is written for a user when a call rings their
extension (`telephony.hooks.popup_on_ringing`) or when they missed one
(`follow_up_missed_call`). The browser asks `inbox(user)` every two seconds
while a tab is visible — one indexed query that is almost always empty — and
fetches `details(...)` once per new notification: who is calling, as far as
this user may know it.

What a popup shows is decided for the *reader*: the matched person is
resolved within the reader's own scope (`profiles.registry.resolve_person`),
and each figure (debt, purchases, score) is one of that person's profile
cards the reader would see on the profile itself (`profiles.cards`).
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.utils import timezone

from accounts.access import capabilities_for
from common.deployment.profile import feature_enabled
from telephony.models import Call, CallNotification

#: How long a missed-call popup waits to be dismissed before it drops out of
#: the inbox on its own; a ringing one drops out when the call ends.
MISSED_KEEP = timedelta(hours=12)
RINGING_KEEP = timedelta(minutes=10)
#: Which profile cards a popup repeats, per person type.
POPUP_CARDS = {"customer": ("debt", "purchases", "score"), "user": ("score",)}
INBOX_LIMIT = 5


def popup_enabled(user):
    """Whether `user`'s pages poll for popups: the feature is on and they
    have an active extension on an enabled PBX connection that shows them."""
    from telephony.services import originating_extension

    if not feature_enabled("telephony"):
        return False
    extension = originating_extension(user)
    return bool(extension and (extension.integration.config or {}).get("call_popup", True))


def inbox(user, *, now=None):
    """`[{id, kind, open}]`, newest first — what the page should be showing."""
    now = now or timezone.now()
    rows = (
        CallNotification.objects.filter(user=user, dismissed_at__isnull=True, created_at__gte=now - MISSED_KEEP)
        .select_related("call")
        .order_by("-created_at", "-id")[: INBOX_LIMIT * 2]
    )
    items = []
    for row in rows:
        is_open = row.call.status in Call.OPEN_STATUSES
        if row.kind == CallNotification.Kind.RINGING and (not is_open or row.created_at < now - RINGING_KEEP):
            continue
        items.append({"id": row.pk, "kind": row.kind, "open": is_open, "status": row.call.status})
        if len(items) >= INBOX_LIMIT:
            break
    return items


def _person(viewer, call):
    from profiles.cards import DEFAULT_PERIOD, cards_for, period_for
    from profiles.registry import resolve_person

    if not call.person_type or not call.person_id:
        return None, False
    adapter, person = resolve_person(viewer, call.person_type, call.person_id)
    if person is None:
        return None, True
    header = adapter.header(viewer, person)
    wanted = POPUP_CARDS.get(adapter.key, ())
    period = period_for(DEFAULT_PERIOD)
    figures = []
    for card in cards_for(viewer, adapter.key, person):
        if card.key not in wanted:
            continue
        value = card.compute(viewer, person, period)
        figures.append({
            "key": card.key,
            "label": card.label,
            "value": value.get("value", ""),
            "missing": value.get("missing", False),
            "tooltip": value.get("tooltip", ""),
            "accent": value.get("accent", ""),
        })
    return {
        "type": adapter.key,
        "type_label": adapter.label,
        "id": person.pk,
        "name": header["name"],
        "initials": header["initials"],
        "avatar_url": header.get("avatar_url", ""),
        "subtitle": (header.get("job_title") or {}).get("value", ""),
        "url": adapter.profile_url(person),
        "figures": figures,
    }, False


def details(viewer, notification):
    """Everything one popup draws, for `viewer` (the notification's owner)."""
    from telephony.services import can_originate

    call = notification.call
    person, hidden = _person(viewer, call)
    number = call.external_number or (call.caller_raw if call.direction == Call.Direction.INBOUND else call.callee_raw)
    may_create = (
        person is None
        and not hidden
        and bool(call.external_number)
        and feature_enabled("customers")
        and "customers.manage" in capabilities_for(viewer)
    )
    return {
        "id": notification.pk,
        "kind": notification.kind,
        "kind_label": notification.get_kind_display(),
        "call": {
            "id": call.pk,
            "direction": call.direction,
            "direction_label": call.get_direction_display(),
            "status": call.status,
            "status_label": call.get_status_display(),
            "number": number,
            "e164": call.external_number,
            "extension": call.extension,
            "started_at": call.started_at.isoformat(),
        },
        "person": person,
        # A match exists but lies outside this reader's scope: the popup says
        # the number is known without saying whose it is.
        "known_elsewhere": hidden,
        "create_customer_url": f"/customers/?{urlencode({'new_phone': call.external_number})}" if may_create else "",
        "can_call_back": bool(call.external_number) and can_originate(viewer),
    }


def dismiss(user, notification_id):
    return CallNotification.objects.filter(pk=notification_id, user=user, dismissed_at__isnull=True).update(
        dismissed_at=timezone.now()
    )
