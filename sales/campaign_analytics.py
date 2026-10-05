"""Campaign results and analytics (2.36.0).

Three different numbers are kept apart on purpose and never added together:

* **registered sales** — `Sale` rows (a marketer's own record of a result),
* **valid invoices** — issued, not cancelled, attributed to the campaign,
* **collected** — the paid amount on those same invoices.

A figure that cannot be known is `None`, which the page draws as «—», never 0.
Conversion counts only people whose stage is `converted`, i.e. a valid invoice
issued to them after they entered the campaign; a person who was already a
customer is counted separately and never as a win.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, DecimalField, Min, Q, Sum
from django.db.models.functions import Coalesce, TruncDate, TruncMonth

from accounts.access import has_any_capability
from accounts.models import User
from sales.campaigns import channel_labels
from sales.models import Campaign, CampaignAttribution, Interaction, Sale, TargetAudienceMember

ZERO = Decimal("0.00")


def campaigns_for(user):
    """The campaigns a role may see.

    Company-wide roles see all. A marketer sees the campaigns they are named
    responsible for or hold people in.
    """
    queryset = Campaign.objects.all()
    if has_any_capability(user, "campaigns.company"):
        return queryset
    if has_any_capability(user, "campaigns.scoped") and user.workstream != User.Workstream.AFTER_SALES:
        return queryset.filter(Q(responsibles=user) | Q(members__assigned_to=user)).distinct()
    return queryset.none()


def members_for(user):
    queryset = TargetAudienceMember.objects.filter(campaign__isnull=False)
    if has_any_capability(user, "campaigns.company"):
        return queryset
    if has_any_capability(user, "campaigns.scoped") and user.workstream != User.Workstream.AFTER_SALES:
        return queryset.filter(assigned_to=user)
    return queryset.none()


def _valid_attributions(campaign_ids, date_from=None, date_to=None):
    from billing.models import Invoice

    queryset = CampaignAttribution.objects.filter(
        campaign_id__in=campaign_ids, invoice__status=Invoice.Status.ISSUED
    )
    if date_from:
        queryset = queryset.filter(invoice__issued_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(invoice__issued_at__date__lte=date_to)
    return queryset


def _first_contact(members):
    """Average hours from entering a campaign to the first logged interaction,
    over people who were contacted at all (`None` when nobody was), and how
    many people were left out because their first call is dated before they
    entered (a back-dated call, 2.40.0 — reported, not silently dropped)."""
    firsts = (
        Interaction.objects.filter(target_member__in=members)
        .values("target_member_id", "target_member__created_at")
        .annotate(first=Min("occurred_at"))
    )
    spans = [(row["first"] - row["target_member__created_at"]).total_seconds() / 3600 for row in firsts]
    kept = [span for span in spans if span >= 0]
    return (round(sum(kept) / len(kept), 1) if kept else None), len(spans) - len(kept)


def _first_contact_hours(members):
    return _first_contact(members)[0]


def campaign_rows(user, *, ids=None, date_from=None, date_to=None, with_money=True):
    """One row per visible campaign, in the shape the pages and the export share."""
    campaigns = campaigns_for(user)
    if ids:
        # Choosing a parent includes its sub-campaigns, so its row can be rolled up.
        campaigns = campaigns.filter(Q(pk__in=ids) | Q(parent_id__in=ids))
    campaigns = list(campaigns.order_by("-created_at", "-id"))
    campaign_ids = [campaign.pk for campaign in campaigns]
    members = members_for(user).filter(campaign_id__in=campaign_ids)
    if date_from:
        members = members.filter(created_at__date__gte=date_from)
    if date_to:
        members = members.filter(created_at__date__lte=date_to)
    stage_counts = defaultdict(lambda: defaultdict(int))
    for row in members.values("campaign_id", "stage").annotate(n=Count("id")):
        stage_counts[row["campaign_id"]][row["stage"]] = row["n"]
    contacted = dict(
        members.filter(interactions__isnull=False).values("campaign_id").annotate(n=Count("id", distinct=True))
        .values_list("campaign_id", "n")
    )
    already = dict(
        members.filter(was_customer_on_entry=True).values("campaign_id").annotate(n=Count("id"))
        .values_list("campaign_id", "n")
    )
    money = {}
    sales = {}
    if with_money:
        for row in _valid_attributions(campaign_ids, date_from, date_to).values("campaign_id").annotate(
            invoices=Count("id"),
            amount=Coalesce(Sum("invoice__total_amount"), ZERO, output_field=DecimalField()),
            collected=Coalesce(Sum("invoice__paid_amount"), ZERO, output_field=DecimalField()),
        ):
            money[row["campaign_id"]] = row
        sale_rows = Sale.objects.filter(lead__campaign_id__in=campaign_ids, status=Sale.Status.CONFIRMED)
        if date_from:
            sale_rows = sale_rows.filter(sold_at__date__gte=date_from)
        if date_to:
            sale_rows = sale_rows.filter(sold_at__date__lte=date_to)
        for row in sale_rows.values("lead__campaign_id").annotate(
            n=Count("id"), amount=Coalesce(Sum("total_amount"), ZERO, output_field=DecimalField())
        ):
            sales[row["lead__campaign_id"]] = row
    rows = []
    for campaign in campaigns:
        counts = stage_counts[campaign.pk]
        total = sum(counts.values())
        converted = counts.get(TargetAudienceMember.Stage.CONVERTED, 0)
        engaged = counts.get(TargetAudienceMember.Stage.ENGAGED, 0) + converted
        reached = contacted.get(campaign.pk, 0)
        row = {
            "id": campaign.pk,
            "parent_id": campaign.parent_id,
            "name": campaign.name,
            "status": campaign.status,
            "status_display": campaign.get_status_display(),
            "channels": campaign.channels or [campaign.channel],
            "channels_display": channel_labels(campaign),
            "channel_display": "، ".join(channel_labels(campaign)),
            "is_system": bool(campaign.system_key),
            "starts_on": campaign.starts_on,
            "ends_on": campaign.ends_on,
            "target_count": campaign.target_count,
            "members": total,
            "stages": {stage: counts.get(stage, 0) for stage in TargetAudienceMember.Stage.values},
            "contacted": reached,
            "engaged": engaged,
            "converted": converted,
            "already_customers": already.get(campaign.pk, 0),
            "conversion_rate": round(converted * 100 / total, 1) if total else None,
            "target_progress": round(total * 100 / campaign.target_count, 1) if campaign.target_count else None,
        }
        if with_money:
            attributed = money.get(campaign.pk)
            registered = sales.get(campaign.pk)
            row.update({
                "registered_sales_count": registered["n"] if registered else 0,
                "registered_sales_amount": registered["amount"] if registered else ZERO,
                "valid_invoices_count": attributed["invoices"] if attributed else 0,
                "valid_invoices_amount": attributed["amount"] if attributed else ZERO,
                "collected_amount": attributed["collected"] if attributed else ZERO,
                "budget": campaign.budget,
            })
        rows.append(row)
    rows = _roll_up_children(rows)
    if with_money:
        for row in rows:
            row["remaining_amount"] = row["valid_invoices_amount"] - row["collected_amount"]
    return rows


def unattributed_row(user, *, date_from=None, date_to=None):
    """«بدون کمپین» (2.40.0): issued invoices the reader may see that count for
    no campaign, in the same shape as a campaign row, so the rows add up to the
    company's figures. Money-capable readers only."""
    from billing.models import Invoice
    from billing.selectors import invoices_for

    invoices = invoices_for(user).filter(status=Invoice.Status.ISSUED, campaign_attribution__isnull=True)
    if date_from:
        invoices = invoices.filter(issued_at__date__gte=date_from)
    if date_to:
        invoices = invoices.filter(issued_at__date__lte=date_to)
    totals = invoices.aggregate(
        n=Count("id"),
        amount=Coalesce(Sum("total_amount"), ZERO, output_field=DecimalField()),
        collected=Coalesce(Sum("paid_amount"), ZERO, output_field=DecimalField()),
    )
    return {
        "id": None, "parent_id": None, "name": "بدون کمپین", "status": "", "status_display": "—",
        "channels": [], "channels_display": [], "channel_display": "—", "is_system": True,
        "starts_on": None, "ends_on": None, "target_count": None, "members": 0,
        "stages": {stage: 0 for stage in TargetAudienceMember.Stage.values}, "contacted": 0, "engaged": 0,
        "converted": 0, "already_customers": 0, "conversion_rate": None, "target_progress": None,
        "children_count": 0, "registered_sales_count": 0, "registered_sales_amount": ZERO,
        "valid_invoices_count": totals["n"], "valid_invoices_amount": totals["amount"],
        "collected_amount": totals["collected"], "remaining_amount": totals["amount"] - totals["collected"],
        "budget": None, "unattributed": True,
    }


_SUMMED = (
    "members", "contacted", "engaged", "converted", "already_customers",
    "registered_sales_count", "registered_sales_amount", "valid_invoices_count",
    "valid_invoices_amount", "collected_amount",
)


def _roll_up_children(rows):
    """A parent's numbers are its own people plus its sub-campaigns', counted
    once: an invoice is attributed to exactly one campaign, so summing the
    rows never counts it twice."""
    children = defaultdict(list)
    for row in rows:
        if row["parent_id"] is not None:
            children[row["parent_id"]].append(row)
    for row in rows:
        kids = children.get(row["id"])
        row["children_count"] = len(kids or [])
        if not kids:
            continue
        for key in _SUMMED:
            if key in row:
                row[key] = row[key] + sum(kid[key] for kid in kids)
        for stage in row["stages"]:
            row["stages"][stage] += sum(kid["stages"][stage] for kid in kids)
        total = row["members"]
        row["conversion_rate"] = round(row["converted"] * 100 / total, 1) if total else None
        # A parent without its own target or budget is the sum of its
        # children's (2.40.0); one with its own keeps it — that is its cap.
        if row.get("target_count") is None:
            targets = [kid["target_count"] for kid in kids if kid.get("target_count") is not None]
            row["target_count"] = sum(targets) if targets else None
        if "budget" in row and row["budget"] is None:
            budgets = [kid["budget"] for kid in kids if kid.get("budget") is not None]
            row["budget"] = sum(budgets) if budgets else None
        row["target_progress"] = round(total * 100 / row["target_count"], 1) if row.get("target_count") else None
    return rows


def _funnel(members, campaign_ids):
    """Each step a subset of the one before it (2.40.0), ending in money:
    people -> contacted -> engaged -> converted -> with a valid invoice -> paid.
    Counted as sets of people, so no step can exceed the previous one."""
    from billing.models import Invoice

    contacted = members.filter(interactions__isnull=False).values("pk").distinct()
    engaged = members.filter(
        pk__in=contacted,
        stage__in=[TargetAudienceMember.Stage.ENGAGED, TargetAudienceMember.Stage.CONVERTED],
    ).values("pk")
    converted = members.filter(pk__in=engaged, stage=TargetAudienceMember.Stage.CONVERTED).values("pk")
    valid = CampaignAttribution.objects.filter(
        member__in=converted, campaign_id__in=campaign_ids, invoice__status=Invoice.Status.ISSUED
    )
    with_invoice = valid.values("member").distinct()
    paid = valid.filter(invoice__paid_amount__gt=0).values("member").distinct()
    return [
        ("اعضای کمپین", members.count()),
        ("تماس گرفته‌شده", contacted.count()),
        ("در تعامل", engaged.count()),
        ("تبدیل‌شده", converted.count()),
        ("دارای فاکتور معتبر", with_invoice.count()),
        ("وصول‌شده", paid.count()),
    ]


def _jalali_month_series(attributions, *, date_from=None, date_to=None):
    """Valid invoices per **Jalali** month (the calendar the users keep), oldest first."""
    from common.jalali import JALALI_MONTHS, to_jalali, to_persian_digits

    buckets = {}
    per_day = (
        attributions.annotate(d=TruncDate("invoice__issued_at")).values("d")
        .annotate(n=Count("id"), amount=Coalesce(Sum("invoice__total_amount"), ZERO, output_field=DecimalField()))
    )
    for row in per_day:
        if row["d"] is None:
            continue
        year, month, _day = to_jalali(row["d"])
        bucket = buckets.setdefault((year, month), {"count": 0, "amount": ZERO})
        bucket["count"] += row["n"]
        bucket["amount"] += row["amount"]
    # Every month in the span appears, empty ones as zero (2.40.0): a gap in
    # the series would read as «no data» rather than «no sales».
    keys = sorted(buckets)
    if date_from:
        keys.append(tuple(to_jalali(date_from)[:2]))
    if date_to:
        keys.append(tuple(to_jalali(date_to)[:2]))
    span = []
    if keys:
        (year, month), last = min(keys), max(keys)
        while (year, month) <= last:
            span.append((year, month))
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return [
        {
            "month": f"{year}-{month:02d}",
            "label": to_persian_digits(f"{JALALI_MONTHS[month - 1]} {year}"),
            "count": buckets.get((year, month), {}).get("count", 0),
            "amount": buckets.get((year, month), {}).get("amount", ZERO),
        }
        for year, month in span
    ]


def campaign_analysis(user, *, ids=None, date_from=None, date_to=None):
    """Funnel, first-contact speed and the two time series, for the chosen campaigns."""
    rows = campaign_rows(user, ids=ids, date_from=date_from, date_to=date_to)
    campaign_ids = [row["id"] for row in rows]
    members = members_for(user).filter(campaign_id__in=campaign_ids)
    funnel = _funnel(members, campaign_ids)
    invoices_by_month = _jalali_month_series(
        _valid_attributions(campaign_ids, date_from, date_to), date_from=date_from, date_to=date_to
    )
    hours, back_dated = _first_contact(members)
    joined_by_day = [
        {"day": row["d"].isoformat(), "count": row["n"]}
        for row in members.annotate(d=TruncDate("created_at")).values("d").annotate(n=Count("id")).order_by("d")
    ]
    return {
        "campaigns": rows,
        "funnel": [{"label": label, "value": value} for label, value in funnel],
        "first_contact_hours": hours,
        "first_contact_excluded": back_dated,
        "invoices_by_month": invoices_by_month,
        "members_by_day": joined_by_day,
    }
