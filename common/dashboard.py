"""What the home page shows each role, beyond a row of bare counts.

Product-owner request (2026-09-04): the dashboard was the weakest surface in
the panel relative to everything around it — four tiles carrying a count, one
performance panel, and (for a marketer) a work queue. Every other page had
charts, filters and real figures; the first page anyone sees had the least.

This module answers three questions per role, and the answers differ by
role because the questions do:

* **KPIs** — a figure with a *comparison*, not a bare count. "۳۷٬۰۰۰٬۰۰۰
  ریال this month" says little; "…, ۱۲٪ more than last month" says what a
  reader actually wanted to know.
* **Trend** — sales over the last twelve weeks, so direction is visible
  without opening a report.
* **Breakdown** — where the work is sitting: leads by status for the sales
  side, after-sales cases by status for the after-sales side.

The same three shapes as `reminders`, `search` and `customer_timeline`, for
the same reasons: no new table, nothing stored, object scope taken from each
module's own selector, and only feature availability checked here. A role
that cannot see sales simply has no sales KPI and no trend — the panel is
assembled from what that reader may see, never filtered afterwards.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from accounts.models import User
from aftersales.selectors import after_sales_requests_for
from billing.selectors import invoices_for
from common import formatting
from common.deployment.profile import feature_enabled
from sales.models import Lead, Sale
from sales.selectors import interactions_for, leads_for, sales_for

#: Weeks on the trend chart. A quarter is long enough to show a direction and
#: short enough that the most recent weeks are still legible.
TREND_WEEKS = 12

#: Slices before the breakdown stops being readable.
BREAKDOWN_LIMIT = 6


def _kpi(key, label, *, display, hint="", icon="ki-element-11", icon_paths=4, accent="primary", url=None):
    return {
        "key": key,
        "label": label,
        "display": display,
        "hint": hint,
        "icon": icon,
        "icon_paths": icon_paths,
        "accent": accent,
        "url": url,
    }


def _month_bounds(now):
    """This month so far, and the same span of the month before it.

    Compared against the *same number of days* into the previous month, not
    the whole of it: on the 3rd, "this month vs last month" would otherwise
    read as a collapse every single time.
    """
    local = timezone.localtime(now)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=local.day - 1)
    elapsed = now - start
    previous_start = (start - timedelta(days=1)).replace(day=1)
    return start, previous_start, previous_start + elapsed


def _change_hint(current, previous, *, noun):
    """«۱۲٪ بیشتر از ماه گذشته», or a plain statement when there is no base."""
    if previous and previous > 0:
        percent = int(round((current - previous) / previous * 100))
        if percent == 0:
            return f"مثل {noun} گذشته"
        direction = "بیشتر" if percent > 0 else "کمتر"
        return f"{formatting.persian_digits(abs(percent))}٪ {direction} از {noun} گذشته"
    if current:
        return f"در {noun} گذشته چیزی ثبت نشده بود"
    return f"در این {noun} چیزی ثبت نشده"


def _sales_kpis(user, *, now):
    scope = sales_for(user).exclude(status=Sale.Status.CANCELLED)
    start, previous_start, previous_end = _month_bounds(now)
    this_month = scope.filter(sold_at__gte=start)
    last_month = scope.filter(sold_at__gte=previous_start, sold_at__lt=previous_end)
    amount = this_month.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    previous = last_month.aggregate(total=Sum("total_amount"))["total"] or Decimal("0")
    count = this_month.count()
    return [
        _kpi(
            "sales_amount_this_month", "فروش این ماه",
            display=formatting.money(amount),
            hint=_change_hint(amount, previous, noun="ماه"),
            icon="ki-chart-line-up", icon_paths=2, accent="success", url="/sales/",
        ),
        _kpi(
            "sales_count_this_month", "تعداد فروش این ماه",
            display=formatting.persian_digits(count),
            hint=_change_hint(count, last_month.count(), noun="ماه"),
            icon="ki-basket", icon_paths=4, accent="primary", url="/sales/",
        ),
    ]


def _receivables_kpi(user, *, now):
    """What is still owed, across every issued invoice this reader may see.

    Summed in Python rather than in SQL because `balance_due` is a property
    that honours `is_manually_settled` — a manually settled invoice owes
    nothing even though its stored columns still show a figure. A `Sum()`
    over the columns would quietly disagree with every other page.
    """
    invoices = invoices_for(user).filter(status="issued")
    outstanding = sum((invoice.balance_due for invoice in invoices), Decimal("0"))
    unpaid = sum(1 for invoice in invoices if invoice.balance_due > 0)
    return [
        _kpi(
            "outstanding", "مطالبات باز",
            display=formatting.money(outstanding),
            hint=f"{formatting.persian_digits(unpaid)} فاکتور تسویه‌نشده",
            icon="ki-wallet", icon_paths=4, accent="warning", url="/reports/receivables/",
        )
    ]


def _call_kpi(user, *, now):
    week_start = timezone.localtime(now) - timedelta(days=7)
    previous_start = week_start - timedelta(days=7)
    scope = interactions_for(user)
    this_week = scope.filter(occurred_at__gte=week_start).count()
    last_week = scope.filter(occurred_at__gte=previous_start, occurred_at__lt=week_start).count()
    return [
        _kpi(
            "calls_this_week", "تماس‌های هفت روز اخیر",
            display=formatting.persian_digits(this_week),
            hint=_change_hint(this_week, last_week, noun="هفته"),
            icon="ki-call", icon_paths=8, accent="info", url="/interactions/",
        )
    ]


def _after_sales_kpis(user, *, now):
    scope = after_sales_requests_for(user)
    open_cases = scope.filter(closed_at__isnull=True)
    start, _previous_start, _previous_end = _month_bounds(now)
    return [
        _kpi(
            "after_sales_open", "پرونده‌های باز",
            display=formatting.persian_digits(open_cases.count()),
            hint=(
                f"{formatting.persian_digits(open_cases.filter(next_appointment_at__isnull=False).count())}"
                " مورد با قرار ثبت‌شده"
            ),
            icon="ki-wrench", icon_paths=2, accent="danger", url="/after-sales/",
        ),
        _kpi(
            "after_sales_closed_this_month", "بسته‌شده در این ماه",
            display=formatting.persian_digits(scope.filter(closed_at__gte=start).count()),
            hint="از ابتدای ماه جاری",
            icon="ki-check-circle", icon_paths=2, accent="success", url="/after-sales/",
        ),
    ]


def _sales_trend(user, *, now):
    """Sales amount per week for the last twelve weeks, oldest first.

    Bucketed in Python over one ordered query rather than with a database
    date-truncation function: this codebase runs on PostgreSQL in production
    and SQLite in development and tests, and the two disagree about week
    boundaries. Twelve buckets over one indexed range scan is not worth a
    dialect-specific query.
    """
    local_now = timezone.localtime(now)
    start_of_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    first_bucket_start = start_of_today - timedelta(weeks=TREND_WEEKS - 1, days=local_now.weekday())
    rows = (
        sales_for(user)
        .exclude(status=Sale.Status.CANCELLED)
        .filter(sold_at__gte=first_bucket_start)
        .values_list("sold_at", "total_amount")
    )
    buckets = [Decimal("0")] * TREND_WEEKS
    for sold_at, amount in rows:
        index = (timezone.localtime(sold_at) - first_bucket_start).days // 7
        if 0 <= index < TREND_WEEKS:
            buckets[index] += amount or Decimal("0")
    points = []
    for index, amount in enumerate(buckets):
        week_start = first_bucket_start + timedelta(weeks=index)
        points.append({
            "label": _jalali_day(week_start),
            "value": float(amount),
            "display": formatting.money(amount),
        })
    total = sum(buckets, Decimal("0"))
    return {
        "title": "روند فروش دوازده هفتهٔ اخیر",
        "points": points,
        "summary": f"مجموع این بازه: {formatting.money(total)}",
    }


def _jalali_day(value):
    from common.jalali import format_date

    return format_date(value)


def _lead_breakdown(user):
    rows = (
        leads_for(user)
        .values("status")
        .annotate(total=Count("id"))
        .order_by("-total")[:BREAKDOWN_LIMIT]
    )
    labels = dict(Lead.Status.choices)
    items = [
        {
            "label": labels.get(row["status"], row["status"] or "بدون وضعیت"),
            "value": row["total"],
            "display": formatting.persian_digits(row["total"]),
        }
        for row in rows
    ]
    return {"title": "سرنخ‌ها به تفکیک وضعیت", "items": items, "url": "/leads/"}


def _after_sales_breakdown(user):
    rows = (
        after_sales_requests_for(user)
        .values("status")
        .annotate(total=Count("id"))
        .order_by("-total")[:BREAKDOWN_LIMIT]
    )
    items = [
        {
            "label": row["status"] or "بدون وضعیت",
            "value": row["total"],
            "display": formatting.persian_digits(row["total"]),
        }
        for row in rows
    ]
    return {"title": "پرونده‌ها به تفکیک وضعیت", "items": items, "url": "/after-sales/"}


def dashboard_for(user, *, now=None):
    """The role's own panel: KPIs, a trend, and a breakdown.

    Every part is optional. A reader who may see none of the sources gets
    empty lists and `None`s rather than an error, and the page simply does
    not render those sections — the same way a withheld feature leaves no
    trace anywhere else in the panel.
    """
    now = now or timezone.now()
    after_sales_side = (
        user.role == User.Role.SALES_AGENT and user.workstream == User.Workstream.AFTER_SALES
    )

    kpis = []
    if feature_enabled("sales") and sales_for(user).exists():
        kpis.extend(_sales_kpis(user, now=now))
    if feature_enabled("invoices") and invoices_for(user).exists():
        kpis.extend(_receivables_kpi(user, now=now))
    if feature_enabled("leads") and interactions_for(user).exists():
        kpis.extend(_call_kpi(user, now=now))
    if feature_enabled("after_sales") and after_sales_requests_for(user).exists():
        kpis.extend(_after_sales_kpis(user, now=now))

    trend = None
    if feature_enabled("sales") and sales_for(user).exists():
        trend = _sales_trend(user, now=now)

    breakdown = None
    if after_sales_side:
        if feature_enabled("after_sales") and after_sales_requests_for(user).exists():
            breakdown = _after_sales_breakdown(user)
    elif feature_enabled("leads") and leads_for(user).exists():
        breakdown = _lead_breakdown(user)

    return {"kpis": kpis, "trend": trend, "breakdown": breakdown}
