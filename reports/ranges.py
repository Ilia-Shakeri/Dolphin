"""The one place a time window becomes a row of chart buckets.

Every line chart in the panel asks the same two questions — *which window* and
*how wide is a bucket* — and until 2.11.0 two modules answered them with two
copies of the same four helpers. `customer_insights` and `sales_insights` each
had their own `GRANULARITIES`, `_truncation`, `_next_bucket`, `_bucket_sequence`
and `MAX_BUCKETS`, identical line for line, which is exactly the duplication
that goes wrong the first time one of them gains a granularity the other does
not. Both now read this module.

Two rules live here and nowhere else.

**The bucket width is derived from the window, not chosen beside it.** The
panel's shared range filter offers windows — today, a week, thirty days, three
months, a year, a custom pair — because that is what a reader actually picks.
"Weekly or monthly" was never the question they were asking; it is a
consequence of how much time is on screen, and a consequence belongs in one
function (`granularity_for`) rather than in each caller's UI. The endpoints
still accept an explicit `granularity` for anything that genuinely needs to
override the derivation, and derive it when none is given.

**A bucket count is bounded.** `MAX_BUCKETS` is what stops a request for ten
years of daily points from being answered with an unreadable picture; the
thresholds in `granularity_for` are chosen so that a derived granularity can
never exceed it, and an explicit one that would is refused by the caller.
"""

from datetime import date, datetime, timedelta

from django.db.models.functions import TruncDay, TruncHour, TruncMonth, TruncWeek
from django.utils import timezone


#: Bucket widths, narrowest first. The order is load-bearing: `granularity_for`
#: walks `_THRESHOLDS` in the same order and returns the first that fits.
GRANULARITIES = ("hour", "day", "week", "month")

#: How many buckets before a chart stops being a picture. Six hundred weekly
#: points is not one, so the request is refused rather than rendered
#: unreadable. Every derived granularity stays under this by construction —
#: see `_THRESHOLDS`.
MAX_BUCKETS = 120

#: (granularity, the longest window it may cover). A window longer than the
#: last threshold falls through to `month`, which at `MAX_BUCKETS` covers ten
#: years. Each pair is chosen so `span / bucket <= MAX_BUCKETS`:
#: 2 days of hours is 48, 62 days is 62, 730 days of weeks is ~105.
_THRESHOLDS = (
    ("hour", timedelta(days=2)),
    ("day", timedelta(days=62)),
    ("week", timedelta(days=730)),
)

_TRUNCATIONS = {
    "hour": TruncHour,
    "day": TruncDay,
    "week": TruncWeek,
    "month": TruncMonth,
}


def granularity_for(period_start, period_end):
    """How wide a bucket should be to draw `period_start`→`period_end` well.

    A day of data wants hours; a year wants months. Between those the choice is
    the one that leaves a readable number of points on screen — enough for the
    line to have a shape, few enough that the x-axis can be labelled.
    """
    span = period_end - period_start
    for granularity, longest in _THRESHOLDS:
        if span <= longest:
            return granularity
    return "month"


def truncation_for(granularity):
    """The database function that snaps a timestamp to its bucket's start."""
    return _TRUNCATIONS[granularity]


def bucket_key(granularity, value):
    """The dictionary key for a truncated timestamp.

    An hourly bucket has to stay a datetime — `.date()` would collapse a whole
    day's twenty-four buckets into one — while every wider bucket is a calendar
    date and is easier to compare, print and step as one. Which of the two a
    caller gets is decided here rather than at each of the three call sites.
    """
    if granularity == "hour":
        return timezone.localtime(value).replace(minute=0, second=0, microsecond=0)
    return value.date() if isinstance(value, datetime) else value


def next_bucket(granularity, bucket):
    """The bucket immediately after this one."""
    if granularity == "hour":
        return bucket + timedelta(hours=1)
    if granularity == "day":
        return bucket + timedelta(days=1)
    if granularity == "week":
        return bucket + timedelta(days=7)
    if bucket.month == 12:
        return bucket.replace(year=bucket.year + 1, month=1, day=1)
    return bucket.replace(month=bucket.month + 1, day=1)


def bucket_sequence(granularity, first, last):
    """Every bucket from `first` to `last`, including the empty ones.

    A series that skips its empty buckets draws a straight line across the gap,
    which reads as steady growth over months where nothing happened. The zeros
    are the honest picture.

    One more than `MAX_BUCKETS` is produced deliberately: callers test the
    length against the cap and refuse, and a sequence that stopped exactly at
    the cap would be indistinguishable from one that happened to fit.
    """
    buckets = []
    cursor = first
    while cursor <= last and len(buckets) <= MAX_BUCKETS:
        buckets.append(cursor)
        cursor = next_bucket(granularity, cursor)
    return buckets


def bucket_label_value(bucket):
    """What a bucket key means to the panel's Jalali formatters.

    `common.jalali.format_date` takes a date and `format_datetime` a datetime,
    and an hourly bucket needs the second. Returning the key unchanged and
    letting the caller pick would put that branch in every caller, so the
    branch is here and the caller asks for a label instead.
    """
    from common.jalali import format_date, format_datetime

    if isinstance(bucket, datetime):
        return format_datetime(bucket)
    if isinstance(bucket, date):
        return format_date(bucket)
    return str(bucket)


def local_bucket_starts(granularity, period_start, period_end):
    """Every bucket start in the window, in local time, oldest first.

    The companion to `truncation_for` for the callers that bucket in Python
    rather than in SQL. `reports.list_charts` is the one that does, for the
    reason `common/dashboard.py` already records for its own trend: this
    codebase runs on PostgreSQL in production and SQLite in development, and
    the two disagree about where a week starts. Doing the arithmetic here
    keeps that disagreement out of the answer entirely — and keeps it out of
    one place rather than three.

    The first bucket is the one containing `period_start`, snapped back to its
    own start, so the window always begins on a whole bucket.
    """
    start = _snap(granularity, timezone.localtime(period_start))
    end = timezone.localtime(period_end)
    starts = []
    cursor = start
    while cursor < end and len(starts) <= MAX_BUCKETS:
        starts.append(cursor)
        cursor = next_bucket(granularity, cursor)
    return starts


def _snap(granularity, moment):
    """`moment` moved back to the start of the bucket it falls in."""
    if granularity == "hour":
        return moment.replace(minute=0, second=0, microsecond=0)
    midnight = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "day":
        return midnight
    if granularity == "week":
        # Python's Monday-first `weekday()`, matching `TruncWeek`, so a chart
        # bucketed here and one bucketed in SQL agree about which week a row
        # belongs to even though only one of them is used at a time.
        return midnight - timedelta(days=midnight.weekday())
    return midnight.replace(day=1)


def bucket_index(granularity, starts, moment):
    """Which bucket of `starts` a timestamp falls in, or `None` if outside.

    Index arithmetic rather than a search: every granularity but `month` has a
    fixed width, and a month's index is a calendar subtraction.
    """
    if not starts:
        return None
    local = timezone.localtime(moment)
    first = starts[0]
    if local < first:
        return None
    if granularity == "month":
        index = (local.year - first.year) * 12 + (local.month - first.month)
    elif granularity == "week":
        index = (local - first).days // 7
    elif granularity == "day":
        index = (local - first).days
    else:
        index = int((local - first).total_seconds()) // 3600
    return index if 0 <= index < len(starts) else None
