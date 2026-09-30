"""PRELIMINARY, UNCOMMITTED — see integration/apps.py.

The CRM-side mirror of Dolphin Accounting's own `integration/models.py`:
`PairingSettings` (the same shared secret, entered independently on both
sides — see that repo's docs/ops/DEPLOYMENT_RUNBOOK.md §2) and
`OutboundEvent` (this side's outbox — the durability guarantee for
real-time sync: written inside the *same* database transaction as the
real financial event it describes, so a crash between "the invoice was
issued" and "the event reached Accounting" is structurally impossible —
either both happened, or neither did).
"""

from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class PairingSettings(TimeStampedModel):
    """Singleton — same pattern as `communications.SmsProviderSettings`.
    `shared_secret` is plain text, same acknowledged limitation as that
    model's own `token_password` (see its docstring)."""

    SINGLETON = 1

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON)
    is_enabled = models.BooleanField(default=False)
    shared_secret = models.CharField(max_length=255, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    def __str__(self):
        return "تنظیمات اتصال به دلفین حسابداری"


class OutboundEvent(TimeStampedModel):
    """One real financial event, queued for delivery to Dolphin Accounting.

    `enqueue_event` (integration/services.py) is the only writer, always
    called from inside the same `@transaction.atomic` block as the event
    it describes (see billing/services.py's `issue_invoice`/`cancel_invoice`
    and billing/payments.py's `register_payment`/`cancel_payment`/
    `transition_cheque` for the five call sites). `dispatch_outbound_events`
    (a management command, not a new background-worker dependency — this
    codebase deliberately carries no Celery/Redis, same reasoning as
    chat/'s own polling instead of a channel layer) is the only reader.
    """

    idempotency_key = models.CharField(max_length=64, unique=True)
    event_type = models.CharField(max_length=50, db_index=True)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField()
    dispatched_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.event_type} ({self.idempotency_key})"
