"""Telephony — calls from a connected PBX (2.22.0).

- `Extension` maps a PBX extension to a Dolphin user, per connection.
- `Call` is one call as the PBX saw it, keyed by Asterisk's `Linkedid` (the
  id every channel of one call shares), built live from AMI events and
  corrected from the CDR table.
- `CallNotification` is the per-user popup queue (a call ringing for you, one
  you missed).
- `CdrSyncState` is where the CDR sync resumes.

Calls refer to the person on the other end by the `profiles` reference
(decision D1), and to the connection with `PROTECT`: a connection that has
calls cannot be deleted, only switched off.
"""

from django.conf import settings
from django.db import models


class Extension(models.Model):
    integration = models.ForeignKey("integrations.Integration", on_delete=models.PROTECT, related_name="extensions")
    number = models.CharField(max_length=20)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="extensions"
    )
    label = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["integration", "number"]
        constraints = [
            models.UniqueConstraint(fields=["integration", "number"], name="extension_number_unique"),
            models.UniqueConstraint(
                fields=["integration", "user"],
                condition=models.Q(active=True, user__isnull=False),
                name="extension_one_active_per_user",
            ),
            models.CheckConstraint(condition=models.Q(number__regex=r"^[0-9*#]{1,20}$"), name="extension_number_digits"),
        ]

    def __str__(self):
        return self.number


class Call(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "ورودی"
        OUTBOUND = "outbound", "خروجی"
        INTERNAL = "internal", "داخلی"

    class Status(models.TextChoices):
        RINGING = "ringing", "در حال زنگ"
        ANSWERED = "answered", "در حال مکالمه"
        COMPLETED = "completed", "انجام‌شده"
        MISSED = "missed", "بی‌پاسخ"
        NO_ANSWER = "no_answer", "پاسخ داده نشد"
        BUSY = "busy", "مشغول"
        FAILED = "failed", "ناموفق"

    OPEN_STATUSES = frozenset({Status.RINGING, Status.ANSWERED})

    integration = models.ForeignKey("integrations.Integration", on_delete=models.PROTECT, related_name="calls")
    linkedid = models.CharField(max_length=64)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    caller_raw = models.CharField(max_length=64, blank=True)
    callee_raw = models.CharField(max_length=64, blank=True)
    #: The party outside the PBX, in E.164 (blank for an internal call or a
    #: number that does not normalise) — what contact matching used.
    external_number = models.CharField(max_length=20, blank=True, db_index=True)
    extension = models.CharField(max_length=20, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="calls"
    )
    person_type = models.CharField(max_length=32, blank=True)
    person_id = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RINGING)
    started_at = models.DateTimeField()
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    #: Seconds from start to end, and seconds actually talking.
    duration = models.PositiveIntegerField(default=0)
    billsec = models.PositiveIntegerField(default=0)
    hangup_cause = models.CharField(max_length=80, blank=True)
    #: The PBX's own reference to the recording (a relative path or file
    #: name). Never a URL a browser is given — recordings are streamed
    #: through Dolphin after a permission check.
    recording = models.CharField(max_length=500, blank=True)
    seen_by_ami = models.BooleanField(default=False)
    seen_in_cdr = models.BooleanField(default=False)
    #: The last events or CDR row that shaped this call, trimmed, for support.
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [
            models.Index(fields=["person_type", "person_id", "-started_at"], name="call_person_recent"),
            models.Index(fields=["user", "-started_at"], name="call_user_recent"),
            models.Index(fields=["status", "-started_at"], name="call_status_recent"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["integration", "linkedid"], name="call_linkedid_unique"),
            models.CheckConstraint(
                condition=models.Q(direction__in=["inbound", "outbound", "internal"]), name="call_direction_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["ringing", "answered", "completed", "missed", "no_answer", "busy", "failed"]),
                name="call_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(person_type="", person_id__isnull=True)
                    | (~models.Q(person_type="") & models.Q(person_id__isnull=False))
                ),
                name="call_person_reference_complete",
            ),
        ]


class CallNotification(models.Model):
    class Kind(models.TextChoices):
        RINGING = "ringing", "در حال زنگ"
        MISSED = "missed", "تماس بی‌پاسخ"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="call_notifications")
    call = models.ForeignKey(Call, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "dismissed_at", "-created_at"], name="call_notification_inbox")]
        constraints = [
            models.UniqueConstraint(fields=["user", "call", "kind"], name="call_notification_once"),
        ]


class CdrSyncState(models.Model):
    integration = models.OneToOneField("integrations.Integration", on_delete=models.CASCADE, related_name="cdr_state")
    #: The newest `calldate` already read; the next sync starts a little
    #: before it (see `telephony.cdr.OVERLAP`) so a late-written row is not
    #: skipped.
    cursor = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
