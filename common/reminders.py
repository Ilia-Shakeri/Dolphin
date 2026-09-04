"""What this user has to act on today — the topbar bell.

Product-owner request (2026-09-04): the panel already stores every date that
matters (a lead's next follow-up, an after-sales appointment, a cheque's due
date, an instalment's due date), but nothing surfaces them. Someone had to
remember to open the calendar, then the cheque list, then the instalments
page. This module is the one place that asks all four questions at once.

Three decisions worth keeping, because each one had an alternative:

**No new model, no migration.** A reminder is *derived* from a due date that
already exists on a row someone else's module owns. Storing a second copy of
it would create the usual drift (row rescheduled, reminder not) and buy
nothing — the queries below are indexed (`Lead.next_follow_up_at`,
`AfterSalesRequest.next_appointment_at`, `Cheque.due_date`,
`Installment.due_date` all carry `db_index=True`).

**No read/dismiss state.** The badge counts work that is *actually due*, and
it clears when the work is done — the follow-up is rescheduled, the
appointment moves, the cheque clears, the instalment is paid — not when
somebody glances at the panel. A dismissable notification stream would need
a per-user-per-row table and would let a real overdue cheque be silenced by
a stray click; a work queue cannot be. This is the same reading the agent
dashboard's «صف کار امروز» already takes.

**Each source keeps its own three controls.** Feature availability is
checked here (a deployment without `payments` gets no cheque reminders),
while role permission and object scope are *not* re-implemented: every query
starts from the owning module's own selector (`leads_for`,
`after_sales_requests_for`, `cheques_for`, `installments_for`), each of
which already returns an empty queryset for a role that may not see those
rows. A marketer therefore sees their own follow-ups and nothing about
company money, without a single rule being written twice.
"""

from datetime import timedelta

from django.utils import timezone

from aftersales.selectors import after_sales_requests_for
from billing.selectors import cheques_for, installments_for
from common.deployment.profile import feature_enabled
from common.jalali import to_persian_digits
from sales.models import Lead
from sales.selectors import leads_for

#: How far ahead money is worth warning about. A cheque or an instalment
#: needs arranging before its due date, unlike a phone call, which is either
#: due now or not. Seven days is one working week — long enough to act,
#: short enough that the bell is not permanently full.
MONEY_LEAD_TIME_DAYS = 7

#: The most rows any one group returns. `count` still reports the true total,
#: so a deployment with two hundred overdue instalments shows «۲۰۰» on the
#: badge and lists the twenty most urgent — the panel's own list pages are
#: where someone works through the rest.
GROUP_ITEM_LIMIT = 20

#: Cheque statuses still awaiting money. `cleared`, `bounced` and `spent` are
#: all finished business — see `billing.models.CHEQUE_STATUS_VALUES`.
OPEN_CHEQUE_STATUSES = ("pending",)

#: Instalment statuses still owed something.
OPEN_INSTALMENT_STATUSES = ("pending", "partially_paid")

#: Lead statuses still being worked. A completed or cancelled campaign keeps
#: whatever follow-up date it had; it is not work any more.
OPEN_LEAD_STATUSES = (Lead.Status.PENDING, "")


def _lead_reminders(user, *, now):
    """Follow-ups that are due — overdue, or falling today."""
    end_of_today = _end_of_today(now)
    leads = (
        leads_for(user)
        .filter(
            next_follow_up_at__isnull=False,
            next_follow_up_at__lte=end_of_today,
            status__in=OPEN_LEAD_STATUSES,
        )
        .select_related("customer")
        .order_by("next_follow_up_at", "id")
    )
    total = leads.count()
    items = [
        {
            "id": lead.pk,
            "title": _lead_title(lead),
            "subtitle": lead.source or lead.campaign_or_batch or "بدون منبع ثبت‌شده",
            "due_at": lead.next_follow_up_at.isoformat(),
            "due_kind": "datetime",
            "overdue": lead.next_follow_up_at < now,
            "url": f"/leads/{lead.pk}/",
        }
        for lead in leads[:GROUP_ITEM_LIMIT]
    ]
    return _group("lead_follow_up", "پیگیری سرنخ", "ki-call", "primary", total, items)


def _appointment_reminders(user, *, now):
    """After-sales appointments that are due — overdue, or falling today."""
    end_of_today = _end_of_today(now)
    requests = (
        after_sales_requests_for(user)
        .filter(next_appointment_at__isnull=False, next_appointment_at__lte=end_of_today)
        .exclude(closed_at__isnull=False)
        .select_related("customer")
        .order_by("next_appointment_at", "id")
    )
    total = requests.count()
    items = [
        {
            "id": request.pk,
            "title": getattr(request.customer, "full_name", "") or f"پروندهٔ #{request.pk}",
            "subtitle": request.subject or request.status,
            "due_at": request.next_appointment_at.isoformat(),
            "due_kind": "datetime",
            "overdue": request.next_appointment_at < now,
            "url": f"/after-sales/{request.pk}/",
        }
        for request in requests[:GROUP_ITEM_LIMIT]
    ]
    return _group("after_sales_appointment", "قرار پس از فروش", "ki-calendar-tick", "info", total, items)


def _cheque_reminders(user, *, now):
    """Cheques whose due date has passed or arrives within the lead time."""
    today = timezone.localdate(now)
    horizon = today + timedelta(days=MONEY_LEAD_TIME_DAYS)
    cheques = (
        cheques_for(user)
        .filter(due_date__lte=horizon, status__in=OPEN_CHEQUE_STATUSES)
        .select_related("payment", "payment__customer")
        .order_by("due_date", "id")
    )
    total = cheques.count()
    items = [
        {
            "id": cheque.pk,
            "title": _cheque_title(cheque),
            "subtitle": f"شمارهٔ چک {cheque.serial_number}" if cheque.serial_number else cheque.bank_name,
            "due_at": cheque.due_date.isoformat(),
            "due_kind": "date",
            "overdue": cheque.due_date < today,
            "url": "/cheques/",
        }
        for cheque in cheques[:GROUP_ITEM_LIMIT]
    ]
    return _group("cheque_due", "سررسید چک", "ki-bank", "warning", total, items)


def _instalment_reminders(user, *, now):
    """Instalments whose due date has passed or arrives within the lead time."""
    today = timezone.localdate(now)
    horizon = today + timedelta(days=MONEY_LEAD_TIME_DAYS)
    instalments = (
        installments_for(user)
        .filter(due_date__lte=horizon, status__in=OPEN_INSTALMENT_STATUSES)
        .select_related("plan", "plan__invoice", "plan__invoice__customer")
        .order_by("due_date", "id")
    )
    total = instalments.count()
    items = [
        {
            "id": instalment.pk,
            "title": _instalment_title(instalment),
            # Persian digits, like every other figure the panel prints
            # since 1.7.14 — the client localises the dates and counts it
            # is given, but this sentence is composed here.
            "subtitle": f"قسط {to_persian_digits(str(instalment.sequence))}",
            "due_at": instalment.due_date.isoformat(),
            "due_kind": "date",
            "overdue": instalment.due_date < today,
            "url": "/installments/",
        }
        for instalment in instalments[:GROUP_ITEM_LIMIT]
    ]
    return _group("installment_due", "سررسید قسط", "ki-wallet", "danger", total, items)


#: Every source, in the order the panel shows them: the two that are somebody's
#: own day's work first, then the two about money. Each entry pairs the feature
#: that must be enabled with the function that reads it.
SOURCES = (
    ("leads", _lead_reminders),
    ("after_sales", _appointment_reminders),
    ("payments", _cheque_reminders),
    ("payments", _instalment_reminders),
)


def reminders_for(user, *, now=None):
    """Every due item this user may see, grouped by kind.

    Returns `{"count": int, "overdue_count": int, "groups": [...]}`. `count`
    is the true total across every source, not the number of rows listed —
    see `GROUP_ITEM_LIMIT`. An empty group is dropped rather than returned
    empty, so the panel renders only what someone actually has to do.
    """
    now = now or timezone.now()
    groups = []
    for feature, source in SOURCES:
        if not feature_enabled(feature):
            continue
        group = source(user, now=now)
        if group["count"]:
            groups.append(group)
    return {
        "count": sum(group["count"] for group in groups),
        "overdue_count": sum(
            1 for group in groups for item in group["items"] if item["overdue"]
        ),
        "groups": groups,
    }


def reminder_count_for(user, *, now=None):
    """Just the badge number — the polled call, with no rows built."""
    now = now or timezone.now()
    total = 0
    for feature, source in SOURCES:
        if not feature_enabled(feature):
            continue
        total += source(user, now=now)["count"]
    return total


#: How many `.path*` spans each keenicon needs. A duotone glyph is drawn
#: from nested spans, and rendering fewer than it has draws a partial icon —
#: `ki-call` has eight. Sent with the group rather than hardcoded in the
#: script for the same reason `WIDGET_STYLE` in `common/ui_views.py` sends
#: `icon_paths` for the dashboard tiles: the count belongs with the icon.
ICON_PATHS = {
    "ki-call": 8,
    "ki-calendar-tick": 6,
    "ki-bank": 2,
    "ki-wallet": 4,
}


def _group(kind, label, icon, accent, count, items):
    return {
        "kind": kind,
        "label": label,
        "icon": icon,
        "icon_paths": ICON_PATHS.get(icon, 2),
        "accent": accent,
        "count": count,
        "items": items,
    }


def _end_of_today(now):
    """The last instant of the local day `now` falls in.

    Local, not UTC: «امروز» means the Tehran day someone is working, and this
    deployment's `TIME_ZONE` is `Asia/Tehran`. Comparing against `now + 24h`
    instead would make a follow-up set for tomorrow morning look due tonight.
    """
    local_now = timezone.localtime(now)
    end = local_now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return end


def _lead_title(lead):
    customer = getattr(lead, "customer", None)
    name = getattr(customer, "full_name", "") if customer else ""
    return name or f"سرنخ #{lead.pk}"


def _instalment_title(instalment):
    """The customer an instalment belongs to, reached through its invoice.

    `InstallmentPlan` names an `invoice`, not a customer — the plan exists
    because that invoice is being paid over time, and the invoice is what
    names who owes it.
    """
    plan = getattr(instalment, "plan", None)
    invoice = getattr(plan, "invoice", None) if plan else None
    customer = getattr(invoice, "customer", None) if invoice else None
    name = getattr(customer, "full_name", "") if customer else ""
    return name or f"قسط #{instalment.pk}"


def _cheque_title(cheque):
    """Who the cheque is with.

    A cheque hangs off a `Payment`, and only a *receipt* names a customer: a
    disbursement names a free-text `payee` instead (there is no supplier
    model in this codebase, deliberately — see `Payment.payee`). Both are
    real cheques with real due dates, so both get a reminder; they just get
    their name from different places.
    """
    payment = getattr(cheque, "payment", None)
    customer = getattr(payment, "customer", None) if payment else None
    name = getattr(customer, "full_name", "") if customer else ""
    return name or (getattr(payment, "payee", "") if payment else "") or f"چک #{cheque.pk}"
