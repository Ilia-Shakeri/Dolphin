"""Creating and moving tasks — every write goes through here.

Three controls, as everywhere else: the `tasks` feature, the `tasks.*`
capabilities, and scope (`tasks.selectors.tasks_for`). Someone holding only
`tasks.own` works their own list: they assign tasks to themselves and touch
only tasks assigned to or created by them. `tasks.company` may assign to any
active colleague. A task about a person is only accepted when that person is
in the actor's own scope (`profiles.registry.resolve_person`).
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.access import capabilities_for, crm_identities
from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from profiles.registry import adapter_for, resolve_person
from tasks.models import TASK_NOTES_MAX_LENGTH, TASK_TITLE_MAX_LENGTH, Task
from tasks.selectors import tasks_for

TASKS_MANAGE = "tasks.manage"
TASKS_COMPANY = "tasks.company"
TASK_MUTABLE_FIELDS = {"title", "notes", "due_at", "assignee"}


def _require_feature():
    if not feature_enabled("tasks"):
        raise BusinessPermissionDenied("وظیفه‌ها در این استقرار فعال نیست.")


def _clean_text(data):
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise BusinessRuleError({"title": "عنوان وظیفه را بنویسید."})
        if len(title) > TASK_TITLE_MAX_LENGTH:
            raise BusinessRuleError({"title": f"عنوان حداکثر {TASK_TITLE_MAX_LENGTH} نویسه است."})
        data["title"] = title
    if "notes" in data:
        notes = (data["notes"] or "").strip()
        if len(notes) > TASK_NOTES_MAX_LENGTH:
            raise BusinessRuleError({"notes": f"توضیح حداکثر {TASK_NOTES_MAX_LENGTH} نویسه است."})
        data["notes"] = notes


def _check_assignee(actor, assignee):
    if assignee is None:
        raise BusinessRuleError({"assignee": "مسئول وظیفه را انتخاب کنید."})
    if not crm_identities(User.objects.filter(pk=assignee.pk, is_active=True)).exists():
        raise BusinessRuleError({"assignee": "مسئول باید یک کاربر فعال سامانه باشد."})
    if actor is not None and assignee.pk != actor.pk and TASKS_COMPANY not in capabilities_for(actor):
        raise BusinessPermissionDenied("شما فقط می‌توانید برای خودتان وظیفه ثبت کنید.")


def _check_person(actor, person_type, person_id):
    if not person_type and person_id is None:
        return "", None
    if not person_type or person_id is None or adapter_for(person_type) is None:
        raise BusinessRuleError({"person": "شخص مرتبط نامعتبر است."})
    if actor is not None:
        _, person = resolve_person(actor, person_type, person_id)
        if person is None:
            raise BusinessRuleError({"person": "این شخص در محدودهٔ دسترسی شما نیست."})
    return person_type, int(person_id)


def _timeline(task, kind, title, actor):
    if not task.person_type or not feature_enabled("tasks"):
        return
    from timeline.services import record

    record(
        person_type=task.person_type,
        person_id=task.person_id,
        kind=kind,
        title=title,
        body=task.notes,
        source="tasks",
        source_ref=task.pk,
        actor=actor,
        required_capability="",
    )


@transaction.atomic
def create_task(*, actor, title, assignee, due_at=None, notes="", person_type="", person_id=None):
    _require_feature()
    if TASKS_MANAGE not in capabilities_for(actor):
        raise BusinessPermissionDenied("ثبت وظیفه برای شما مجاز نیست.")
    data = {"title": title, "notes": notes}
    _clean_text(data)
    _check_assignee(actor, assignee)
    person_type, person_id = _check_person(actor, person_type, person_id)
    task = Task.objects.create(
        title=data["title"], notes=data["notes"], due_at=due_at, assignee=assignee,
        person_type=person_type, person_id=person_id, created_by=actor,
    )
    _timeline(task, "task_created", task.title, actor)
    log_activity(actor=actor, operation="task.created", instance=task, changes={"fields": sorted(k for k, v in data.items() if v)})
    return task


def create_system_task(*, title, assignee, source, source_ref, due_at=None, notes="", person_type="", person_id=None):
    """A task the product itself raises (a missed call, …). Idempotent on
    `(source, source_ref)`: the same cause never creates a second task."""
    if not feature_enabled("tasks"):
        return None
    data = {"title": title, "notes": notes}
    _clean_text(data)
    _check_assignee(None, assignee)
    person_type, person_id = _check_person(None, person_type, person_id)
    existing = Task.objects.filter(source=source, source_ref=str(source_ref)).first()
    if existing is not None:
        return existing
    try:
        with transaction.atomic():
            task = Task.objects.create(
                title=data["title"], notes=data["notes"], due_at=due_at, assignee=assignee,
                person_type=person_type, person_id=person_id, source=source, source_ref=str(source_ref),
            )
    except IntegrityError:
        return Task.objects.get(source=source, source_ref=str(source_ref))
    _timeline(task, "task_created", task.title, None)
    return task


def _locked(actor, task):
    task = tasks_for(actor).select_for_update().filter(pk=task.pk).first()
    if task is None:
        raise BusinessRuleError({"task": "این وظیفه در محدودهٔ دسترسی شما نیست."})
    return task


@transaction.atomic
def update_task(*, actor, task, **changes):
    _require_feature()
    if TASKS_MANAGE not in capabilities_for(actor):
        raise BusinessPermissionDenied("ویرایش وظیفه برای شما مجاز نیست.")
    unknown = set(changes) - TASK_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    task = _locked(actor, task)
    if task.status != Task.Status.OPEN:
        raise BusinessConflictError({"status": "فقط وظیفهٔ باز قابل ویرایش است."})
    _clean_text(changes)
    if "assignee" in changes:
        _check_assignee(actor, changes["assignee"])
    changed = []
    for field, value in changes.items():
        if getattr(task, field) != value:
            setattr(task, field, value)
            changed.append(field)
    if changed:
        task.save(update_fields=[*changed, "updated_at"])
        log_activity(actor=actor, operation="task.updated", instance=task, changes={"fields": sorted(changed)})
    return task


def _may_close(actor, task):
    return task.assignee_id == actor.pk or TASKS_COMPANY in capabilities_for(actor) or task.created_by_id == actor.pk


@transaction.atomic
def complete_task(*, actor, task):
    _require_feature()
    task = _locked(actor, task)
    if not _may_close(actor, task):
        raise BusinessPermissionDenied("این وظیفه را فقط مسئول آن می‌تواند انجام‌شده بزند.")
    if task.status != Task.Status.OPEN:
        raise BusinessConflictError({"status": "این وظیفه باز نیست."})
    task.status = Task.Status.DONE
    task.completed_at = timezone.now()
    task.save(update_fields=["status", "completed_at", "updated_at"])
    _timeline(task, "task_done", task.title, actor)
    log_activity(actor=actor, operation="task.completed", instance=task, changes={"status_from": "open", "status_to": "done"})
    return task


@transaction.atomic
def cancel_task(*, actor, task):
    _require_feature()
    task = _locked(actor, task)
    if not _may_close(actor, task):
        raise BusinessPermissionDenied("لغو این وظیفه برای شما مجاز نیست.")
    if task.status != Task.Status.OPEN:
        raise BusinessConflictError({"status": "این وظیفه باز نیست."})
    task.status = Task.Status.CANCELLED
    task.save(update_fields=["status", "updated_at"])
    log_activity(actor=actor, operation="task.cancelled", instance=task, changes={"status_from": "open", "status_to": "cancelled"})
    return task


@transaction.atomic
def reopen_task(*, actor, task):
    _require_feature()
    task = _locked(actor, task)
    if not _may_close(actor, task):
        raise BusinessPermissionDenied("بازکردن دوبارهٔ این وظیفه برای شما مجاز نیست.")
    if task.status == Task.Status.OPEN:
        raise BusinessConflictError({"status": "این وظیفه همین حالا باز است."})
    previous = task.status
    task.status = Task.Status.OPEN
    task.completed_at = None
    task.save(update_fields=["status", "completed_at", "updated_at"])
    if previous == Task.Status.DONE:
        from timeline.services import forget

        forget(source="tasks", source_ref=task.pk, kind="task_done")
    log_activity(actor=actor, operation="task.reopened", instance=task, changes={"status_from": previous, "status_to": "open"})
    return task
