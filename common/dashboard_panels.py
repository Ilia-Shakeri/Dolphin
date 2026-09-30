"""List-and-calendar dashboard widgets: tasks, chat, today, calls, month.

The insight grid used to hold only figures and charts. These are the other
family every dashboard product ships — a short list of what needs doing, who
wrote, what rang — built the same way as everything else on the page: real
rows from the owning module's own selector (so object scope is that module's,
not re-decided here), each gated by `feature_enabled(...)` and by the
reader's own capability, and never a placeholder. A reader with nothing to
show gets an honest empty state; a reader who may not use the module gets no
widget at all.

A panel is a plain dict: `key`, `family: "panel"`, `kind`, `title`, `icon`,
`icon_paths`, `accent`, `count`, `items`, `url`, `empty`. The page draws the
list from `items` (`title`, `meta`, `badge`, `tone`, `url`); `calendar` adds
its own month grid fields.
"""

import datetime

from django.db.models import F
from django.utils import timezone

from accounts.access import capabilities_for
from common.deployment.profile import feature_enabled
from common.jalali import JALALI_MONTHS, format_datetime, from_jalali, to_jalali, to_persian_digits

#: Rows a list widget shows. A dashboard box is a glance; the module's own
#: page is where the full list lives.
PANEL_ROWS = 6

#: Saturday-first, the Iranian week.
WEEKDAYS = ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه")


def _panel(key, kind, title, icon, icon_paths, accent, *, count, count_label, items, empty, url=None, **extra):
    return {
        "key": key,
        "family": "panel",
        "kind": kind,
        "title": title,
        "icon": icon,
        "icon_paths": icon_paths,
        "accent": accent,
        "count": count,
        "count_label": count_label,
        "items": items,
        "url": url,
        "empty": empty,
        **extra,
    }


def _tasks_panel(user, *, now):
    from tasks.models import Task
    from tasks.selectors import tasks_for

    from common.reminders import _task_url

    caps = capabilities_for(user)
    if "tasks.company" not in caps and "tasks.own" not in caps:
        return None
    open_tasks = tasks_for(user).filter(assignee=user, status=Task.Status.OPEN)
    rows = open_tasks.order_by(F("due_at").asc(nulls_last=True), "id")[:PANEL_ROWS]
    items = []
    for task in rows:
        overdue = task.due_at is not None and task.due_at < now
        items.append({
            "title": task.title,
            "meta": format_datetime(task.due_at) if task.due_at else "بدون موعد",
            "badge": "معوق" if overdue else None,
            "tone": "danger" if overdue else "primary",
            "url": _task_url(task),
        })
    return _panel(
        "panel_tasks", "list", "وظایف من", "di-check-circle", 2, "success",
        count=open_tasks.count(), count_label="باز", items=items, empty="وظیفهٔ بازی ندارید.",
        url=f"/users/{user.pk}/?tab=tasks",
    )


def _chat_panel(user):
    from chat.selectors import threads_for, total_unread_count
    from chat.serializers import serialize_threads

    threads = threads_for(user).prefetch_related("participants__user")[:PANEL_ROWS]
    items = []
    for row in serialize_threads(threads, viewer=user):
        body = row["last_message_body"] or "گفتگو شروع نشده است"
        unread = row["unread_count"]
        items.append({
            "title": row["peer"]["display_name"],
            "meta": body if len(body) <= 60 else f"{body[:60]}…",
            "badge": to_persian_digits(str(unread)) if unread else None,
            "tone": "danger",
            "url": "/chat/",
        })
    return _panel(
        "panel_chat", "list", "گفتگوهای اخیر", "di-message-text-2", 3, "info",
        count=total_unread_count(user), count_label="خوانده‌نشده", items=items, empty="هنوز گفتگویی ندارید.", url="/chat/",
    )


def _agenda_panel(user, *, now):
    from common.reminders import reminders_for

    local = timezone.localtime(now)
    year, month, day = to_jalali(local.date())
    result = reminders_for(user, now=now)
    items = []
    for group in result["groups"]:
        for item in group["items"]:
            due = datetime.datetime.fromisoformat(item["due_at"])
            if timezone.is_naive(due):
                due = timezone.make_aware(due)
            items.append({
                "title": item["title"],
                "meta": item.get("subtitle") or group["label"],
                "time": to_persian_digits(timezone.localtime(due).strftime("%H:%M")) if item.get("due_kind") == "datetime" else None,
                "badge": "معوق" if item["overdue"] else None,
                "tone": "danger" if item["overdue"] else "primary",
                "url": item.get("url"),
                "_due": due,
            })
    items.sort(key=lambda item: item["_due"])
    for item in items:
        del item["_due"]
    return _panel(
        "panel_agenda", "agenda", "برنامهٔ امروز", "di-calendar-tick", 6, "primary",
        count=result["count"], count_label="مورد", items=items[:PANEL_ROWS], empty="برای امروز کاری ندارید.",
        weekday=WEEKDAYS[(local.weekday() + 2) % 7],
        day=to_persian_digits(str(day)),
        month_name=JALALI_MONTHS[month - 1],
        year=to_persian_digits(str(year)),
    )


def _calendar_panel(user, *, now):
    from tasks.models import Task
    from tasks.selectors import tasks_for

    caps = capabilities_for(user)
    if "tasks.company" not in caps and "tasks.own" not in caps:
        return None
    local = timezone.localtime(now)
    year, month, today = to_jalali(local.date())
    first = from_jalali(year, month, 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    following = from_jalali(next_year, next_month, 1)
    days_in_month = (following - first).days
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.datetime.combine(first, datetime.time.min), tz)
    end = timezone.make_aware(datetime.datetime.combine(following, datetime.time.min), tz)
    due = tasks_for(user).filter(
        assignee=user, status=Task.Status.OPEN, due_at__gte=start, due_at__lt=end,
    ).values_list("due_at", flat=True)
    marked = sorted({to_jalali(timezone.localtime(value).date())[2] for value in due})
    return _panel(
        "panel_calendar", "calendar", "تقویم ماه", "di-calendar", 2, "warning",
        count=len(marked), count_label="روز دارای وظیفه", items=[], empty="", url=f"/users/{user.pk}/?tab=tasks",
        month_name=JALALI_MONTHS[month - 1],
        year=to_persian_digits(str(year)),
        weekdays=[name[0] for name in WEEKDAYS],
        offset=(first.weekday() + 2) % 7,
        days_in_month=days_in_month,
        today=today,
        marked=marked,
    )


def _calls_panel(user):
    from telephony.models import Call
    from telephony.selectors import calls_for

    caps = capabilities_for(user)
    if "calls.company" not in caps and "calls.own" not in caps:
        return None
    calls = calls_for(user).order_by("-started_at", "-id")
    items = []
    for call in calls[:PANEL_ROWS]:
        missed = call.status in {Call.Status.MISSED, Call.Status.NO_ANSWER, Call.Status.FAILED, Call.Status.BUSY}
        number = call.external_number or call.caller_raw or call.callee_raw
        items.append({
            "title": to_persian_digits(number) if number else "—",
            "meta": f"{call.get_direction_display()} · {format_datetime(call.started_at)}",
            "badge": call.get_status_display(),
            "tone": "danger" if missed else "success",
            "url": f"/customers/{call.person_id}/" if call.person_type == "customer" and call.person_id else None,
        })
    return _panel(
        "panel_calls", "list", "تماس‌های اخیر", "di-call", 8, "primary",
        count=calls_for(user).filter(status=Call.Status.MISSED).count(), count_label="بی‌پاسخ",
        items=items, empty="تماسی ثبت نشده است.",
    )


def panels_for(user, *, now):
    panels = []
    if feature_enabled("tasks"):
        panels.append(_tasks_panel(user, now=now))
    if feature_enabled("internal_chat"):
        panels.append(_chat_panel(user))
    if feature_enabled("reminders"):
        panels.append(_agenda_panel(user, now=now))
    if feature_enabled("tasks"):
        panels.append(_calendar_panel(user, now=now))
    if feature_enabled("telephony"):
        panels.append(_calls_panel(user))
    return [panel for panel in panels if panel is not None]
