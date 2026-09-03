from accounts.access import has_any_capability
from communications.models import InboundSMS, OutboundSMS


def inbound_sms_for(actor):
    queryset = InboundSMS.objects.select_related("customer", "lead")
    if has_any_capability(actor, "sms.company"):
        return queryset
    return queryset.none()


def outbound_sms_for(actor):
    queryset = OutboundSMS.objects.select_related("customer", "lead", "sent_by")
    if has_any_capability(actor, "sms.company"):
        return queryset
    return queryset.none()

