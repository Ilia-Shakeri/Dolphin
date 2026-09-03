from django.conf import settings
from django.db import models

from sales.models import Customer, Sale, SalesDocument, TimeStampedModel


class AfterSalesRequest(TimeStampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="after_sales_requests")
    sale = models.ForeignKey(Sale, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_requests")
    document = models.ForeignKey(SalesDocument, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_requests")
    subject = models.CharField(max_length=200)
    description = models.CharField(max_length=4000)
    status = models.CharField(max_length=80, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_after_sales_requests")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_after_sales_requests")
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    #: The follow-up calendar's own field on Lead (`next_follow_up_at`) named
    #: this exact gap in DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §7 phase E: the
    #: lead side of the calendar shipped in 1.7.1, the after-sales side never
    #: had a field to draw from. Mirrors that one directly — same shape, same
    #: "null means nothing scheduled" meaning — set only through
    #: `schedule_after_sales_appointment` (aftersales/services.py), never
    #: through the general create/update path.
    next_appointment_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(subject__regex=r"\S"), name="after_sales_subject_nonblank"),
            models.CheckConstraint(condition=models.Q(description__regex=r"\S"), name="after_sales_description_nonblank"),
            models.CheckConstraint(condition=models.Q(status__regex=r"\S"), name="after_sales_status_nonblank"),
        ]
        indexes = [
            models.Index(fields=["assigned_to", "status", "-created_at"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["assigned_to", "next_appointment_at"]),
        ]


class AfterSalesHistory(models.Model):
    class Event(models.TextChoices):
        CREATED = "created", "Created"
        ASSIGNED = "assigned", "Assigned"
        STATUS_CHANGED = "status_changed", "Status changed"
        CLOSED = "closed", "Closed"
        APPOINTMENT_SCHEDULED = "appointment_scheduled", "Appointment scheduled"

    request = models.ForeignKey(AfterSalesRequest, on_delete=models.PROTECT, related_name="history")
    event = models.CharField(max_length=32, choices=Event.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="after_sales_changes")
    from_status = models.CharField(max_length=80, blank=True)
    to_status = models.CharField(max_length=80, blank=True)
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_assignments_lost")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_assignments_received")
    #: Set only on an `appointment_scheduled` row — the value `next_
    #: appointment_at` was changed to (null clears a scheduled appointment).
    appointment_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event__in=["created", "assigned", "status_changed", "closed", "appointment_scheduled"]),
                name="after_sales_history_event_valid",
            ),
        ]
        indexes = [models.Index(fields=["request", "-created_at"])]
