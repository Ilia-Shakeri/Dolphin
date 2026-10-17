"""One set of conversion definitions for all of Dolphin (2.40.59, BIZ-004).

Product owner, 2026-10-17:

1. **نرخ تبدیل سرنخ به فروش** — qualified leads that reached a valid purchase
   ÷ the qualified leads of the same group.
2. **نرخ تعیین تکلیف** — leads closed as won ÷ every lead closed (won or
   lost) in the period. A different measure, never to be confused with (1).
3. **نرخ فروش کمپین** — new customers who reached a valid purchase through
   the campaign ÷ the campaign's qualified leads.

* The denominator is the *qualified* leads — not every entry, not only the
  calls that were answered.
* Groups are by the date a lead entered the group or campaign; the invoice
  date is shown beside it for the time to convert.
* A purchase counts within the attribution window: 30 days from the last
  relevant call by default, set in Settings. Outside it, only a manager's
  attribution with a reason counts.
* An existing customer buying again is a **repeat purchase**, counted apart
  and never mixed into new customers won.
* Cancelling an invoice corrects every figure — each is read from valid
  invoices every time. There is no minimum amount.
* Every rate is shown with its definition, numerator and denominator.

What "qualified" means for a lead is this module's: at least one call marked
qualified (`Interaction.qualified`, 2.40.58), or reaching a stage that counts
as qualified (`PipelineStage.qualifies`, 2.40.57 — «واجد شرایط» and after by
default). A lead here is a person being sold to: a lead that names a
customer, or a campaign person.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Min, Q

from sales.models import Interaction, Lead, SalesSettings, StageChange, TargetAudienceMember

#: The bounds a company may set the window to.
MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 365


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    definition: str
    numerator: str
    denominator: str


METRICS = {metric.key: metric for metric in (
    Metric(
        "lead_to_sale", "نرخ تبدیل سرنخ به فروش",
        "سرنخ‌های واجد شرایطی که به خرید معتبر رسیده‌اند، تقسیم بر سرنخ‌های واجد شرایط همان گروه؛ "
        "گروه‌بندی با تاریخ ورود سرنخ، و خرید در پنجرهٔ انتساب پس از آخرین تماس.",
        "سرنخ واجد شرایط با خرید معتبر", "سرنخ واجد شرایط",
    ),
    Metric(
        "resolution", "نرخ تعیین تکلیف",
        "سرنخ‌هایی که در بازه با «برنده» بسته شده‌اند، تقسیم بر همهٔ سرنخ‌هایی که در بازه بسته شده‌اند "
        "(برنده یا بازنده). با نرخ تبدیل به فروش فرق دارد: مرحلهٔ دستی است، نه فاکتور.",
        "بسته‌شده با برنده", "بسته‌شده (برنده یا بازنده)",
    ),
    Metric(
        "campaign_sales", "نرخ فروش کمپین",
        "مشتریان تازه‌ای که از کمپین به خرید معتبر رسیده‌اند، تقسیم بر سرنخ‌های واجد شرایط همان کمپین؛ "
        "گروه‌بندی با تاریخ ورود به کمپین.",
        "مشتری تازه با خرید معتبر", "سرنخ واجد شرایط کمپین",
    ),
    Metric(
        "repeat", "خرید تکراری",
        "کسانی که پیش از ورود به گروه یا کمپین مشتری بوده‌اند و دوباره خرید معتبر کرده‌اند؛ جدا از جذب مشتری تازه "
        "شمرده می‌شوند.",
        "مشتری قبلی با خرید معتبر تازه", "",
    ),
)}


def window_days():
    """The attribution window in days: the company's setting, else the
    deployment's `DOLPHIN_CAMPAIGN_ATTRIBUTION_WINDOW_DAYS`, else 30."""
    row = SalesSettings.objects.filter(pk=1).only("attribution_window_days").first()
    if row is not None and row.attribution_window_days:
        return row.attribution_window_days
    return int(getattr(settings, "CAMPAIGN_ATTRIBUTION_WINDOW_DAYS", 30))


def can_configure(user):
    from accounts.access import has_any_capability

    return has_any_capability(user, "customization.manage")


def settings_payload():
    row = SalesSettings.objects.filter(pk=1).first()
    return {
        "attribution_window_days": window_days(),
        "is_default": row is None or not row.attribution_window_days,
        "min_days": MIN_WINDOW_DAYS,
        "max_days": MAX_WINDOW_DAYS,
        "definitions": definitions(),
    }


def update_settings(*, actor, attribution_window_days):
    """Set the attribution window (1–365 days). Changing it changes how every
    later purchase is attributed; what was attributed before stays."""
    from django.db import transaction

    from auditlog.services import log_activity
    from common.exceptions import BusinessPermissionDenied, BusinessRuleError

    if not can_configure(actor):
        raise BusinessPermissionDenied("تغییر پنجرهٔ انتساب مجاز نیست.")
    try:
        days = int(attribution_window_days)
    except (TypeError, ValueError):
        raise BusinessRuleError({"attribution_window_days": "تعداد روز را عددی بنویسید."}) from None
    if not MIN_WINDOW_DAYS <= days <= MAX_WINDOW_DAYS:
        raise BusinessRuleError({
            "attribution_window_days": f"پنجره باید بین {MIN_WINDOW_DAYS} و {MAX_WINDOW_DAYS} روز باشد.",
        })
    with transaction.atomic():
        row, _ = SalesSettings.objects.select_for_update().get_or_create(pk=1)
        previous = row.attribution_window_days
        row.attribution_window_days, row.updated_by = days, actor
        row.save()
        log_activity(actor=actor, operation="sales_settings.updated", instance=row,
                     changes={"attribution_window_days": {"from": previous, "to": days}})
    return settings_payload()


def rate(numerator, denominator):
    """A percentage to one decimal place, or `None` when there is nothing to divide by."""
    if not denominator:
        return None
    return (Decimal(numerator * 100) / Decimal(denominator)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def figure(key, numerator, denominator):
    """A rate with what it is: what the reports show for every percentage."""
    metric = METRICS[key]
    return {
        "key": key, "label": metric.label, "definition": metric.definition,
        "numerator_label": metric.numerator, "denominator_label": metric.denominator,
        "numerator": numerator, "denominator": denominator, "rate": rate(numerator, denominator),
    }


def definitions():
    return [
        {"key": metric.key, "label": metric.label, "definition": metric.definition,
         "numerator_label": metric.numerator, "denominator_label": metric.denominator}
        for metric in METRICS.values()
    ]


# --- qualified ---------------------------------------------------------------------


def _qualifying(pipeline):
    from sales.pipeline import qualifying_keys

    return qualifying_keys(pipeline)


def qualified_leads(leads):
    """The leads among `leads` that are qualified: a call marked qualified, or a
    stage reached that counts as qualified (now, or in the stage history)."""
    keys = _qualifying("lead")
    called = Interaction.objects.filter(qualified=True, lead__in=leads, target_member__isnull=True).values("lead_id")
    reached = StageChange.objects.filter(lead__in=leads, to_stage__in=keys).values("lead_id")
    return leads.filter(Q(stage__in=keys) | Q(pk__in=called) | Q(pk__in=reached))


def qualified_members(members):
    """The campaign people among `members` that are qualified, the same way."""
    keys = _qualifying("campaign")
    called = Interaction.objects.filter(qualified=True, target_member__in=members).values("target_member_id")
    reached = StageChange.objects.filter(member__in=members, to_stage__in=keys).values("member_id")
    return members.filter(Q(stage__in=keys) | Q(pk__in=called) | Q(pk__in=reached))


# --- leads that name a customer ----------------------------------------------------


@dataclass
class LeadOutcome:
    """What became of one qualified lead: won (a new customer's valid purchase
    in the window), a repeat purchase, or neither yet."""

    lead_id: int
    owner_id: int | None = None
    won_at: object = None
    repeat_at: object = None


def lead_purchases(leads):
    """For each qualified lead naming a customer, its valid purchase if any.

    A purchase is an issued, not cancelled, invoice to the lead's customer,
    issued after the lead entered and within the window after the lead's last
    call before it. A customer who already had a valid invoice before the lead
    entered is a repeat purchase, not a conversion.
    """
    from billing.models import Invoice

    rows = list(
        qualified_leads(leads).filter(customer__isnull=False).values("pk", "customer_id", "created_at", "assigned_to_id")
    )
    if not rows:
        return []
    customer_ids = {row["customer_id"] for row in rows}
    invoices = {}
    for customer_id, issued_at in (
        Invoice.objects.filter(customer_id__in=customer_ids, status=Invoice.Status.ISSUED, issued_at__isnull=False)
        .order_by("issued_at").values_list("customer_id", "issued_at")
    ):
        invoices.setdefault(customer_id, []).append(issued_at)
    calls = {}
    for lead_id, occurred_at in (
        Interaction.objects.filter(lead_id__in=[row["pk"] for row in rows]).values_list("lead_id", "occurred_at")
    ):
        calls.setdefault(lead_id, []).append(occurred_at)
    window = timedelta(days=window_days())
    outcomes = []
    for row in rows:
        outcome = LeadOutcome(row["pk"], row["assigned_to_id"])
        issued = invoices.get(row["customer_id"], [])
        was_customer = any(at < row["created_at"] for at in issued)
        for at in (at for at in issued if at >= row["created_at"]):
            before = [call for call in calls.get(row["pk"], []) if call <= at]
            if before and at - max(before) <= window:
                if was_customer:
                    outcome.repeat_at = at
                else:
                    outcome.won_at = at
                break
        outcomes.append(outcome)
    return outcomes


def lead_to_sale(leads):
    """Metric 1 over `leads` (already the group, by entry date): the figure,
    and the repeat purchases beside it."""
    work = leads.exclude(source="campaign")
    qualified = qualified_leads(work).count()
    outcomes = lead_purchases(work)
    won = sum(1 for item in outcomes if item.won_at)
    repeat = sum(1 for item in outcomes if item.repeat_at)
    return figure("lead_to_sale", won, qualified), repeat


def lead_to_sale_all(leads, members):
    """Metric 1 over both kinds of lead together — leads naming a customer and
    campaign people — and the repeat purchases beside it."""
    from billing.models import Invoice
    from sales.models import CampaignAttribution

    work = leads.exclude(source="campaign")
    outcomes = lead_purchases(work)
    qualified_people = qualified_members(members)
    won = sum(1 for item in outcomes if item.won_at) + qualified_people.filter(
        stage=TargetAudienceMember.Stage.CONVERTED, was_customer_on_entry=False,
    ).count()
    qualified = qualified_leads(work).count() + qualified_people.count()
    repeat = sum(1 for item in outcomes if item.repeat_at) + (
        CampaignAttribution.objects.filter(
            member__in=members.filter(was_customer_on_entry=True), invoice__status=Invoice.Status.ISSUED,
        ).values("member_id").distinct().count()
    )
    return figure("lead_to_sale", won, qualified), repeat


def resolution(leads, start=None, end=None):
    """Metric 2: leads closed won ÷ leads closed (won or lost), by `closed_at`."""
    closed = leads.exclude(source="campaign").filter(status__in=[Lead.Status.COMPLETED, Lead.Status.CANCELLED])
    if start is not None:
        closed = closed.filter(closed_at__gte=start)
    if end is not None:
        closed = closed.filter(closed_at__lt=end)
    total = closed.count()
    won = closed.filter(status=Lead.Status.COMPLETED).count()
    return figure("resolution", won, total)


def per_owner(user_ids, start, end):
    """The three figures for each person in `user_ids`, in a handful of queries.

    Their group is what was given to them in [start, end): leads that name a
    customer by `assigned_at`, campaign people by `assigned_at`. Lead-to-sale
    counts both kinds of lead; resolution counts their leads closed in the
    window. `{user_id: {"won", "qualified", "repeat", "closed_won", "closed"}}`.
    """
    from django.db.models import Count

    from billing.models import Invoice
    from sales.models import CampaignAttribution

    figures = {pk: {"won": 0, "qualified": 0, "repeat": 0, "closed_won": 0, "closed": 0} for pk in user_ids}
    leads = Lead.objects.exclude(source="campaign").filter(
        assigned_to_id__in=user_ids, assigned_at__gte=start, assigned_at__lt=end,
    )
    for owner, total in qualified_leads(leads).values_list("assigned_to_id").annotate(n=Count("id")):
        figures[owner]["qualified"] += total
    for outcome in lead_purchases(leads):
        if outcome.owner_id in figures:
            figures[outcome.owner_id]["won"] += 1 if outcome.won_at else 0
            figures[outcome.owner_id]["repeat"] += 1 if outcome.repeat_at else 0
    members = TargetAudienceMember.objects.filter(
        campaign__isnull=False, assigned_to_id__in=user_ids, assigned_at__gte=start, assigned_at__lt=end,
    )
    qualified = qualified_members(members)
    for owner, total in qualified.values_list("assigned_to_id").annotate(n=Count("id")):
        figures[owner]["qualified"] += total
    for owner, total in (
        qualified.filter(stage=TargetAudienceMember.Stage.CONVERTED, was_customer_on_entry=False)
        .values_list("assigned_to_id").annotate(n=Count("id"))
    ):
        figures[owner]["won"] += total
    for owner, total in (
        CampaignAttribution.objects.filter(
            member__in=members.filter(was_customer_on_entry=True), invoice__status=Invoice.Status.ISSUED,
        ).values_list("member__assigned_to_id").annotate(n=Count("member_id", distinct=True))
    ):
        figures[owner]["repeat"] += total
    closed = Lead.objects.exclude(source="campaign").filter(
        assigned_to_id__in=user_ids, closed_at__gte=start, closed_at__lt=end,
        status__in=[Lead.Status.COMPLETED, Lead.Status.CANCELLED],
    )
    for owner, total, won in (
        closed.values_list("assigned_to_id")
        .annotate(n=Count("id"), w=Count("id", filter=Q(status=Lead.Status.COMPLETED)))
    ):
        figures[owner]["closed"] += total
        figures[owner]["closed_won"] += won
    return figures


# --- campaign people ---------------------------------------------------------------


def campaign_sales(members):
    """Metric 3 over campaign people (already the cohort, by entry date), and
    the repeat purchases beside it.

    Won is a person moved to «تبدیل‌شده» by a valid attributed invoice — never
    one who was a customer on entry (`sales.campaign_attribution`). A repeat
    purchase is a person who was a customer on entry with a valid attributed
    invoice.
    """
    from billing.models import Invoice
    from sales.models import CampaignAttribution

    qualified = qualified_members(members)
    won = qualified.filter(stage=TargetAudienceMember.Stage.CONVERTED, was_customer_on_entry=False).count()
    repeat = (
        CampaignAttribution.objects.filter(
            member__in=members.filter(was_customer_on_entry=True), invoice__status=Invoice.Status.ISSUED,
        ).values("member_id").distinct().count()
    )
    return figure("campaign_sales", won, qualified.count()), repeat


def time_to_convert(members):
    """Average days from entering a campaign to the valid invoice that
    converted the person, over the people converted; `None` when none were."""
    from billing.models import Invoice
    from sales.models import CampaignAttribution

    spans = (
        CampaignAttribution.objects.filter(
            member__in=members.filter(stage=TargetAudienceMember.Stage.CONVERTED, was_customer_on_entry=False),
            invoice__status=Invoice.Status.ISSUED,
        )
        .values("member_id", "member__created_at")
        .annotate(first=Min("invoice__issued_at"))
    )
    days = [(row["first"] - row["member__created_at"]).total_seconds() / 86400 for row in spans if row["first"]]
    days = [value for value in days if value >= 0]
    return round(sum(days) / len(days), 1) if days else None

