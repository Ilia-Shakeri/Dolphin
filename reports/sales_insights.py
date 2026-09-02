"""One seller's confirmed-sales trend, by week or month — the profile page's chart.

Built the same way `reports.customer_insights.build_customer_growth_report`
builds a customer trend: bucket by a truncated timestamp, emit every bucket
between the first and last one that has data (an empty bucket is drawn as
zero, never skipped, so the line between two points always spans the same
amount of time), and stop at a bounded number of buckets so the request is
refused rather than rendered unreadable.

The one thing this adds beyond that: whose sales it is allowed to sum.
`sales_for(actor)` alone would let an elevated role sum the whole company —
correct for the company report, wrong for one seller's own page — so the
target `user_id` must additionally sit inside
`reports.selectors.users_for_performance_report(actor)`, the exact scope the
user-performance report itself already enforces. A Sales Agent's own scope
there is themselves alone, so this refuses them a trend for anyone else; an
elevated role's scope is the whole company, so this accepts any seller in it.
"""

from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone

from reports.selectors import users_for_performance_report
from sales.models import Sale
from sales.selectors import sales_for


GRANULARITIES = ("week", "month")
#: A bounded window, matching `customer_insights.MAX_BUCKETS` — a chart of six
#: hundred weekly points is not a chart, and the request is refused rather
#: than rendered unreadable.
MAX_BUCKETS = 120

MONEY_QUANTUM = Decimal("0.01")


class InvalidReportPeriod(Exception):
    """The requested window or granularity cannot be charted."""


class InvalidReportUser(Exception):
    """`user_id` is not inside the actor's report scope."""


def _truncation(granularity):
    return TruncWeek if granularity == "week" else TruncMonth


def _next_bucket(granularity, bucket):
    if granularity == "week":
        return bucket + timedelta(days=7)
    if bucket.month == 12:
        return bucket.replace(year=bucket.year + 1, month=1, day=1)
    return bucket.replace(month=bucket.month + 1, day=1)


def _bucket_sequence(granularity, first, last):
    buckets = []
    cursor = first
    while cursor <= last and len(buckets) <= MAX_BUCKETS:
        buckets.append(cursor)
        cursor = _next_bucket(granularity, cursor)
    return buckets


def build_sales_growth_report(
    *, actor, user_id, granularity="month", period_start=None, period_end=None
):
    """Confirmed sales for `user_id`, bucketed, within the actor's report scope.

    Defaults to the last 365 days, exactly as the customer growth chart does —
    the same "a year, by month" starting point a reader of either chart already
    expects.
    """
    if granularity not in GRANULARITIES:
        raise InvalidReportPeriod("سطح تجمیع نامعتبر است.")
    if not users_for_performance_report(actor).filter(pk=user_id).exists():
        raise InvalidReportUser

    now = timezone.now()
    if period_end is None:
        period_end = now
    if period_start is None:
        period_start = period_end - timedelta(days=365)
    if period_start >= period_end:
        raise InvalidReportPeriod("تاریخ شروع دوره باید قبل از تاریخ پایان آن باشد.")

    scoped = sales_for(actor).filter(sold_by_id=user_id, status=Sale.Status.CONFIRMED)
    truncate = _truncation(granularity)
    grouped = (
        scoped.filter(sold_at__gte=period_start, sold_at__lt=period_end)
        .annotate(bucket=truncate("sold_at"))
        .values("bucket")
        .annotate(count=Count("id"), amount=Sum("total_amount"))
        .order_by("bucket")
    )
    per_bucket = OrderedDict()
    for row in grouped:
        if row["bucket"] is not None:
            per_bucket[row["bucket"].date()] = (
                row["count"],
                Decimal(row["amount"] or 0).quantize(MONEY_QUANTUM),
            )

    results = []
    if per_bucket:
        sequence = _bucket_sequence(granularity, min(per_bucket), max(per_bucket))
        if len(sequence) > MAX_BUCKETS:
            raise InvalidReportPeriod(
                "این بازه برای رسم نمودار با این سطح تجمیع بیش از حد طولانی است."
            )
        zero = (0, Decimal("0.00"))
        for bucket in sequence:
            count, amount = per_bucket.get(bucket, zero)
            results.append({"bucket": bucket.isoformat(), "sales_count": count, "sales_amount": amount})

    return {
        "user_id": user_id,
        "granularity": granularity,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "results": results,
    }
