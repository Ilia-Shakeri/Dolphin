"""A small to-do list for the people who work customers (2.20.0, decision D6).

Until this release the only "task" Dolphin had was a lead's next follow-up
date. A task is the general version: something one person has to do by a
time, optionally about one customer or colleague, done or not. It feeds the
reminders bell like a follow-up does, and later releases create them
automatically — a missed call from a known customer becomes a task for the
salesperson who owns that customer.

Deliberately minimal — no priorities, projects, sub-tasks or recurrence —
because nothing in the product has asked for them yet.
"""

from django.conf import settings
from django.db import models

TASK_TITLE_MAX_LENGTH = 200
TASK_NOTES_MAX_LENGTH = 2000


class Task(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "باز"
        DONE = "done", "انجام‌شده"
        CANCELLED = "cancelled", "لغوشده"

    class Source(models.TextChoices):
        MANUAL = "manual", "دستی"
        MISSED_CALL = "missed_call", "تماس بی‌پاسخ"
        SYSTEM = "system", "سامانه"

    title = models.CharField(max_length=TASK_TITLE_MAX_LENGTH)
    notes = models.CharField(max_length=TASK_NOTES_MAX_LENGTH, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tasks")
    #: Whom it is about, as a `profiles` reference (decision D1). Both blank
    #: for a task about no one in particular.
    person_type = models.CharField(max_length=32, blank=True)
    person_id = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    completed_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    #: The creating module's own id for what caused it (a call's id for a
    #: missed-call task), so an automatic task is never created twice.
    source_ref = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="created_tasks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_at", "id"]
        indexes = [
            models.Index(fields=["assignee", "status", "due_at"], name="task_assignee_open_due"),
            models.Index(fields=["person_type", "person_id", "status"], name="task_person_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["open", "done", "cancelled"]), name="task_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(source__in=["manual", "missed_call", "system"]), name="task_source_valid"
            ),
            models.CheckConstraint(condition=models.Q(title__regex=r"\S"), name="task_title_nonblank"),
            # Done and only done carries a completion time.
            models.CheckConstraint(
                condition=(
                    models.Q(status="done", completed_at__isnull=False)
                    | (~models.Q(status="done") & models.Q(completed_at__isnull=True))
                ),
                name="task_completed_at_matches_status",
            ),
            # A person reference is both halves or neither.
            models.CheckConstraint(
                condition=(
                    models.Q(person_type="", person_id__isnull=True)
                    | (~models.Q(person_type="") & models.Q(person_id__isnull=False))
                ),
                name="task_person_reference_complete",
            ),
            models.UniqueConstraint(
                fields=["source", "source_ref"],
                condition=~models.Q(source_ref=""),
                name="task_source_ref_unique",
            ),
        ]

    def __str__(self):
        return self.title
