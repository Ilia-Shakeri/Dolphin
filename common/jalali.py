"""Jalali (Solar Hijri) calendar conversion, for presentation only.

`BIZ-007` is resolved as: the database and the versioned API stay Gregorian
ISO-8601 and timezone-aware, and **only what a Client-1 user reads or types** is
Jalali. Nothing here touches storage, and no value produced here is ever written
back to a model or returned from `/api/v1/`.

**No legal, tax, or accounting compliance is claimed.** This converts one
calendar to another and formats the result; it does not decide which calendar an
invoice is legally dated in.

Why the arithmetic is here rather than from a package: the conversion is exact
integer arithmetic over a fixed 33-year leap cycle, roughly forty lines, and
fully checkable against published reference dates — unlike Persian *text*
shaping, which is why `common/pdf.py` refuses to hand-roll its own engine. Adding
a dependency would mean regenerating the hash-pinned lock on a Linux host
(`docs/ops/DEPENDENCIES.md`) for something this small.

The frontend performs the same conversion in `forooshbin-app.js`; the two are held
to the same reference vectors by `common/tests/test_jalali.py`.
"""

import datetime
import unicodedata
import zoneinfo


#: The operational timezone for Client-1. Every naive-looking calendar date a
#: user sees is the date it was in Tehran, not in UTC.
OPERATIONAL_TIMEZONE = zoneinfo.ZoneInfo("Asia/Tehran")

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_LATIN_TO_PERSIAN = {str(index): digit for index, digit in enumerate(PERSIAN_DIGITS)}

JALALI_MONTHS = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)

#: 1 Farvardin 1 in the proleptic Gregorian calendar. This exact anchor is what
#: makes the conversion agree with ICU day for day; it is verified against
#: 16,801 ICU reference vectors in common/tests/test_jalali.py rather than
#: taken on trust.
JALALI_EPOCH_ORDINAL = datetime.date(622, 3, 21).toordinal()

# Days before the start of each Jalali month in a common year.
_JALALI_MONTH_OFFSETS = (0, 31, 62, 93, 124, 155, 186, 216, 246, 276, 306, 336)


def _is_jalali_leap(year):
    """A Jalali year is a leap year on 8 of every 33 years.

    Using the 33-year cycle residues rather than an approximation keeps the
    conversion exact for the range this product will ever see.
    """
    return (((year + 12) % 33) % 4) == 1


def _jalali_year_length(year):
    return 366 if _is_jalali_leap(year) else 365


def to_jalali(value):
    """Gregorian `date` → `(jalali_year, jalali_month, jalali_day)`."""
    gregorian_ordinal = value.toordinal()
    days = gregorian_ordinal - JALALI_EPOCH_ORDINAL
    if days < 0:
        raise ValueError("Dates before the Jalali epoch are out of range.")
    year = 1
    while True:
        length = _jalali_year_length(year)
        if days < length:
            break
        days -= length
        year += 1
    for index in range(11, -1, -1):
        if days >= _JALALI_MONTH_OFFSETS[index]:
            month = index + 1
            day = days - _JALALI_MONTH_OFFSETS[index] + 1
            # The 12th month carries the leap day, so only it can reach 30.
            return year, month, day
    raise ValueError("Unreachable: month offset table is exhaustive.")


#: A plausible Jalali year for business data. The bound exists to catch a
#: *Gregorian* value typed or pasted into a Jalali field: 2026 is a valid
#: Jalali year arithmetically, but it means 2647 CE, and accepting it silently
#: would store a date six centuries out with no visible complaint.
MIN_JALALI_YEAR = 1200
MAX_JALALI_YEAR = 1700


def from_jalali(year, month, day):
    """`(jalali_year, jalali_month, jalali_day)` → Gregorian `date`."""
    year, month, day = int(year), int(month), int(day)
    if not MIN_JALALI_YEAR <= year <= MAX_JALALI_YEAR:
        raise ValueError(
            f"Jalali year must be between {MIN_JALALI_YEAR} and {MAX_JALALI_YEAR}; "
            "a Gregorian year here would mean a date centuries away."
        )
    if not 1 <= month <= 12:
        raise ValueError("Jalali month must be between 1 and 12.")
    month_length = 31 if month <= 6 else 30
    if month == 12:
        month_length = 30 if _is_jalali_leap(year) else 29
    if not 1 <= day <= month_length:
        raise ValueError("Jalali day is out of range for that month.")

    days = sum(_jalali_year_length(each) for each in range(1, year))
    days += _JALALI_MONTH_OFFSETS[month - 1] + day - 1
    return datetime.date.fromordinal(JALALI_EPOCH_ORDINAL + days)


def to_persian_digits(text):
    """Latin digits → Persian digits, leaving everything else alone."""
    return "".join(_LATIN_TO_PERSIAN.get(character, character) for character in str(text))


def to_latin_digits(text):
    """Persian and Arabic-Indic digits → Latin, for parsing typed input."""
    result = []
    for character in str(text):
        if character.isdigit():
            # `unicodedata.digit` maps every Unicode digit form to its value,
            # so Persian ۱ and Arabic-Indic ١ both normalise here.
            result.append(str(unicodedata.digit(character)))
        else:
            result.append(character)
    return "".join(result)


def _coerce(value):
    """Accept the canonical representations a stored value arrives in.

    Report fields and query echoes carry the ISO *text* rather than a
    `datetime`, because that is what crossed the API. Parsing it here keeps
    every caller from having to know which of the two it holds.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # `fromisoformat` in 3.11+ accepts the trailing Z form.
        return datetime.datetime.fromisoformat(text)
    return value


def _as_local_date(value):
    """Take the calendar date this instant fell on in the operational zone."""
    value = _coerce(value)
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(OPERATIONAL_TIMEZONE)
        return value.date(), value
    return value, None


def format_date(value, *, persian_digits=True):
    """A Gregorian date or datetime as `۱۴۰۵/۰۵/۲۵`."""
    if value in (None, ""):
        return ""
    local_date, _ = _as_local_date(value)
    if local_date is None:
        return ""
    year, month, day = to_jalali(local_date)
    text = f"{year:04d}/{month:02d}/{day:02d}"
    return to_persian_digits(text) if persian_digits else text


def format_datetime(value, *, persian_digits=True):
    """A Gregorian datetime as `۱۴۰۵/۰۵/۲۵ ۱۴:۳۰`, in Tehran local time."""
    if value in (None, ""):
        return ""
    local_date, local_datetime = _as_local_date(value)
    if local_date is None:
        return ""
    if local_datetime is None:
        return format_date(value, persian_digits=persian_digits)
    year, month, day = to_jalali(local_date)
    text = f"{year:04d}/{month:02d}/{day:02d} {local_datetime.hour:02d}:{local_datetime.minute:02d}"
    return to_persian_digits(text) if persian_digits else text


def format_long_date(value, *, persian_digits=True):
    """A Gregorian date as `۲۵ مرداد ۱۴۰۵`, for a document heading."""
    if value in (None, ""):
        return ""
    local_date, _ = _as_local_date(value)
    if local_date is None:
        return ""
    year, month, day = to_jalali(local_date)
    text = f"{day} {JALALI_MONTHS[month - 1]} {year}"
    return to_persian_digits(text) if persian_digits else text


def parse_date(text):
    """`۱۴۰۵/۰۵/۲۵` (or Latin digits, or `-` separators) → Gregorian `date`.

    Raises `ValueError` on anything it cannot read, so a caller never has to
    guess whether a returned value was understood.
    """
    if text in (None, ""):
        return None
    normalized = to_latin_digits(str(text)).strip().replace("-", "/").replace(".", "/")
    parts = [part for part in normalized.split("/") if part != ""]
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("A Jalali date must look like 1405/05/25.")
    return from_jalali(*parts)
