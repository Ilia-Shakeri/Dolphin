"""Template filters that render a stored Gregorian value as Jalali.

Presentation only (`BIZ-007`). The model field, the serializer, and every
`/api/v1/` response keep the canonical Gregorian ISO value; these filters exist
so a template never has to know how the conversion works, and so there is one
place to change it.
"""

from django import template

from common import jalali


register = template.Library()


@register.filter(name="jalali")
def jalali_date(value):
    """`۱۴۰۵/۰۵/۲۵`, or an empty string for a missing value."""
    try:
        return jalali.format_date(value)
    except (ValueError, TypeError, AttributeError):
        # A template must not raise over an unexpected value; showing nothing is
        # better than a 500 on a printed invoice.
        return ""


@register.filter(name="jalali_datetime")
def jalali_datetime(value):
    """`۱۴۰۵/۰۵/۲۵ ۱۴:۳۰` in Tehran local time."""
    try:
        return jalali.format_datetime(value)
    except (ValueError, TypeError, AttributeError):
        return ""


@register.filter(name="jalali_long")
def jalali_long(value):
    """`۲۵ مرداد ۱۴۰۵`, for a document heading."""
    try:
        return jalali.format_long_date(value)
    except (ValueError, TypeError, AttributeError):
        return ""
