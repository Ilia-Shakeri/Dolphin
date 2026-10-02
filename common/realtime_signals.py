"""Which saves announce themselves as live updates (2.38.0).

Connected once from `CommonConfig.ready`. A handler only calls
`common.realtime.publish`, which is a no-op unless live updates are on, so a
deployment without them pays one function call per save.
"""

from django.apps import apps
from django.db.models.signals import post_delete, post_save

from common import realtime

#: Business records the pages list. The event names the kind; the page re-reads
#: its own list through the API, under its own scope.
LIST_KINDS = {
    "sales.Customer": "customer",
    "sales.Lead": "lead",
    "sales.Interaction": "interaction",
    "sales.Sale": "sale",
    "sales.Campaign": "campaign",
    "sales.TargetAudienceMember": "campaign",
    "billing.Invoice": "invoice",
    "billing.Order": "order",
    "billing.Payment": "payment",
    "billing.PaymentAllocation": "payment",
    "aftersales.AfterSalesRequest": "after_sales",
    "inventory.StockMovement": "inventory",
}


def _announce(kind):
    def handler(sender, instance, **kwargs):
        realtime.publish(kind, object_id=instance.pk)

    return handler


def _chat_message(sender, instance, created, **kwargs):
    if not created:
        return
    users = list(instance.thread.participants.values_list("user_id", flat=True))
    realtime.publish("chat", object_id=instance.thread_id, users=users)


def _call_notification(sender, instance, created, **kwargs):
    if created:
        realtime.publish("call", object_id=instance.pk, users=[instance.user_id])


def connect():
    for label, kind in LIST_KINDS.items():
        model = apps.get_model(label)
        handler = _announce(kind)
        post_save.connect(handler, sender=model, weak=False, dispatch_uid=f"realtime-save-{label}")
        post_delete.connect(handler, sender=model, weak=False, dispatch_uid=f"realtime-delete-{label}")
    post_save.connect(_chat_message, sender=apps.get_model("chat.ChatMessage"), weak=False, dispatch_uid="realtime-chat")
    post_save.connect(_call_notification, sender=apps.get_model("telephony.CallNotification"), weak=False, dispatch_uid="realtime-call")
