"""Deadlines in the company's working time (2.40.60, BIZ-008).

Product owner, 2026-10-17: «مهلت‌ها بر اساس ساعات و روزهای کاری تعریف‌شده
شرکت محاسبه شوند و تعطیلات رسمی، در صورت فعال بودن تنظیم مربوطه، از زمان
محاسبه حذف شوند».

A deadline is counted in working time only:

* `hour` — that many working hours from the moment the clock starts, carried
  over closed hours, closed days and (when the company counts them) holidays;
* `day` — the same clock time that many working days later; a start outside
  working hours begins at the next opening.

Everything is in Tehran time (`settings.TIME_ZONE`), the company's own day.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone

#: Python weekdays (Monday 0 … Sunday 6). The default week of an Iranian
#: office: Saturday to Wednesday 08:00–16:00, Thursday 08:00–13:00, Friday off.
DEFAULT_HOURS = {
    "5": ["08:00", "16:00"],
    "6": ["08:00", "16:00"],
    "0": ["08:00", "16:00"],
    "1": ["08:00", "16:00"],
    "2": ["08:00", "16:00"],
    "3": ["08:00", "13:00"],
}
MAX_DAYS_SCANNED = 800


def _parse(value):
    hour, minute = (int(part) for part in str(value).split(":"))
    return time(hour, minute)


class WorkingTime:
    """The company's week and holidays, for counting."""

    def __init__(self, hours=None, holidays=()):
        self.hours = {}
        for day, pair in (hours or DEFAULT_HOURS).items():
            start, end = _parse(pair[0]), _parse(pair[1])
            if end > start:
                self.hours[int(day)] = (start, end)
        self.holidays = set(holidays)

    def window(self, day):
        """`(open, close)` aware datetimes for a date, or `None` when closed."""
        if day in self.holidays or day.weekday() not in self.hours:
            return None
        start, end = self.hours[day.weekday()]
        zone = timezone.get_current_timezone()
        return (timezone.make_aware(datetime.combine(day, start), zone),
                timezone.make_aware(datetime.combine(day, end), zone))

    def _days_from(self, moment):
        day = timezone.localtime(moment).date()
        for offset in range(MAX_DAYS_SCANNED):
            current = day + timedelta(days=offset)
            window = self.window(current)
            if window is not None:
                yield current, window
        raise ValueError("no working day within the scanned range")

    def add_hours(self, start, hours):
        remaining = timedelta(hours=hours)
        for _day, (opens, closes) in self._days_from(start):
            begin = max(start, opens)
            if begin >= closes:
                continue
            available = closes - begin
            if remaining <= available:
                return begin + remaining
            remaining -= available
        raise ValueError("unreachable")

    def add_days(self, start, days):
        """The same working moment `days` working days later."""
        days_iter = self._days_from(start)
        first_day, (opens, closes) = next(days_iter)
        local = timezone.localtime(start)
        if local.date() != first_day or start < opens:
            clock = opens.timetz()
        elif start >= closes:
            first_day, (opens, closes) = next(days_iter)
            clock = opens.timetz()
        else:
            clock = local.timetz()
        counted = 0
        target = None
        for current, (day_opens, day_closes) in days_iter:
            counted += 1
            if counted == days:
                target = (current, day_opens, day_closes)
                break
        current, day_opens, day_closes = target
        moment = timezone.make_aware(datetime.combine(current, clock.replace(tzinfo=None)), timezone.get_current_timezone())
        return min(max(moment, day_opens), day_closes)

    def add(self, start, value, unit):
        if value is None:
            return None
        return self.add_hours(start, value) if unit == "hour" else self.add_days(start, value)
