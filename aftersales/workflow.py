"""After-sales stages, types, priorities and deadlines (2.40.60, BIZ-008).

Product owner, 2026-10-17:

* stages «ثبت‌شده، در حال بررسی، منتظر مشتری یا اطلاعات تکمیلی، منتظر قطعه یا
  تأمین‌کننده، در حال انجام، آماده تحویل یا اعلام نتیجه، بسته‌شده»;
* a closed case has its own final result — «حل‌شده، حل‌نشده، مختومه با توافق
  مشتری»; reopening needs a reason and keeps the history;
* types «شکایت، تعمیر، گارانتی، پرسش، مرجوعی، پیگیری ارسال، سایر», each with
  its own stages, priority and deadlines when it wants them;
* priorities «عادی، فوری، بحرانی», with first-response and resolution
  deadlines (critical: a handling plan too, resolution by type), all
  changeable per company and counted in the company's working time;
* older cases go to the nearest new stage, keeping their status and history.

Three controls: the `after_sales` feature; `after_sales.manage` (or the
after-sales agent the case is assigned to, for the moves the agent makes);
shaping the lists, deadlines and calendar needs `customization.manage`.
"""

import unicodedata

from django.db import transaction
from django.utils import timezone

from accounts.access import has_any_capability
from accounts.models import User
from aftersales.models import (
    PRIORITIES,
    AfterSalesHistory,
    AfterSalesRequest,
    CaseStage,
    CaseType,
    Holiday,
    SlaPolicy,
    WorkingCalendar,
)
from aftersales.sla import DEFAULT_HOURS, WorkingTime
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError

CONFIGURE_CAPABILITY = "customization.manage"
REASON_MAX = 500

PRIORITY_LABELS = {"normal": "عادی", "urgent": "فوری", "critical": "بحرانی"}
RESULT_LABELS = {"resolved": "حل‌شده", "unresolved": "حل‌نشده", "agreed": "مختومه با توافق مشتری"}

#: (key, label)
DEFAULT_TYPES = (
    ("complaint", "شکایت"),
    ("repair", "تعمیر"),
    ("warranty", "گارانتی"),
    ("question", "پرسش"),
    ("return", "مرجوعی"),
    ("shipping", "پیگیری ارسال"),
    ("other", "سایر"),
)
#: (key, label, kind)
DEFAULT_STAGES = (
    ("registered", "ثبت‌شده", "open"),
    ("reviewing", "در حال بررسی", "open"),
    ("waiting_customer", "منتظر مشتری یا اطلاعات تکمیلی", "open"),
    ("waiting_parts", "منتظر قطعه یا تأمین‌کننده", "open"),
    ("in_progress", "در حال انجام", "open"),
    ("ready", "آماده تحویل یا اعلام نتیجه", "open"),
    ("closed", "بسته‌شده", "closed"),
)
#: priority → (response, plan, resolution), each (value, unit) or None.
DEFAULT_SLA = {
    "normal": ((1, "day"), None, (5, "day")),
    "urgent": ((4, "hour"), None, (2, "day")),
    "critical": ((1, "hour"), (4, "hour"), None),
}
#: Words in an older case's status and the stage they mean, checked in order.
LEGACY_WORDS = (
    (("بسته", "مختومه", "closed"), "closed"),
    (("قطعه", "تأمین", "تامین"), "waiting_parts"),
    (("منتظر مشتری", "اطلاعات", "منتظر پاسخ"), "waiting_customer"),
    (("آماده", "تحویل", "اعلام نتیجه"), "ready"),
    (("انجام", "تعمیر", "پیگیری"), "in_progress"),
    (("بررسی",), "reviewing"),
    (("ثبت", "جدید", "باز"), "registered"),
)
#: Fixed solar holidays: (month, day, title). Lunar ones are not here on
#: purpose: their dates follow the moon and the official calendar each year.
FIXED_SOLAR_HOLIDAYS = (
    (1, 1, "عید نوروز"),
    (1, 2, "عید نوروز"),
    (1, 3, "عید نوروز"),
    (1, 4, "عید نوروز"),
    (1, 12, "روز جمهوری اسلامی"),
    (1, 13, "روز طبیعت"),
    (3, 14, "رحلت امام خمینی"),
    (3, 15, "قیام ۱۵ خرداد"),
    (11, 22, "پیروزی انقلاب اسلامی"),
    (12, 29, "ملی شدن صنعت نفت"),
)


# --- defaults --------------------------------------------------------------------


def ensure_defaults():
    """The seeded types, stages and deadlines, put back if a table was emptied."""
    if not CaseType.objects.exists():
        for position, (key, label) in enumerate(DEFAULT_TYPES, start=1):
            CaseType.objects.get_or_create(key=key, defaults={"label": label, "position": position, "is_system": True})
    if not CaseStage.objects.filter(case_type__isnull=True).exists():
        for position, (key, label, kind) in enumerate(DEFAULT_STAGES, start=1):
            CaseStage.objects.get_or_create(
                case_type=None, key=key,
                defaults={"label": label, "kind": kind, "position": position, "is_system": True},
            )
    if not SlaPolicy.objects.filter(case_type__isnull=True).exists():
        for priority, (response, plan, resolution) in DEFAULT_SLA.items():
            SlaPolicy.objects.get_or_create(priority=priority, case_type=None, defaults=_sla_fields(response, plan, resolution))


def _sla_fields(response, plan, resolution):
    fields = {}
    for name, pair in (("response", response), ("plan", plan), ("resolution", resolution)):
        fields[f"{name}_value"] = pair[0] if pair else None
        fields[f"{name}_unit"] = pair[1] if pair else ("day" if name == "resolution" else "hour")
    return fields


# --- reading ---------------------------------------------------------------------


def stages_for(case_type):
    """The stage list a case of this type moves through: the type's own when
    it has one, else the default list."""
    ensure_defaults()
    own = list(CaseStage.objects.filter(case_type=case_type).order_by("position", "id")) if case_type else []
    if own:
        return own
    return list(CaseStage.objects.filter(case_type__isnull=True).order_by("position", "id"))


def stage_of(case):
    return next((stage for stage in stages_for(case.case_type) if stage.key == case.stage), None)


def first_open(case_type):
    return next((stage for stage in stages_for(case_type) if stage.kind == "open" and stage.is_active), None)


def closed_stage(case_type):
    return next(stage for stage in stages_for(case_type) if stage.kind == "closed")


def policy_for(priority, case_type):
    """The type's own rule for the priority when it has one, else the company's."""
    ensure_defaults()
    if case_type is not None:
        own = SlaPolicy.objects.filter(priority=priority, case_type=case_type).first()
        if own is not None:
            return own
    return SlaPolicy.objects.filter(priority=priority, case_type__isnull=True).first()


def working_time():
    calendar = WorkingCalendar.objects.filter(pk=1).first()
    hours = calendar.hours if calendar and calendar.hours else DEFAULT_HOURS
    skip = calendar.skip_holidays if calendar else True
    holidays = Holiday.objects.values_list("day", flat=True) if skip else []
    return WorkingTime(hours, holidays)


def nearest_stage(text, *, closed=False):
    """The default stage an older case's words mean; «در حال بررسی» when none."""
    if closed:
        return "closed"
    words = " ".join(unicodedata.normalize("NFKC", str(text or "")).replace("ي", "ی").replace("ك", "ک").split())
    for needles, key in LEGACY_WORDS:
        if key == "closed":
            continue
        if any(needle in words for needle in needles):
            return key
    return "reviewing"


# --- deadlines -------------------------------------------------------------------


def set_deadlines(case, *, start=None):
    """Write the case's deadlines from its priority and type, counted from
    `start` (when it was made, by default) in working time."""
    policy = policy_for(case.priority, case.case_type)
    clock = working_time()
    start = start or case.created_at or timezone.now()
    if policy is None:
        case.response_due = case.plan_due = case.resolution_due = None
        return
    case.response_due = clock.add(start, policy.response_value, policy.response_unit)
    case.plan_due = clock.add(start, policy.plan_value, policy.plan_unit) if case.priority == "critical" else None
    case.resolution_due = clock.add(start, policy.resolution_value, policy.resolution_unit)


def _responded(case, now):
    """The first action on a case is its first response."""
    if case.responded_at is None:
        case.responded_at = now
        return ["responded_at"]
    return []


# --- one case ----------------------------------------------------------------------


def _lock_actor(actor):
    from aftersales.services import _lock_actor as lock

    return lock(actor)


def _may_work(actor, case):
    return has_any_capability(actor, "after_sales.manage") or (
        actor.role == User.Role.SALES_AGENT and actor.workstream == User.Workstream.AFTER_SALES
        and case.assigned_to_id == actor.pk
    )


def _reason(value, *, required=False):
    text = " ".join(str(value or "").split())
    if required and not text:
        raise BusinessRuleError({"reason": "دلیل را بنویسید."})
    if len(text) > REASON_MAX:
        raise BusinessRuleError({"reason": f"دلیل نباید بیش از {REASON_MAX} نویسه باشد."})
    return text


def resolve_stage(case_type, value):
    """A stage of the type's list by key or by name, or a clear refusal."""
    text = " ".join(str(value or "").split())
    for stage in stages_for(case_type):
        if text in (stage.key, stage.label):
            return stage
    raise BusinessRuleError({"to_status": "مرحله را از فهرست مرحله‌های این پرونده انتخاب کنید."})


@transaction.atomic
def set_stage(*, actor, request, to_stage, reason=""):
    """Move an open case to another open stage. Closing is `close`."""
    actor = _lock_actor(actor)
    case = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if not _may_work(actor, case):
        raise BusinessPermissionDenied("تغییر مرحلهٔ پرونده مجاز نیست.")
    if case.closed_at is not None:
        raise BusinessConflictError({"closed_at": "پروندهٔ بسته را اول بازگشایی کنید."})
    target = resolve_stage(case.case_type, to_stage)
    if target.kind == "closed":
        raise BusinessRuleError({"to_status": "برای بستن، «بستن پرونده» را با نتیجهٔ نهایی بزنید."})
    if not target.is_active:
        raise BusinessRuleError({"to_status": "این مرحله خاموش است."})
    if target.key == case.stage:
        raise BusinessConflictError({"to_status": "پرونده هم‌اکنون در همین مرحله است."})
    reason = _reason(reason)
    previous = case.status
    now = timezone.now()
    case.stage, case.status = target.key, target.label
    fields = ["stage", "status", "updated_at", *_responded(case, now)]
    case.save(update_fields=fields)
    AfterSalesHistory.objects.create(
        request=case, event=AfterSalesHistory.Event.STATUS_CHANGED, actor=actor,
        from_status=previous, to_status=target.label, reason=reason,
    )
    log_activity(actor=actor, operation="after_sales.status_changed", instance=case,
                 changes={"case_from": previous, "case_to": target.label, "reason_provided": bool(reason)})
    return case


@transaction.atomic
def close(*, actor, request, final_result, reason=""):
    actor = _lock_actor(actor)
    if not has_any_capability(actor, "after_sales.manage"):
        raise BusinessPermissionDenied("بستن درخواست خدمات پس از فروش مجاز نیست.")
    case = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if case.closed_at is not None:
        raise BusinessConflictError({"closed_at": "این درخواست قبلاً بسته شده است."})
    if final_result not in RESULT_LABELS:
        raise BusinessRuleError({"final_result": "نتیجهٔ نهایی را انتخاب کنید: حل‌شده، حل‌نشده یا مختومه با توافق مشتری."})
    reason = _reason(reason)
    now = timezone.now()
    previous = case.status
    stage = closed_stage(case.case_type)
    case.stage, case.status, case.final_result, case.closed_at = stage.key, stage.label, final_result, now
    fields = ["stage", "status", "final_result", "closed_at", "updated_at", *_responded(case, now)]
    case.save(update_fields=fields)
    AfterSalesHistory.objects.create(
        request=case, event=AfterSalesHistory.Event.CLOSED, actor=actor, from_status=previous,
        to_status=f"{stage.label} — {RESULT_LABELS[final_result]}", reason=reason,
    )
    log_activity(actor=actor, operation="after_sales.closed", instance=case,
                 changes={"final_result": final_result, "reason_provided": bool(reason)})
    # The satisfaction survey (2.40.61), once the closing is committed: a text
    # that fails never undoes it.
    from aftersales.alerts import send_survey

    transaction.on_commit(lambda: send_survey(case.pk))
    return case


@transaction.atomic
def reopen(*, actor, request, reason, to_stage=None):
    """Open a closed case again; the reason stays in its history."""
    actor = _lock_actor(actor)
    if not has_any_capability(actor, "after_sales.manage"):
        raise BusinessPermissionDenied("بازگشایی پرونده مجاز نیست.")
    case = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if case.closed_at is None:
        raise BusinessConflictError({"closed_at": "این پرونده باز است."})
    reason = _reason(reason, required=True)
    target = resolve_stage(case.case_type, to_stage) if to_stage else first_open(case.case_type)
    if target is None or target.kind != "open" or not target.is_active:
        raise BusinessRuleError({"to_status": "مرحلهٔ بازگشایی باید یکی از مرحله‌های باز باشد."})
    previous = case.status
    case.stage, case.status, case.final_result, case.closed_at = target.key, target.label, "", None
    case.save(update_fields=["stage", "status", "final_result", "closed_at", "updated_at"])
    AfterSalesHistory.objects.create(
        request=case, event=AfterSalesHistory.Event.REOPENED, actor=actor,
        from_status=previous, to_status=target.label, reason=reason,
    )
    log_activity(actor=actor, operation="after_sales.reopened", instance=case, changes={"reason_provided": True})
    return case


@transaction.atomic
def set_priority(*, actor, request, priority, reason=""):
    """A different priority; the deadlines are counted again from the start."""
    actor = _lock_actor(actor)
    if not has_any_capability(actor, "after_sales.manage"):
        raise BusinessPermissionDenied("تغییر اولویت مجاز نیست.")
    if priority not in PRIORITIES:
        raise BusinessRuleError({"priority": "اولویت باید عادی، فوری یا بحرانی باشد."})
    case = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if case.priority == priority:
        raise BusinessConflictError({"priority": "اولویت هم‌اکنون همین است."})
    reason = _reason(reason)
    previous = case.priority
    case.priority = priority
    set_deadlines(case)
    case.save(update_fields=["priority", "response_due", "plan_due", "resolution_due", "updated_at"])
    AfterSalesHistory.objects.create(
        request=case, event=AfterSalesHistory.Event.PRIORITY_CHANGED, actor=actor,
        from_status=PRIORITY_LABELS[previous], to_status=PRIORITY_LABELS[priority], reason=reason,
    )
    log_activity(actor=actor, operation="after_sales.priority_changed", instance=case,
                 changes={"from": previous, "to": priority})
    return case


@transaction.atomic
def record_plan(*, actor, request, note):
    """The handling plan of a critical case: its own deadline, met here."""
    actor = _lock_actor(actor)
    case = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if not _may_work(actor, case):
        raise BusinessPermissionDenied("ثبت برنامهٔ رسیدگی مجاز نیست.")
    if case.closed_at is not None:
        raise BusinessConflictError({"closed_at": "پرونده بسته است."})
    note = " ".join(str(note or "").split())
    if not note:
        raise BusinessRuleError({"note": "برنامهٔ رسیدگی را بنویسید."})
    if len(note) > REASON_MAX:
        raise BusinessRuleError({"note": f"برنامه نباید بیش از {REASON_MAX} نویسه باشد."})
    now = timezone.now()
    case.planned_at = case.planned_at or now
    fields = ["planned_at", "updated_at", *_responded(case, now)]
    case.save(update_fields=fields)
    AfterSalesHistory.objects.create(request=case, event=AfterSalesHistory.Event.PLANNED, actor=actor, reason=note)
    log_activity(actor=actor, operation="after_sales.planned", instance=case, changes={})
    return case


# --- shaping the lists, deadlines and calendar -------------------------------------


def can_configure(user):
    return has_any_capability(user, CONFIGURE_CAPABILITY)


def _require_configurer(actor):
    if not can_configure(actor):
        raise BusinessPermissionDenied("تنظیم پس از فروش مجاز نیست.")


def fixed_holidays(jalali_year):
    from common.jalali import from_jalali

    return [(from_jalali(jalali_year, month, day), title) for month, day, title in FIXED_SOLAR_HOLIDAYS]


@transaction.atomic
def add_fixed_holidays(*, actor, jalali_year):
    """The fixed solar holidays of one Jalali year; days already listed stay."""
    _require_configurer(actor)
    if not 1390 <= int(jalali_year) <= 1500:
        raise BusinessRuleError({"jalali_year": "سال شمسی را درست بنویسید."})
    added = 0
    for day, title in fixed_holidays(int(jalali_year)):
        _row, created = Holiday.objects.get_or_create(day=day, defaults={"title": title, "created_by": actor})
        added += int(created)
    log_activity(actor=actor, operation="after_sales.holidays_added", instance=_calendar(),
                 changes={"jalali_year": int(jalali_year), "added": added})
    return added


# --- settings: types, stages, deadlines, calendar, holidays --------------------------


def _clean_label(value, *, others):
    from sales.customer_backfill import clean_label, normalize_label

    label = clean_label(value)
    if not label:
        raise BusinessRuleError({"label": "نام را بنویسید."})
    if len(label) > 60:
        raise BusinessRuleError({"label": "نام نباید بیش از ۶۰ نویسه باشد."})
    if normalize_label(label) in {normalize_label(other) for other in others}:
        raise BusinessRuleError({"label": "این نام در همین فهرست هست."})
    return label


def _next_key(keys):
    numbers = [int(key[1:]) for key in keys if key[:1] == "c" and key[1:].isdigit()]
    return f"c{max(numbers, default=0) + 1}"


def _calendar():
    row, _ = WorkingCalendar.objects.get_or_create(pk=1, defaults={"hours": DEFAULT_HOURS})
    return row


def serialize_stage(stage):
    return {"id": stage.pk, "key": stage.key, "label": stage.label, "kind": stage.kind, "position": stage.position,
            "is_system": stage.is_system, "is_active": stage.is_active,
            "case_type": stage.case_type_id}


def serialize_policy(policy):
    return {
        "id": policy.pk, "priority": policy.priority, "priority_label": PRIORITY_LABELS[policy.priority],
        "case_type": policy.case_type_id,
        "response_value": policy.response_value, "response_unit": policy.response_unit,
        "plan_value": policy.plan_value, "plan_unit": policy.plan_unit,
        "resolution_value": policy.resolution_value, "resolution_unit": policy.resolution_unit,
    }


def page_payload():
    """What the case pages embed: the types that are on, every stage list,
    the priorities and the final results (2.40.60)."""
    ensure_defaults()
    types = list(CaseType.objects.order_by("position", "id"))
    return {
        "types": [{"id": item.pk, "label": item.label, "default_priority": item.default_priority,
                   "is_active": item.is_active} for item in types],
        "default_stages": [serialize_stage(stage) for stage in stages_for(None)],
        "type_stages": {
            str(item.pk): [serialize_stage(stage) for stage in CaseStage.objects.filter(case_type=item).order_by("position", "id")]
            for item in types
        },
        "priorities": [{"key": key, "label": label} for key, label in PRIORITY_LABELS.items()],
        "results": [{"key": key, "label": label} for key, label in RESULT_LABELS.items()],
    }


def settings_payload():
    """Everything the settings tab and the case forms read."""
    ensure_defaults()
    calendar = WorkingCalendar.objects.filter(pk=1).first()
    types = list(CaseType.objects.order_by("position", "id"))
    return {
        "types": [
            {"id": item.pk, "key": item.key, "label": item.label, "default_priority": item.default_priority,
             "position": item.position, "is_system": item.is_system, "is_active": item.is_active,
             "own_stages": CaseStage.objects.filter(case_type=item).exists()}
            for item in types
        ],
        "default_stages": [serialize_stage(stage) for stage in stages_for(None)],
        "type_stages": {
            str(item.pk): [serialize_stage(stage) for stage in CaseStage.objects.filter(case_type=item).order_by("position", "id")]
            for item in types
        },
        "policies": [serialize_policy(policy) for policy in SlaPolicy.objects.select_related("case_type").order_by("case_type_id", "priority")],
        "priorities": [{"key": key, "label": label} for key, label in PRIORITY_LABELS.items()],
        "results": [{"key": key, "label": label} for key, label in RESULT_LABELS.items()],
        "calendar": {
            "hours": (calendar.hours if calendar and calendar.hours else DEFAULT_HOURS),
            "skip_holidays": calendar.skip_holidays if calendar else True,
        },
        "holidays": [{"id": row.pk, "day": row.day.isoformat(), "title": row.title} for row in Holiday.objects.order_by("day")],
    }


@transaction.atomic
def create_type(*, actor, label, default_priority="normal"):
    _require_configurer(actor)
    if default_priority not in PRIORITIES:
        raise BusinessRuleError({"default_priority": "اولویت باید عادی، فوری یا بحرانی باشد."})
    existing = list(CaseType.objects.select_for_update().order_by("position", "id"))
    item = CaseType.objects.create(
        key=_next_key([row.key for row in existing]), label=_clean_label(label, others=[row.label for row in existing]),
        default_priority=default_priority, position=max((row.position for row in existing), default=0) + 1,
    )
    log_activity(actor=actor, operation="after_sales.type_created", instance=item, changes={"key": item.key})
    return item


@transaction.atomic
def update_type(*, actor, case_type, **changes):
    _require_configurer(actor)
    item = CaseType.objects.select_for_update().get(pk=case_type.pk)
    unknown = set(changes) - {"label", "default_priority", "is_active"}
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    changed = []
    if "label" in changes:
        others = CaseType.objects.exclude(pk=item.pk).values_list("label", flat=True)
        label = _clean_label(changes["label"], others=list(others))
        if label != item.label:
            item.label = label
            changed.append("label")
    if "default_priority" in changes and changes["default_priority"] != item.default_priority:
        if changes["default_priority"] not in PRIORITIES:
            raise BusinessRuleError({"default_priority": "اولویت باید عادی، فوری یا بحرانی باشد."})
        item.default_priority = changes["default_priority"]
        changed.append("default_priority")
    if "is_active" in changes and bool(changes["is_active"]) != item.is_active:
        if not changes["is_active"] and not CaseType.objects.filter(is_active=True).exclude(pk=item.pk).exists():
            raise BusinessRuleError({"is_active": "دست‌کم یک نوع پرونده باید روشن بماند."})
        item.is_active = bool(changes["is_active"])
        changed.append("is_active")
    if changed:
        item.save(update_fields=[*changed, "updated_at"])
        log_activity(actor=actor, operation="after_sales.type_updated", instance=item, changes={"fields": sorted(changed)})
    return item


@transaction.atomic
def give_type_own_stages(*, actor, case_type):
    """Start a type's own stage list as a copy of the default one."""
    _require_configurer(actor)
    item = CaseType.objects.select_for_update().get(pk=case_type.pk)
    if CaseStage.objects.filter(case_type=item).exists():
        raise BusinessConflictError({"case_type": "این نوع فهرست مرحلهٔ خودش را دارد."})
    for stage in stages_for(None):
        CaseStage.objects.create(
            case_type=item, key=stage.key, label=stage.label, kind=stage.kind, position=stage.position,
            is_system=stage.is_system, is_active=stage.is_active,
        )
    log_activity(actor=actor, operation="after_sales.type_stages_created", instance=item, changes={})
    return item


@transaction.atomic
def create_stage(*, actor, label, case_type=None):
    """An open stage in a list, placed before the closed one."""
    _require_configurer(actor)
    existing = list(CaseStage.objects.select_for_update().filter(case_type=case_type).order_by("position", "id"))
    if not existing:
        raise BusinessRuleError({"case_type": "اول فهرست مرحلهٔ این نوع را بسازید."})
    label = _clean_label(label, others=[stage.label for stage in existing])
    closed_at = next(index for index, stage in enumerate(existing) if stage.kind == "closed")
    ordered = existing[:closed_at] + [None] + existing[closed_at:]
    created = None
    for position, stage in enumerate(ordered, start=1):
        if stage is None:
            created = CaseStage.objects.create(
                case_type=case_type, key=_next_key([row.key for row in existing]), label=label, position=position,
            )
        elif stage.position != position:
            stage.position = position
            stage.save(update_fields=["position", "updated_at"])
    log_activity(actor=actor, operation="after_sales.stage_created", instance=created, changes={"key": created.key})
    return created


@transaction.atomic
def update_stage(*, actor, stage, **changes):
    _require_configurer(actor)
    item = CaseStage.objects.select_for_update().get(pk=stage.pk)
    unknown = set(changes) - {"label", "is_active"}
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    changed = []
    if "label" in changes:
        others = CaseStage.objects.filter(case_type=item.case_type).exclude(pk=item.pk).values_list("label", flat=True)
        label = _clean_label(changes["label"], others=list(others))
        if label != item.label:
            item.label = label
            changed.append("label")
    if "is_active" in changes and bool(changes["is_active"]) != item.is_active:
        if item.kind == "closed":
            raise BusinessRuleError({"is_active": "مرحلهٔ بسته‌شده همیشه روشن است."})
        if not changes["is_active"] and not CaseStage.objects.filter(
            case_type=item.case_type, kind="open", is_active=True,
        ).exclude(pk=item.pk).exists():
            raise BusinessRuleError({"is_active": "دست‌کم یک مرحلهٔ باز باید روشن بماند."})
        item.is_active = bool(changes["is_active"])
        changed.append("is_active")
    if changed:
        item.save(update_fields=[*changed, "updated_at"])
        log_activity(actor=actor, operation="after_sales.stage_updated", instance=item, changes={"fields": sorted(changed)})
    return item


@transaction.atomic
def move_stage(*, actor, stage, direction):
    _require_configurer(actor)
    if direction not in ("up", "down"):
        raise BusinessRuleError({"direction": "جهت باید بالا یا پایین باشد."})
    ordered = list(CaseStage.objects.select_for_update().filter(case_type=stage.case_type).order_by("position", "id"))
    index = next(i for i, item in enumerate(ordered) if item.pk == stage.pk)
    if ordered[index].kind == "closed":
        raise BusinessRuleError({"direction": "مرحلهٔ بسته‌شده آخر فهرست می‌ماند."})
    other = index - 1 if direction == "up" else index + 1
    if 0 <= other < len(ordered) and ordered[other].kind == "open":
        ordered[index], ordered[other] = ordered[other], ordered[index]
    for position, item in enumerate(ordered, start=1):
        if item.position != position:
            item.position = position
            item.save(update_fields=["position", "updated_at"])
    return ordered


def _limit(value, unit, field):
    if value in (None, ""):
        return None, unit if unit in SlaPolicy.UNITS else "hour"
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise BusinessRuleError({field: "عدد درست بنویسید."}) from None
    if not 1 <= value <= 999:
        raise BusinessRuleError({field: "عدد باید بین ۱ و ۹۹۹ باشد."})
    if unit not in SlaPolicy.UNITS:
        raise BusinessRuleError({field: "واحد باید ساعت یا روز باشد."})
    return value, unit


@transaction.atomic
def set_policy(*, actor, priority, case_type=None, response=None, plan=None, resolution=None, clear=False):
    """The deadlines of one priority — the company's, or one type's own.
    `clear` drops a type's own rule so the company's applies again.
    Each limit is `{"value": n or None, "unit": "hour"|"day"}`. Cases already
    open keep their deadlines; new ones and priority changes use the rule."""
    _require_configurer(actor)
    if priority not in PRIORITIES:
        raise BusinessRuleError({"priority": "اولویت باید عادی، فوری یا بحرانی باشد."})
    if clear:
        if case_type is None:
            raise BusinessRuleError({"case_type": "قاعدهٔ شرکت برداشتنی نیست."})
        SlaPolicy.objects.filter(priority=priority, case_type=case_type).delete()
        log_activity(actor=actor, operation="after_sales.sla_cleared", instance=case_type, changes={"priority": priority})
        return None
    policy, _ = SlaPolicy.objects.select_for_update().get_or_create(priority=priority, case_type=case_type)
    for name, given in (("response", response), ("plan", plan), ("resolution", resolution)):
        if given is None:
            continue
        value, unit = _limit(given.get("value"), given.get("unit"), f"{name}_value")
        setattr(policy, f"{name}_value", value)
        setattr(policy, f"{name}_unit", unit)
    policy.save()
    log_activity(actor=actor, operation="after_sales.sla_updated", instance=policy,
                 changes={"priority": priority, "case_type": getattr(case_type, "pk", None)})
    return policy


def _clean_hours(hours):
    import re

    if not isinstance(hours, dict):
        raise BusinessRuleError({"hours": "ساعت‌های کاری درست نیست."})
    cleaned = {}
    for day, pair in hours.items():
        if str(day) not in {str(number) for number in range(7)}:
            raise BusinessRuleError({"hours": "روز هفته درست نیست."})
        if not pair:
            continue
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(
            isinstance(item, str) and re.fullmatch(r"([01][0-9]|2[0-3]):[0-5][0-9]", item) for item in pair
        ):
            raise BusinessRuleError({"hours": "ساعت را به شکل ۰۸:۰۰ بنویسید."})
        if pair[1] <= pair[0]:
            raise BusinessRuleError({"hours": "پایان کار باید پس از شروع آن باشد."})
        cleaned[str(day)] = [pair[0], pair[1]]
    if not cleaned:
        raise BusinessRuleError({"hours": "دست‌کم یک روز کاری لازم است."})
    return cleaned


@transaction.atomic
def update_calendar(*, actor, hours=None, skip_holidays=None):
    _require_configurer(actor)
    row = WorkingCalendar.objects.select_for_update().filter(pk=1).first() or _calendar()
    if hours is not None:
        row.hours = _clean_hours(hours)
    if skip_holidays is not None:
        row.skip_holidays = bool(skip_holidays)
    row.updated_by = actor
    row.save()
    log_activity(actor=actor, operation="after_sales.calendar_updated", instance=row, changes={})
    return row


@transaction.atomic
def add_holiday(*, actor, day, title):
    _require_configurer(actor)
    title = " ".join(str(title or "").split())
    if not title:
        raise BusinessRuleError({"title": "نام تعطیلی را بنویسید."})
    if Holiday.objects.filter(day=day).exists():
        raise BusinessConflictError({"day": "این روز در فهرست هست."})
    row = Holiday.objects.create(day=day, title=title[:120], created_by=actor)
    log_activity(actor=actor, operation="after_sales.holiday_added", instance=_calendar(), changes={"day": day.isoformat()})
    return row


@transaction.atomic
def remove_holiday(*, actor, holiday):
    _require_configurer(actor)
    day = holiday.day
    holiday.delete()
    log_activity(actor=actor, operation="after_sales.holiday_removed", instance=_calendar(), changes={"day": day.isoformat()})
