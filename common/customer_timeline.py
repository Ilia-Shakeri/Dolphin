"""One customer's whole history, in the order it happened.

Product-owner request (2026-09-04): the customer page already showed four
separate boxes — phones, related leads, related calls, related invoices —
and each answered its own question well. What nobody could see was the
*story*: called on Sunday, quoted on Monday, invoiced on Tuesday, paid on
Thursday, complained the week after. Reading that meant four tables, four
sort orders and a lot of guessing.

Nine sources, merged and sorted by when each thing happened:

    calls · leads · orders · invoices · payments · sales documents ·
    after-sales cases · attachments · SMS in and out

The same three shapes as `common/reminders.py` and `common/search.py`, for
the same reasons — no new table, nothing derived stored, and object scope
taken from each module's own selector rather than written a second time
here. Only feature availability is checked in this module.

Two decisions specific to this one:

**Merged in Python, not in SQL.** Nine models with nine different date
columns cannot be a single indexed query without a union view or a
denormalised event table, and both are migrations in aid of one page. Each
source instead contributes at most `PER_SOURCE_LIMIT` rows — an indexed
lookup on its own foreign key to this customer — and the merge sorts a few
dozen tuples in memory.

**The event's own time, not `created_at`.** A call records
`Interaction.occurred_at`, an invoice its `issued_at`, a payment its
`received_at`. Sorting by row-creation time would put a backdated invoice
in the wrong place in the story, which is the one thing this page exists to
get right. Where a row genuinely has no business time of its own, its
`created_at` is used and that is what its date means.
"""

from django.db.models import Q

from aftersales.selectors import after_sales_requests_for
from attachments.models import Attachment
from billing.selectors import invoices_for, orders_for, payments_for
from common import labels
from common.deployment.profile import feature_enabled
from communications.selectors import inbound_sms_for, outbound_sms_for
from sales.selectors import (
    customers_for,
    interactions_for,
    leads_for,
    sales_documents_for,
)

#: Rows each source contributes before the merge. Nine sources at ten rows
#: is ninety tuples to sort — cheap — and the merge keeps the newest
#: `TIMELINE_LIMIT` of them, so a customer with three hundred calls still
#: gets their recent invoices on the page instead of a wall of calls.
PER_SOURCE_LIMIT = 10

#: Events returned after the merge.
TIMELINE_LIMIT = 40


#: See `common.reminders.ICON_PATHS`. `ki-paper-clip` is deliberately not
#: used for attachments here: it is a solid keenicon with no `.path*` spans
#: at all, so `ki-duotone` renders it blank. `ki-file` is the duotone one.
ICON_PATHS = {
    "ki-call": 8,
    "ki-rocket": 2,
    "ki-basket": 4,
    "ki-document": 2,
    "ki-dollar": 3,
    "ki-delivery": 5,
    "ki-wrench": 2,
    "ki-file": 2,
    "ki-send": 2,
    "ki-message-text": 3,
}


def _event(kind, label, icon, accent, *, at, title, subtitle, url):
    return {
        "kind": kind,
        "label": label,
        "icon": icon,
        "icon_paths": ICON_PATHS.get(icon, 2),
        "accent": accent,
        "at": at.isoformat() if at else None,
        "title": title,
        "subtitle": subtitle,
        "url": url,
    }


def _interaction_events(user, customer):
    rows = (
        interactions_for(user)
        .filter(Q(customer=customer) | Q(lead__customer=customer))
        .order_by("-occurred_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "interaction", "تماس", "ki-call", "primary",
            at=row.occurred_at,
            title=row.outcome or "تماس",
            subtitle=_direction_and_phone(row),
            url=f"/interactions/{row.pk}/",
        )
        for row in rows
    ]


def _direction_and_phone(row):
    """«ورودی — ۰۹۱۲…». `Interaction.Direction`'s own labels are English."""
    direction = labels.label(labels.INTERACTION_DIRECTION_LABELS, row.direction)
    return f"{direction} — {row.phone}" if row.phone else direction


def _lead_events(user, customer):
    rows = leads_for(user).filter(customer=customer).order_by("-created_at", "-id")[:PER_SOURCE_LIMIT]
    return [
        _event(
            "lead", "سرنخ", "ki-rocket", "info",
            at=row.created_at,
            title=row.source or row.campaign_or_batch or f"سرنخ #{row.pk}",
            subtitle=row.get_status_display() if row.status else "بدون وضعیت",
            url=f"/leads/{row.pk}/",
        )
        for row in rows
    ]


def _order_events(user, customer):
    rows = orders_for(user).filter(customer=customer).order_by("-created_at", "-id")[:PER_SOURCE_LIMIT]
    return [
        _event(
            "order", "سفارش", "ki-basket", "info",
            at=row.created_at,
            title=row.number,
            subtitle=labels.label(labels.DOCUMENT_STATUS_LABELS, row.status),
            url=f"/orders/{row.pk}/",
        )
        for row in rows
    ]


def _invoice_events(user, customer):
    rows = invoices_for(user).filter(customer=customer).order_by("-created_at", "-id")[:PER_SOURCE_LIMIT]
    return [
        _event(
            "invoice", "فاکتور", "ki-document", "warning",
            # An invoice's own date is the day it was issued; a draft has
            # none yet, and falls back to when it was raised.
            at=row.issued_at or row.created_at,
            title=row.number,
            subtitle=labels.label(labels.DOCUMENT_STATUS_LABELS, row.status),
            url=f"/invoices/{row.pk}/",
        )
        for row in rows
    ]


def _payment_events(user, customer):
    rows = payments_for(user).filter(customer=customer).order_by("-received_at", "-id")[:PER_SOURCE_LIMIT]
    return [
        _event(
            "payment", "دریافت و پرداخت", "ki-dollar", "success",
            at=row.received_at,
            title=row.number,
            subtitle=f"{row.get_direction_display()} — {labels.label(labels.PAYMENT_METHOD_LABELS, row.method)}",
            url=f"/payments/{row.pk}/",
        )
        for row in rows
    ]


def _sales_document_events(user, customer):
    rows = (
        sales_documents_for(user).filter(customer=customer).order_by("-created_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "sales_document", "سند فروش", "ki-delivery", "primary",
            at=row.created_at,
            title=row.document_number,
            subtitle=row.postal_status or "بدون وضعیت پستی",
            url=f"/sales-documents/{row.pk}/",
        )
        for row in rows
    ]


def _after_sales_events(user, customer):
    rows = (
        after_sales_requests_for(user)
        .filter(customer=customer)
        .order_by("-created_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "after_sales", "خدمات پس از فروش", "ki-wrench", "danger",
            at=row.created_at,
            title=row.subject,
            subtitle=row.status,
            url=f"/after-sales/{row.pk}/",
        )
        for row in rows
    ]


def _attachment_events(user, customer):
    # `attachments_for` takes a parent field and id and does its own scope
    # check through that parent's selector — which is this customer, already
    # checked by the caller.
    rows = (
        Attachment.objects.filter(customer=customer).order_by("-uploaded_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "attachment", "پیوست", "ki-file", "info",
            at=row.uploaded_at,
            title=row.original_filename,
            subtitle=row.content_type,
            # Attachments have no page of their own: they live on the
            # customer page this timeline is already on.
            url=f"/customers/{customer.pk}/",
        )
        for row in rows
    ]


def _outbound_sms_events(user, customer):
    rows = outbound_sms_for(user).filter(customer=customer).order_by("-sent_at", "-id")[:PER_SOURCE_LIMIT]
    return [
        _event(
            "outbound_sms", "پیامک خروجی", "ki-send", "success",
            at=row.sent_at,
            title=row.recipient_normalized,
            subtitle=labels.label(labels.OUTBOUND_SMS_STATUS_LABELS, row.status),
            url="/sms/",
        )
        for row in rows
    ]


def _inbound_sms_events(user, customer):
    rows = (
        inbound_sms_for(user)
        .filter(customer=customer)
        .order_by("-provider_received_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "inbound_sms", "پیامک ورودی", "ki-message-text", "primary",
            at=row.provider_received_at,
            title=row.sender_normalized,
            subtitle=labels.label(labels.INBOUND_SMS_STATE_LABELS, row.processing_state),
            url="/reports/inbound-sms/",
        )
        for row in rows
    ]


#: Every source, paired with the feature that must be enabled for it. Calls
#: and leads both belong to the `leads` module — a call is recorded against a
#: campaign, not on its own.
SOURCES = (
    ("leads", _interaction_events),
    ("leads", _lead_events),
    ("orders", _order_events),
    ("invoices", _invoice_events),
    ("payments", _payment_events),
    ("sales_documents", _sales_document_events),
    ("after_sales", _after_sales_events),
    ("attachments", _attachment_events),
    ("outbound_sms", _outbound_sms_events),
    ("inbound_sms", _inbound_sms_events),
)


def timeline_for(user, customer):
    """Every event about this customer that this user may see, newest first.

    The caller is responsible for having established that the customer is in
    scope — `visible_customer` below is what does that.
    """
    events = []
    for feature, source in SOURCES:
        if not feature_enabled(feature):
            continue
        events.extend(source(user, customer))
    # A row with no usable date sorts last rather than crashing the merge on
    # a None comparison; every source above supplies one, and this is the
    # defensive floor for a column that is nullable in the schema.
    events.sort(key=lambda event: (event["at"] is not None, event["at"] or ""), reverse=True)
    return {"count": len(events), "events": events[:TIMELINE_LIMIT]}


def visible_customer(user, customer_id):
    """The customer, or `None` when this user may not see them.

    `None` becomes a 404 rather than a 403 in the view, the same as every
    other out-of-scope direct read in this codebase: a customer outside
    someone's book must not be confirmed to exist.
    """
    return customers_for(user).filter(pk=customer_id).first()
