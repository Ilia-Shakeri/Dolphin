from accounts.access import has_any_capability
from communications.models import InboundSMS


def inbound_sms_for(actor):
    queryset = InboundSMS.objects.select_related("customer", "lead")
    if has_any_capability(actor, "sms.company"):
        return queryset
    return queryset.none()

