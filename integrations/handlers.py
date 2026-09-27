"""Core reactions to domain events — what Dolphin itself does with them.

Registered on import (`IntegrationsConfig.ready`). Each handler is idempotent
because an event can be retried: the timeline store dedupes on
`(source, source_ref, kind)`.
"""

from integrations.events import handles


@handles("message.received")
def record_inbound_message(event):
    """A message from an integration lands on the matched person's timeline.

    SMS is not recorded here: inbound SMS already has its own timeline source
    (`common.customer_timeline`), and recording it twice would show it twice.
    """
    from timeline.services import record

    payload = event.payload
    if payload.get("source") != "webhook" or not event.person_type:
        return
    channel = payload.get("channel") or "پیام‌رسان"
    record(
        person_type=event.person_type,
        person_id=event.person_id,
        kind="message",
        title=f"پیام دریافتی — {channel}",
        body=payload.get("text", ""),
        source="integrations",
        source_ref=f"event:{event.pk}",
        occurred_at=event.created_at,
        payload={"from": payload.get("from", ""), "integration": payload.get("integration")},
    )
