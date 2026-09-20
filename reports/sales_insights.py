"""One seller's confirmed-sales trend — the profile page's chart.

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
from django.utils import timezone

from reports.ranges import (
    GRANULARITIES,
    MAX_BUCKETS,
    bucket_key,
    bucket_sequence,
    granularity_for,
    truncation_for,
)
from reports.selectors import users_for_performance_report
from sales.models import Sale
from sales.selectors import sales_for


#: `GRANULARITIES`, `MAX_BUCKETS` and the four bucket helpers are imported
#: above rather than defined here. Until 2.11.0 this module carried its own
#: copy of all six, identical line for line to `customer_insights`' — which
#: is how one of the two could gain a granularity the other did not.
MONEY_QUANTUM = Decimal("0.01")


class InvalidReportPeriod(Exception):
    """The requested window or granularity cannot be charted."""


class InvalidReportUser(Exception):
    """`user_id` is not inside the actor's report scope."""


def build_sales_growth_report(
    *, actor, user_id, granularity=None, period_start=None, period_end=None
):
    """Confirmed sales for `user_id`, bucketed, within the actor's report scope.

    Defaults to the last 365 days, exactly as the customer growth chart does —
    the same "a year, by month" starting point a reader of either chart already
    expects.
    """
    if granularity is not None and granularity not in GRANULARITIES:
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
    # See `build_customer_growth_report`: the window is what the reader picks,
    # the bucket width is what `reports.ranges` derives from it.
    if granularity is None:
        granularity = granularity_for(period_start, period_end)

    scoped = sales_for(actor).filter(sold_by_id=user_id, status=Sale.Status.CONFIRMED)
    truncate = truncation_for(granularity)
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
            per_bucket[bucket_key(granularity, row["bucket"])] = (
                row["count"],
                Decimal(row["amount"] or 0).quantize(MONEY_QUANTUM),
            )

    results = []
    if per_bucket:
        sequence = bucket_sequence(granularity, min(per_bucket), max(per_bucket))
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
