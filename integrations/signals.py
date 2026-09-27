"""Domain events raised from other modules' saves, without those modules
knowing this one exists (2.21.0).

Billing and communications stay as they are; this listens to their rows and
emits the normalized event after the row is committed. Each emit carries a
`dedupe_key`, so a row saved again never emits twice.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="billing.Payment", dispatch_uid="integrations.payment_received")
def payment_received(sender, instance, created, **kwargs):
    from integrations.events import emit

    if instance.direction != "receipt" or instance.status != "confirmed":
        return
    emit(
        "payment.received",
        {
            "payment": instance.pk,
            "customer": instance.customer_id,
            "amount": str(instance.amount),
            "method": instance.method,
            "received_at": instance.received_at.isoformat() if instance.received_at else None,
        },
        person_type="customer" if instance.customer_id else "",
        person_id=instance.customer_id,
        dedupe_key=f"payment:{instance.pk}:received",
    )


@receiver(post_save, sender="communications.InboundSMS", dispatch_uid="integrations.sms_received")
def sms_received(sender, instance, created, **kwargs):
    from integrations.events import emit

    if not created:
        return
    emit(
        "message.received",
        {"source": "sms", "sms": instance.pk, "customer": instance.customer_id},
        person_type="customer" if instance.customer_id else "",
        person_id=instance.customer_id,
        dedupe_key=f"inbound_sms:{instance.pk}",
    )


@receiver(post_save, sender="communications.OutboundSMS", dispatch_uid="integrations.sms_sent")
def sms_sent(sender, instance, created, **kwargs):
    from integrations.events import emit

    if instance.status != "sent":
        return
    emit(
        "message.sent",
        {"source": "sms", "sms": instance.pk, "customer": instance.customer_id},
        person_type="customer" if instance.customer_id else "",
        person_id=instance.customer_id,
        dedupe_key=f"outbound_sms:{instance.pk}:sent",
    )
