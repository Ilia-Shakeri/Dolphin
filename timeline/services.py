"""Writing to a person's history — the one door every module records through.

`record` is idempotent when given a `source_ref`: the same event recorded
twice (a retried webhook, a sweeper re-running, a double click) stays one
entry. Notes are the first writer; later releases add tasks, calls and
integration events through exactly the same function.
"""

from django.db import transaction
from django.utils import timezone

from accounts.access import can_delete, capabilities_for
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from profiles.registry import adapter_for, resolve_person
from timeline.models import NOTE_MAX_LENGTH, PersonNote, TimelineEntry

NOTE_READ = "notes.read"
NOTE_WRITE = "notes.write"
NOTE_DELETE = "notes.delete"


def record(
    *,
    person_type,
    person_id,
    kind,
    title,
    source,
    source_ref="",
    occurred_at=None,
    body="",
    actor=None,
    url="",
    payload=None,
    required_capability="",
):
    """Add one event to a person's history; return the entry."""
    if adapter_for(person_type) is None:
        raise ValueError(f"Unknown person type {person_type!r}.")
    fields = {
        "person_type": person_type,
        "person_id": int(person_id),
        "occurred_at": occurred_at or timezone.now(),
        "actor": actor if getattr(actor, "pk", None) else None,
        "title": (title or "").strip()[:255] or kind,
        "body": (body or "")[:NOTE_MAX_LENGTH],
        "url": url[:255],
        "payload": payload or {},
        "required_capability": required_capability,
    }
    if source_ref:
        entry, _ = TimelineEntry.objects.get_or_create(
            source=source, source_ref=str(source_ref), kind=kind, defaults=fields
        )
        return entry
    return TimelineEntry.objects.create(source=source, kind=kind, **fields)


def forget(*, source, source_ref, kind=None):
    """Remove what `source` recorded for `source_ref` — its own thing is gone."""
    entries = TimelineEntry.objects.filter(source=source, source_ref=str(source_ref))
    if kind:
        entries = entries.filter(kind=kind)
    entries.delete()


def _require_notes_feature():
    if not feature_enabled("person_notes"):
        raise BusinessPermissionDenied("یادداشت‌ها در این استقرار فعال نیست.")


def _visible_person(actor, person_type, person_id):
    adapter, person = resolve_person(actor, person_type, person_id)
    if adapter is None or person is None:
        # Same answer for "no such person" and "not yours": a person outside
        # someone's scope must not be confirmed to exist.
        raise BusinessRuleError({"person": "این شخص در محدودهٔ دسترسی شما نیست."})
    return person


def _clean_body(body):
    body = (body or "").strip()
    if not body:
        raise BusinessRuleError({"body": "متن یادداشت را بنویسید."})
    if len(body) > NOTE_MAX_LENGTH:
        raise BusinessRuleError({"body": f"یادداشت حداکثر {NOTE_MAX_LENGTH} نویسه است."})
    return body


def _note_title(body):
    first_line = body.splitlines()[0].strip()
    return first_line[:80] + ("…" if len(first_line) > 80 else "")


@transaction.atomic
def add_note(*, actor, person_type, person_id, body):
    _require_notes_feature()
    if NOTE_WRITE not in capabilities_for(actor):
        raise BusinessPermissionDenied("نوشتن یادداشت برای شما مجاز نیست.")
    _visible_person(actor, person_type, person_id)
    body = _clean_body(body)
    note = PersonNote.objects.create(person_type=person_type, person_id=person_id, body=body, author=actor)
    record(
        person_type=person_type,
        person_id=person_id,
        kind="note",
        title=_note_title(body),
        body=body,
        source="notes",
        source_ref=note.pk,
        occurred_at=note.created_at,
        actor=actor,
        required_capability=NOTE_READ,
    )
    log_activity(actor=actor, operation="person_note.created", instance=note, changes={"fields": ["body"]})
    return note


@transaction.atomic
def update_note(*, actor, note, body):
    _require_notes_feature()
    note = PersonNote.objects.select_for_update().get(pk=note.pk)
    if note.author_id != actor.pk:
        raise BusinessPermissionDenied("فقط نویسندهٔ یادداشت می‌تواند آن را ویرایش کند.")
    _visible_person(actor, note.person_type, note.person_id)
    body = _clean_body(body)
    if body != note.body:
        note.body = body
        note.save(update_fields=["body", "updated_at"])
        TimelineEntry.objects.filter(source="notes", source_ref=str(note.pk), kind="note").update(
            title=_note_title(body), body=body
        )
        log_activity(actor=actor, operation="person_note.updated", instance=note, changes={"fields": ["body"]})
    return note


@transaction.atomic
def delete_note(*, actor, note):
    """Permanent removal — the 2.18.8 rule: Platform Admin, or `notes.delete`."""
    _require_notes_feature()
    if not can_delete(actor, NOTE_DELETE):
        raise BusinessPermissionDenied("حذف یادداشت برای شما مجاز نیست.")
    _visible_person(actor, note.person_type, note.person_id)
    log_activity(actor=actor, operation="person_note.deleted", instance=note, changes={})
    forget(source="notes", source_ref=note.pk, kind="note")
    note.delete()
