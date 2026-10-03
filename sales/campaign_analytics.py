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


def _first_contact_hours(members):
    """Average hours from entering a campaign to the first logged interaction,
    over people who were contacted at all; `None` when nobody was."""
    firsts = (
        Interaction.objects.filter(target_member__in=members)
        .values("target_member_id", "target_member__created_at")
        .annotate(first=Min("occurred_at"))
    )
    spans = [(row["first"] - row["target_member__created_at"]).total_seconds() / 3600 for row in firsts]
    spans = [span for span in spans if span >= 0]
    return round(sum(spans) / len(spans), 1) if spans else None


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
    return _roll_up_children(rows)


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
    return rows


def campaign_analysis(user, *, ids=None, date_from=None, date_to=None):
    """Funnel, first-contact speed and the two time series, for the chosen campaigns."""
    rows = campaign_rows(user, ids=ids, date_from=date_from, date_to=date_to)
    campaign_ids = [row["id"] for row in rows]
    members = members_for(user).filter(campaign_id__in=campaign_ids)
    shown = {row["id"] for row in rows}
    # Parents already carry their sub-campaigns' numbers: count top rows only.
    top = [row for row in rows if row["parent_id"] not in shown]
    funnel = [
        ("اعضای کمپین", sum(row["members"] for row in top)),
        ("تماس گرفته‌شده", sum(row["contacted"] for row in top)),
        ("در تعامل", sum(row["engaged"] for row in top)),
        ("تبدیل‌شده", sum(row["converted"] for row in top)),
    ]
    invoices_by_month = [
        {"month": row["m"].strftime("%Y-%m"), "count": row["n"], "amount": row["amount"]}
        for row in _valid_attributions(campaign_ids, date_from, date_to)
        .annotate(m=TruncMonth("invoice__issued_at")).values("m")
        .annotate(n=Count("id"), amount=Coalesce(Sum("invoice__total_amount"), ZERO, output_field=DecimalField()))
        .order_by("m")
    ]
    joined_by_day = [
        {"day": row["d"].isoformat(), "count": row["n"]}
        for row in members.annotate(d=TruncDate("created_at")).values("d").annotate(n=Count("id")).order_by("d")
    ]
    return {
        "campaigns": rows,
        "funnel": [{"label": label, "value": value} for label, value in funnel],
        "first_contact_hours": _first_contact_hours(members),
        "invoices_by_month": invoices_by_month,
        "members_by_day": joined_by_day,
    }
