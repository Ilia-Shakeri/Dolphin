"""Two aggregate readings of the customer book.

Both are built on `sales.selectors.customers_for`, never on `Customer.objects`.
That is the whole of the scope story: a marketer's chart counts the customers a
marketer can list and nothing else, and it stays that way automatically if the
scope rule ever changes, because there is no second copy of it here.

Neither reading invents a business rule. One counts customers per city, the
other counts customers per time bucket by the date they were registered. No
revenue, no status, no derived meaning.
"""

from collections import OrderedDict
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone

from sales.selectors import customers_for


#: How a growth series may be bucketed. Week and month are the two the panel
#: offers; a custom range narrows the window but still buckets by one of these,
#: because a bucket has to be a fixed width for the line between two points to
#: mean anything.
GRANULARITIES = ("week", "month")
#: A bounded window. A growth chart is a picture, and a picture of six hundred
#: weekly points is not one — the request is refused rather than rendered
#: unreadable.
MAX_BUCKETS = 120
#: Cities to name individually before the rest are grouped. A distribution with
#: forty slices communicates nothing; the tail is real and is reported as one
#: labelled row rather than dropped.
TOP_CITIES = 12


class InvalidReportPeriod(Exception):
    """The requested window cannot be charted."""


def _city_label(customer):
    """What to file this customer under.

    City first, province where the city was never filled in, and an explicit
    "not recorded" bucket last. Falling back silently to province would make a
    customer with no city look like one entered carefully at province level, and
    dropping them entirely would make the percentages lie.
    """
    city = (customer.city or "").strip()
    if city:
        return city
    province = (customer.province or "").strip()
    if province:
        return province
    return ""


def build_customer_city_report(*, actor):
    """Customers per city, largest first, with a tail and a percentage each.

    Percentages are computed against the total this actor can see, so they read
    as "of my customers" rather than "of the company's" — which is what a
    marketer looking at their own book means by it.
    """
    counts = {}
    unrecorded = 0
    total = 0
    for customer in customers_for(actor).only("city", "province"):
        total += 1
        label = _city_label(customer)
        if not label:
            unrecorded += 1
            continue
        counts[label] = counts.get(label, 0) + 1

    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    rows = []
    for label, count in ordered[:TOP_CITIES]:
        rows.append({"label": label, "count": count})

    remainder = sum(count for _, count in ordered[TOP_CITIES:])
    if remainder:
        rows.append({"label": "سایر شهرها", "count": remainder, "is_aggregate": True})
    if unrecorded:
        rows.append({"label": "ثبت‌نشده", "count": unrecorded, "is_aggregate": True})

    for row in rows:
        # Rounded for display only. They are not re-summed anywhere, so a
        # rounding residue cannot turn into a wrong total.
        row["percent"] = round((row["count"] / total) * 100, 1) if total else 0.0
        row.setdefault("is_aggregate", False)

    return {
        "total": total,
        "distinct_cities": len(counts),
        "results": rows,
    }


def _truncation(granularity):
    return TruncWeek if granularity == "week" else TruncMonth


def _next_bucket(granularity, bucket):
    """The bucket immediately after this one."""
    if granularity == "week":
        return bucket + timedelta(days=7)
    if bucket.month == 12:
        return bucket.replace(year=bucket.year + 1, month=1, day=1)
    return bucket.replace(month=bucket.month + 1, day=1)


def _bucket_sequence(granularity, first, last):
    """Every bucket from `first` to `last`, including the empty ones.

    A series that skips its empty buckets draws a straight line across the gap,
    which reads as steady growth over months where nothing happened. The zeros
    are the honest picture.
    """
    buckets = []
    cursor = first
    while cursor <= last and len(buckets) <= MAX_BUCKETS:
        buckets.append(cursor)
        cursor = _next_bucket(granularity, cursor)
    return buckets


def build_customer_growth_report(*, actor, granularity="month", period_start=None, period_end=None):
    """How many customers were registered in each bucket, and the running total.

    Two series from one pass, because they answer different questions and a
    reader asks both: `count` is how many arrived in that bucket, `cumulative`
    is how large the book had become by the end of it. A chart of only the first
    hides a shrinking intake behind a growing business; a chart of only the
    second hides the intake entirely.

    Buckets with no registrations are emitted as zero rather than skipped. A
    line drawn between two points that are three months apart while every other
    gap is one month is a lie about the slope.
    """
    if granularity not in GRANULARITIES:
        raise InvalidReportPeriod("سطح تجمیع نامعتبر است.")

    now = timezone.now()
    if period_end is None:
        period_end = now
    if period_start is None:
        period_start = period_end - timedelta(days=365)
    if period_start >= period_end:
        raise InvalidReportPeriod("تاریخ شروع دوره باید قبل از تاریخ پایان آن باشد.")

    scoped = customers_for(actor)
    truncate = _truncation(granularity)
    grouped = (
        scoped.filter(created_at__gte=period_start, created_at__lt=period_end)
        .annotate(bucket=truncate("created_at"))
        .values("bucket")
        .annotate(count=Count("id"))
        .order_by("bucket")
    )
    per_bucket = OrderedDict()
    for row in grouped:
        if row["bucket"] is not None:
            per_bucket[row["bucket"].date()] = row["count"]

    # Everything registered before the window, so the cumulative line starts
    # where the book actually stood rather than at zero.
    running = scoped.filter(created_at__lt=period_start).count()

    results = []
    if per_bucket:
        sequence = _bucket_sequence(granularity, min(per_bucket), max(per_bucket))
        if len(sequence) > MAX_BUCKETS:
            raise InvalidReportPeriod(
                "این بازه برای رسم نمودار با این سطح تجمیع بیش از حد طولانی است."
            )
        for bucket in sequence:
            count = per_bucket.get(bucket, 0)
            running += count
            results.append({
                "bucket": bucket.isoformat(),
                "count": count,
                "cumulative": running,
            })

    return {
        "granularity": granularity,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "opening_total": results[0]["cumulative"] - results[0]["count"] if results else running,
        "closing_total": running,
        "results": results,
    }
