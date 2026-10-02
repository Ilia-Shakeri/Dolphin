"""What the rest of Dolphin does when a call happens (2.23.0).

Registered as domain-event handlers and signal receivers, so the listener and
the CDR sync never call into tasks, scores or the popup directly:

* **ringing** (`telephony.signals.call_ringing`) — a popup for the user whose
  extension rings, if the connection has the popup switched on;
* **missed** (`call.missed`) — a popup for everyone who was rung, and a
  follow-up task for the salesperson who owns that customer, if the
  connection asks for one;
* **ended** (`call.ended`) — the person's score is refreshed.

Calls reach timelines as a *pull* source (`telephony.timeline`), read through
the viewer's own `calls_for`, not as recorded entries — so a marketer's
timeline shows the calls they may see and no others.
"""

import logging
from datetime import timedelta

from django.dispatch import receiver
from django.utils import timezone

from integrations.events import handles
from telephony.signals import call_ringing

logger = logging.getLogger("dolphin.telephony.hooks")


def _config(call):
    return (call.integration.config or {}) if call.integration_id else {}


@receiver(call_ringing, dispatch_uid="telephony.popup_on_ringing")
def popup_on_ringing(sender, call, user_id, **kwargs):
    from telephony.models import CallNotification

    if not _config(call).get("call_popup", True):
        return
    CallNotification.objects.get_or_create(user_id=user_id, call=call, kind=CallNotification.Kind.RINGING)


def owner_of(call):
    """Who follows up a missed call from a customer: whoever holds that
    customer's newest open lead, else the marketer who entered the customer,
    else whoever's extension rang first."""
    from accounts.access import is_crm_identity
    from accounts.models import User
    from sales.models import Customer, Lead
    from telephony.models import Extension

    if call.person_type == "customer" and call.person_id:
        lead = (
            Lead.objects.filter(customer_id=call.person_id, status=Lead.Status.PENDING, assigned_to__isnull=False)
            .select_related("assigned_to").order_by("-assigned_at", "-id").first()
        )
        if lead and is_crm_identity(lead.assigned_to):
            return lead.assigned_to
        customer = Customer.objects.select_related("owner", "created_by").filter(pk=call.person_id).first()
        worker = (customer.owner or customer.created_by) if customer else None
        if worker and worker.role == User.Role.SALES_AGENT and is_crm_identity(worker):
            return worker
    extension = call.extension
    if extension:
        row = Extension.objects.filter(integration_id=call.integration_id, number=extension, active=True).select_related("user").first()
        if row and row.user and is_crm_identity(row.user):
            return row.user
    return None


@handles("call.missed")
def follow_up_missed_call(event):
    from tasks.services import create_system_task
    from telephony.models import Call, CallNotification, Extension

    call = Call.objects.select_related("integration").filter(pk=event.payload.get("call")).first()
    if call is None:
        return
    config = _config(call)
    if config.get("call_popup", True):
        rung = event.payload.get("rung_extensions") or ([call.extension] if call.extension else [])
        for row in Extension.objects.filter(integration_id=call.integration_id, number__in=rung, active=True, user__isnull=False):
            CallNotification.objects.get_or_create(user_id=row.user_id, call=call, kind=CallNotification.Kind.MISSED)
    if not config.get("missed_call_task", True) or call.person_type != "customer":
        return
    owner = owner_of(call)
    if owner is None:
        return
    from sales.models import Customer
    from telephony.profile import display_number

    number = display_number(call)
    name = Customer.objects.filter(pk=call.person_id).values_list("full_name", flat=True).first() or number
    create_system_task(
        title=f"پاسخ به تماس بی‌پاسخ {name}",
        notes=f"تماس ورودی از {number} بی‌پاسخ ماند.",
        assignee=owner,
        source="missed_call",
        source_ref=f"call:{call.pk}",
        due_at=timezone.now() + timedelta(hours=2),
        person_type="customer",
        person_id=call.person_id,
    )


@handles("call.ended")
def refresh_scores(event):
    from scoring.services import refresh
    from telephony.models import Call

    call = Call.objects.filter(pk=event.payload.get("call")).first()
    if call is None:
        return
    if call.person_type == "customer" and call.person_id:
        from sales.models import Customer

        customer = Customer.objects.filter(pk=call.person_id).first()
        if customer is not None:
            refresh("customer", customer)
    if call.user_id:
        refresh("user", call.user)
