"""One colleague's recent work, in the order it happened (2.19.0).

The user-profile counterpart of `common.customer_timeline`, in the same event
shape so the page draws both with one renderer. Where the customer timeline
asks "what happened to this customer", this one asks "what did this person
do": the calls they logged, the leads handed to them, the customers they
entered, the sales they closed and the after-sales cases they were given.

Every source reads through its module's own selector for the *viewer*, so a
manager reading a marketer's timeline sees exactly the rows the manager may
see anyway, and a marketer reading their own sees their own. Each source is
gated by its own feature; nothing here is stored.
"""

from aftersales.selectors import after_sales_requests_for
from common import labels
from common.customer_timeline import PER_SOURCE_LIMIT, TIMELINE_LIMIT, _event
from common.deployment.profile import feature_enabled
from common.formatting import money
from common.preferences import effective_preferences
from sales.selectors import customers_for, interactions_for, leads_for, sales_for


def _interaction_events(viewer, person):
    rows = (
        interactions_for(viewer)
        .filter(agent=person)
        .select_related("customer", "lead__customer")
        .order_by("-occurred_at", "-id")[:PER_SOURCE_LIMIT]
    )
    events = []
    for row in rows:
        customer = row.customer or (row.lead.customer if row.lead_id else None)
        direction = labels.label(labels.INTERACTION_DIRECTION_LABELS, row.direction)
        events.append(_event(
            "interaction", "تماس ثبت‌شده", "ki-call", "primary",
            at=row.occurred_at,
            title=row.outcome or "تماس",
            subtitle=f"{direction} — {customer.full_name}" if customer else direction,
            url=f"/interactions/{row.pk}/",
        ))
    return events


def _lead_events(viewer, person):
    rows = (
        leads_for(viewer)
        .filter(assigned_to=person, assigned_at__isnull=False)
        .select_related("customer")
        .order_by("-assigned_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "lead", "سرنخ واگذارشده", "ki-rocket", "info",
            at=row.assigned_at,
            title=row.customer.full_name if row.customer_id else (row.source or f"سرنخ #{row.pk}"),
            subtitle=row.get_status_display() if row.status else "بدون وضعیت",
            url=f"/leads/{row.pk}/",
        )
        for row in rows
    ]


def _customer_events(viewer, person):
    rows = customers_for(viewer).filter(created_by=person).order_by("-created_at", "-id")[:PER_SOURCE_LIMIT]
    return [
        _event(
            "customer", "مشتری ثبت‌شده", "ki-profile-circle", "success",
            at=row.created_at,
            title=row.full_name,
            subtitle=row.get_kind_display(),
            url=f"/customers/{row.pk}/",
        )
        for row in rows
    ]


#: `Sale.Status`'s own labels are English.
SALE_STATUS_LABELS = {"confirmed": "تأییدشده", "cancelled": "لغوشده"}


def _sale_events(viewer, person):
    unit = effective_preferences(viewer)["currency_unit"]
    rows = (
        sales_for(viewer)
        .filter(sold_by=person)
        .select_related("customer")
        .order_by("-sold_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "sale", "فروش", "ki-dollar", "success",
            at=row.sold_at,
            title=row.customer.full_name,
            subtitle=f"{labels.label(SALE_STATUS_LABELS, row.status)} — {money(row.total_amount, unit)}",
            url=f"/sales/{row.pk}/",
        )
        for row in rows
    ]


def _after_sales_events(viewer, person):
    rows = (
        after_sales_requests_for(viewer)
        .filter(assigned_to=person)
        .order_by("-created_at", "-id")[:PER_SOURCE_LIMIT]
    )
    return [
        _event(
            "after_sales", "پروندهٔ پس از فروش", "ki-wrench", "warning",
            at=row.created_at,
            title=row.subject,
            subtitle=row.status,
            url=f"/after-sales/{row.pk}/",
        )
        for row in rows
    ]


SOURCES = (
    ("leads", _interaction_events),
    ("leads", _lead_events),
    ("customers", _customer_events),
    ("sales", _sale_events),
    ("after_sales", _after_sales_events),
)


def timeline_for(viewer, person):
    """Every event about `person`'s work that `viewer` may see, newest first.

    The caller establishes that `person` is a profile `viewer` may open
    (`profiles.registry.resolve_person`)."""
    events = []
    for feature, source in SOURCES:
        if not feature_enabled(feature):
            continue
        events.extend(source(viewer, person))
    events.sort(key=lambda event: (event["at"] is not None, event["at"] or ""), reverse=True)
    return {"count": len(events), "events": events[:TIMELINE_LIMIT]}
