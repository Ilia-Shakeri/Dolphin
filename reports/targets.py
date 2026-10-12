"""Marketers against their monthly sales targets (2.40.41).

For one Jalali month: every active marketer (the ranking's own list), the
target a manager set for them (`sales.SalesTarget`, or none), and what they
sold — the ranking's «مبلغ فروش», issued invoices they made, counted from the
first to the last day of that month in Tehran time. Company-wide figures:
`reports.company` only; setting the targets is `sales_targets.manage`
(`sales.targets`).
"""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum

from accounts.access import has_any_capability
from billing.models import Invoice
from common import jalali
from reports.marketers import marketers_queryset
from reports.services import MONEY_QUANTUM, ReportAccessDenied, format_utc_timestamp
from sales.models import SalesTarget
from sales.targets import clean_month


def month_window(year, month):
    """The month's first and the next month's first moment, Tehran time."""
    start = datetime.datetime.combine(jalali.from_jalali(year, month, 1), datetime.time(0), tzinfo=jalali.OPERATIONAL_TIMEZONE)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    end = datetime.datetime.combine(jalali.from_jalali(next_year, next_month, 1), datetime.time(0), tzinfo=jalali.OPERATIONAL_TIMEZONE)
    return start, end


def current_month(now):
    year, month, _ = jalali.to_jalali(now.astimezone(jalali.OPERATIONAL_TIMEZONE).date())
    return year, month


def _percent(part, whole):
    if not whole:
        return None
    return (Decimal(part) * 100 / whole).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def build_monthly_targets(*, actor, year, month):
    if not has_any_capability(actor, "reports.company"):
        raise ReportAccessDenied
    year, month = clean_month(year, month)
    start, end = month_window(year, month)
    users = list(marketers_queryset())
    ids = [user.pk for user in users]
    sold = dict(
        Invoice.objects.filter(
            created_by_id__in=ids, status=Invoice.Status.ISSUED, issued_at__gte=start, issued_at__lt=end,
        ).values_list("created_by_id").annotate(amount=Sum("total_amount"))
    )
    targets = dict(SalesTarget.objects.filter(year=year, month=month, user_id__in=ids).values_list("user_id", "amount"))
    results = []
    for user in users:
        achieved = Decimal(sold.get(user.pk) or 0).quantize(MONEY_QUANTUM)
        target = targets.get(user.pk)
        results.append({
            "user_id": user.pk,
            "name": user.get_full_name() or user.username,
            "target": target,
            "achieved": achieved,
            "percent": _percent(achieved, target),
        })
    # Furthest along first; those without a target last, by what they sold.
    results.sort(key=lambda row: (row["target"] is None, -(row["percent"] or 0), -row["achieved"], row["user_id"]))
    total_target = sum((row["target"] for row in results if row["target"] is not None), start=Decimal("0.00"))
    achieved_with_target = sum((row["achieved"] for row in results if row["target"] is not None), start=Decimal("0.00"))
    return {
        "year": year,
        "month": month,
        "label": f"{jalali.JALALI_MONTHS[month - 1]} {jalali.to_persian_digits(str(year))}",
        "period_start": format_utc_timestamp(start),
        "period_end": format_utc_timestamp(end),
        "can_manage": has_any_capability(actor, "sales_targets.manage"),
        "totals": {
            "target": total_target,
            "achieved": achieved_with_target,
            "percent": _percent(achieved_with_target, total_target),
            "with_target": sum(1 for row in results if row["target"] is not None),
        },
        "results": results,
    }
