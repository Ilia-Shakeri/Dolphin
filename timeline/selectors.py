"""Reading a person's recorded history and notes, within a reader's rights.

The caller has already established that the reader may open the person's
profile (`profiles.registry.resolve_person`); these only apply the extra
capability each entry or note carries.
"""

from accounts.access import capabilities_for
from common.deployment.profile import feature_enabled
from timeline.models import PersonNote, TimelineEntry
from timeline.services import NOTE_READ

#: How each kind of recorded event is shown: label, keenicon, its `.path`
#: count, and the theme accent. A kind missing here still renders, with the
#: generic row.
KIND_STYLE = {
    "note": ("یادداشت", "ki-notepad", 5, "primary"),
    "task_created": ("وظیفهٔ تازه", "ki-add-notepad", 4, "info"),
    "task_done": ("وظیفهٔ انجام‌شده", "ki-check-circle", 2, "success"),
    "call": ("تماس تلفنی", "ki-call", 8, "primary"),
    "missed_call": ("تماس بی‌پاسخ", "ki-call", 8, "danger"),
    "message": ("پیام", "ki-message-text-2", 3, "info"),
    "integration": ("رویداد یکپارچه‌سازی", "ki-abstract-26", 2, "warning"),
}
DEFAULT_STYLE = ("رویداد", "ki-information-5", 3, "info")


def recorded_entries_for(viewer, person_type, person_id):
    """Entries `viewer` may see; notes only while notes are switched on."""
    capabilities = capabilities_for(viewer)
    entries = TimelineEntry.objects.filter(person_type=person_type, person_id=person_id)
    allowed = [""] + sorted(capabilities)
    entries = entries.filter(required_capability__in=allowed)
    if not feature_enabled("person_notes"):
        entries = entries.exclude(kind="note")
    return entries


def recorded_events_for(viewer, person_type, person_id, *, limit):
    """`(count, events)` in `common.customer_timeline`'s event shape."""
    entries = recorded_entries_for(viewer, person_type, person_id)
    count = entries.count()
    rows = entries.select_related("actor").order_by("-occurred_at", "-id")[:limit]
    events = []
    for row in rows:
        label, icon, paths, accent = KIND_STYLE.get(row.kind, DEFAULT_STYLE)
        author = ""
        if row.actor_id:
            author = row.actor.get_full_name() or row.actor.username
        events.append({
            "kind": row.kind,
            "label": label,
            "icon": icon,
            "icon_paths": paths,
            "accent": accent,
            "at": row.occurred_at.isoformat(),
            "title": row.title,
            "subtitle": author or row.body[:120],
            "url": row.url or "",
        })
    return count, events


def notes_for(viewer, person_type, person_id):
    if not feature_enabled("person_notes") or NOTE_READ not in capabilities_for(viewer):
        return PersonNote.objects.none()
    return PersonNote.objects.filter(person_type=person_type, person_id=person_id).select_related("author")
