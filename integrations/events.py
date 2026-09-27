"""Domain events and the outbox that carries them (2.21.0).

`emit(...)` writes a `DomainEvent` in the caller's transaction and asks for it
to be handled right after that transaction commits — so an event exists if
and only if the change behind it does. Handling runs the core handlers
registered here (timeline, scores, tasks) and queues one outbound webhook
delivery per matching subscription. Anything that fails stays `pending` with
its error and a later `available_at`; the worker (`run_integrations_worker`,
or `process_domain_events` once) retries it with backoff, and after
`MAX_ATTEMPTS` it is `failed` and visible on the integrations page.

Event names are stable strings (`call.ended`), because outside systems
subscribe to them.
"""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from common.deployment.profile import feature_enabled

logger = logging.getLogger("dolphin.integrations.events")

#: Every event this release emits, with its Persian name.
EVENT_TYPES = {
    "call.started": "شروع تماس",
    "call.answered": "پاسخ به تماس",
    "call.ended": "پایان تماس",
    "call.missed": "تماس بی‌پاسخ",
    "message.received": "دریافت پیام",
    "message.sent": "ارسال پیام",
    "payment.received": "دریافت وجه",
    "webhook.ping": "آزمایش وب‌هوک",
}

MAX_ATTEMPTS = 6
RETRY_DELAYS = (60, 300, 1800, 7200, 43200)

_HANDLERS = {}


def handles(*event_types):
    """Register `fn(event)` for these event types (decorator)."""

    def decorate(fn):
        for event_type in event_types:
            _HANDLERS.setdefault(event_type, []).append(fn)
        return fn

    return decorate


def emit(event_type, payload, *, person_type="", person_id=None, dedupe_key=""):
    """Record one event now; handle it after the surrounding commit.

    Returns the event, or `None` when the integrations feature is off or the
    same `dedupe_key` was emitted before.
    """
    from integrations.models import DomainEvent

    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event type {event_type!r}.")
    if not feature_enabled("integrations"):
        return None
    try:
        with transaction.atomic():
            event = DomainEvent.objects.create(
                event_type=event_type,
                payload=payload or {},
                person_type=person_type or "",
                person_id=person_id,
                dedupe_key=dedupe_key[:120],
                available_at=timezone.now(),
            )
    except IntegrityError:
        return None
    transaction.on_commit(lambda: _safe_process(event.pk))
    return event


def _safe_process(event_id):
    try:
        process(event_id)
    except Exception:  # noqa: BLE001 — the request that emitted it already committed
        # A handler failing after commit must not turn a saved change into an
        # error page; the event stays pending and the worker retries it.
        logger.exception("domain event handling failed", extra={"event_id": event_id})


def process(event_id, *, now=None):
    """Handle one event: core handlers, then outbound deliveries."""
    from integrations.models import DomainEvent

    now = now or timezone.now()
    with transaction.atomic():
        event = DomainEvent.objects.select_for_update(skip_locked=True).filter(
            pk=event_id, status=DomainEvent.Status.PENDING
        ).first()
        if event is None:
            return None
        event.attempts += 1
        try:
            with transaction.atomic():
                for handler in _HANDLERS.get(event.event_type, []):
                    handler(event)
                if feature_enabled("outbound_webhooks"):
                    from integrations.webhooks import queue_deliveries

                    queue_deliveries(event, now=now)
        except Exception as error:  # noqa: BLE001 — recorded and retried, never lost
            event.last_error = f"{type(error).__name__}: {error}"[:500]
            if event.attempts >= MAX_ATTEMPTS:
                event.status = DomainEvent.Status.FAILED
            else:
                delay = RETRY_DELAYS[min(event.attempts - 1, len(RETRY_DELAYS) - 1)]
                event.available_at = now + timedelta(seconds=delay)
            event.save(update_fields=["attempts", "last_error", "status", "available_at"])
            logger.warning("domain event %s failed (attempt %s)", event.pk, event.attempts)
            return event
        event.status = DomainEvent.Status.PROCESSED
        event.processed_at = now
        event.last_error = ""
        event.save(update_fields=["attempts", "status", "processed_at", "last_error"])
        return event


def process_pending(*, now=None, limit=200):
    """What the worker sweeps: every pending event whose time has come."""
    from integrations.models import DomainEvent

    now = now or timezone.now()
    ids = list(
        DomainEvent.objects.filter(status=DomainEvent.Status.PENDING, available_at__lte=now)
        .order_by("available_at", "id")
        .values_list("pk", flat=True)[:limit]
    )
    return sum(1 for event_id in ids if process(event_id, now=now) is not None)
