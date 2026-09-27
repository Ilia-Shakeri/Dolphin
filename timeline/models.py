"""Events recorded against a person, and notes written about one (2.20.0).

The profile timeline is hybrid (decision D7): the old *pull* sources —
calls, leads, invoices, payments and the rest, read live from the modules
that own them (`common.customer_timeline`, `profiles.user_timeline`) — stay
as they are, with no history migrated, and anything that has no row of its
own elsewhere is *pushed* here through `timeline.services.record`: a note,
a task being done, and in later releases a PBX call or an integration event.

A person is referred to by the `profiles` adapter key and id (decision D1),
not by a foreign key per person type.
"""

from django.conf import settings
from django.db import models

#: Longest text a note may hold — the same bound every free-text field in
#: the product uses (`sales.models.FREE_TEXT_MAX_LENGTH`).
NOTE_MAX_LENGTH = 4000


class TimelineEntry(models.Model):
    """One event in a person's history that no other table already holds."""

    person_type = models.CharField(max_length=32)
    person_id = models.PositiveBigIntegerField()
    #: What happened: `note`, `task_done`, `call`, … — drives the label and
    #: icon (`timeline.selectors.KIND_STYLE`).
    kind = models.CharField(max_length=40)
    occurred_at = models.DateTimeField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        # A person's history outlives an account that is later removed; the
        # entry keeps its text and loses only the link.
        on_delete=models.SET_NULL,
        related_name="+",
    )
    title = models.CharField(max_length=255)
    body = models.CharField(max_length=NOTE_MAX_LENGTH, blank=True)
    #: Which module recorded it, and that module's own id for the thing, so
    #: recording the same event twice is a no-op rather than a duplicate.
    source = models.CharField(max_length=40)
    source_ref = models.CharField(max_length=64, blank=True)
    url = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    #: A capability a reader must hold to see this entry, on top of seeing
    #: the person at all. Blank means "whoever may open the profile".
    required_capability = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "timeline entry"
        verbose_name_plural = "timeline entries"
        indexes = [
            models.Index(fields=["person_type", "person_id", "-occurred_at"], name="timeline_person_recent"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_ref", "kind"],
                condition=~models.Q(source_ref=""),
                name="timeline_entry_source_unique",
            ),
            models.CheckConstraint(condition=models.Q(title__regex=r"\S"), name="timeline_entry_title_nonblank"),
        ]


class PersonNote(models.Model):
    """A note someone wrote on a customer's or a colleague's profile."""

    person_type = models.CharField(max_length=32)
    person_id = models.PositiveBigIntegerField()
    body = models.CharField(max_length=NOTE_MAX_LENGTH)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="person_notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "person note"
        verbose_name_plural = "person notes"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["person_type", "person_id", "-created_at"], name="person_note_recent"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(body__regex=r"\S"), name="person_note_body_nonblank"),
        ]
