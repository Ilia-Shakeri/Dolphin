"""Deadline warnings, escalation and the satisfaction survey (2.40.61, BIZ-008).

Product owner, 2026-10-17: «نزدیک شدن به مهلت یا عبور از آن، از طریق اعلان
داخل پنل به مسئول پرونده و در صورت نیاز به مدیر اطلاع داده شود. امکان
فعال‌سازی پیامک و ارجاع خودکار پرونده‌های معوق به مدیر نیز وجود داشته باشد.
پس از بسته شدن پرونده، امکان ارسال پیامک نظرسنجی رضایت مشتری با متن قابل
تنظیم فراهم باشد.»

* **In the panel**, always: the topbar bell (`common.reminders`) shows the
  assignee their cases near a deadline (four fifths of the time gone) or past
  it, and the managers the cases past it. Nothing to dismiss — it clears when
  the deadline is met.
* **By text**, when the company turns it on: `check_deadlines` (cron, every
  15 minutes) writes one `SlaAlert` per deadline and level, and texts the
  assignee — and the managers once a deadline has passed — once.
* **Escalation**, when turned on: a case past a deadline is handed to the
  managers (`escalated_at`, a history row), once.
* **Survey**: when a case closes, the customer is asked for a score in the
  company's own words — if turned on, with the SMS feature and a provider.

Every text is the outbound-SMS module's (`communications.services`), which
records each attempt and its outcome; a failure is logged, never raised.
"""

import logging

from django.db import transaction
from django.utils import timezone

from accounts.access import crm_identities, has_any_capability
from accounts.models import User
from aftersales.models import AfterSalesHistory, AfterSalesRequest, AfterSalesSettings, SlaAlert
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError

logger = logging.getLogger("dolphin.after_sales")

#: "Near" is four fifths of a deadline's time gone: 5 × elapsed ≥ 4 × span,
#: in whole microseconds, the same sum in Python and in SQL.
APPROACHING_PARTS = (4, 5)
CONFIGURE_CAPABILITY = "customization.manage"
SURVEY_TOKENS = ("{نام}", "{پرونده}", "{موضوع}")
KIND_LABELS = dict(SlaAlert.Kind.choices)


# --- settings ----------------------------------------------------------------------


def settings_row():
    row, _ = AfterSalesSettings.objects.get_or_create(pk=1)
    return row


def sms_available():
    """The outbound SMS feature is on and a provider is configured."""
    if not feature_enabled("outbound_sms"):
        return False
    from communications import sms

    return sms.provider_is_available()


def serialize_settings():
    row = settings_row()
    return {
        "sms_alerts": row.sms_alerts, "escalate_overdue": row.escalate_overdue,
        "survey_sms": row.survey_sms, "survey_text": row.survey_text,
        "survey_tokens": list(SURVEY_TOKENS), "sms_available": sms_available(),
    }


@transaction.atomic
def update_settings(*, actor, **changes):
    if not has_any_capability(actor, CONFIGURE_CAPABILITY):
        raise BusinessPermissionDenied("تنظیم هشدار و نظرسنجی پس از فروش مجاز نیست.")
    unknown = set(changes) - {"sms_alerts", "escalate_overdue", "survey_sms", "survey_text"}
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    row = AfterSalesSettings.objects.select_for_update().filter(pk=1).first() or settings_row()
    for flag in ("sms_alerts", "escalate_overdue", "survey_sms"):
        if flag in changes:
            setattr(row, flag, bool(changes[flag]))
    if "survey_text" in changes:
        text = " ".join(str(changes["survey_text"] or "").split())
        if not text:
            raise BusinessRuleError({"survey_text": "متن نظرسنجی را بنویسید."})
        if len(text) > 500:
            raise BusinessRuleError({"survey_text": "متن نباید بیش از ۵۰۰ نویسه باشد."})
        row.survey_text = text
    row.updated_by = actor
    row.save()
    log_activity(actor=actor, operation="after_sales.alerts_updated", instance=row, changes={"fields": sorted(changes)})
    return serialize_settings()


# --- deadlines ---------------------------------------------------------------------


def deadlines(case):
    """`(kind, due, met_at)` for each deadline the case has."""
    rows = []
    if case.response_due:
        rows.append(("response", case.response_due, case.responded_at))
    if case.plan_due:
        rows.append(("plan", case.plan_due, case.planned_at))
    if case.resolution_due:
        rows.append(("resolution", case.resolution_due, case.closed_at))
    return rows


def warnings_for(case, now):
    """`[(kind, level, due)]`: the unmet deadlines now near or past."""
    if case.closed_at is not None:
        return []
    found = []
    for kind, due, met_at in deadlines(case):
        if met_at is not None:
            continue
        if due <= now:
            found.append((kind, SlaAlert.Level.BREACHED, due))
        elif (now - case.created_at) * APPROACHING_PARTS[1] >= (due - case.created_at) * APPROACHING_PARTS[0]:
            found.append((kind, SlaAlert.Level.APPROACHING, due))
    return found


def _open_with_deadlines(queryset):
    from django.db.models import Q

    return queryset.filter(closed_at__isnull=True).filter(
        Q(response_due__isnull=False, responded_at__isnull=True)
        | Q(plan_due__isnull=False, planned_at__isnull=True)
        | Q(resolution_due__isnull=False)
    )


def _managers():
    return crm_identities(User.objects.filter(
        is_active=True, role__in=[User.Role.SALES_MANAGER, User.Role.PLATFORM_ADMIN],
    ))


def _text_staff(user, body):
    """One text to a member of staff; `False` when it could not be sent."""
    from communications.services import send_system_sms

    if user is None or not user.normalized_phone:
        return False
    try:
        return bool(send_system_sms(body=body, phone=user.normalized_phone))
    except BusinessRuleError as error:
        logger.warning("after-sales alert text not sent to user %s: %s", user.pk, error)
        return False


def check_deadlines(*, now=None):
    """Write and act on the warnings due now: texts and escalation, once each.

    Returns `{"alerts", "texts", "escalated"}`. Each case is handled in its own
    transaction, so one failure never stops the rest.
    """
    now = now or timezone.now()
    row = settings_row()
    texting = row.sms_alerts and sms_available()
    counts = {"alerts": 0, "texts": 0, "escalated": 0}
    cases = _open_with_deadlines(AfterSalesRequest.objects.all()).select_related("assigned_to", "customer")
    for case in cases.iterator():
        for kind, level, due in warnings_for(case, now):
            with transaction.atomic():
                alert, created = SlaAlert.objects.get_or_create(request=case, kind=kind, level=level, due_at=due)
                if not created:
                    continue
                counts["alerts"] += 1
                if texting:
                    when = "گذشت" if level == SlaAlert.Level.BREACHED else "نزدیک است"
                    body = f"مهلت {KIND_LABELS[kind]} پروندهٔ #{case.pk} ({case.subject[:40]}) {when}."
                    people = [case.assigned_to]
                    if level == SlaAlert.Level.BREACHED:
                        people += list(_managers())
                    sent = sum(1 for person in {p.pk: p for p in people if p}.values() if _text_staff(person, body))
                    alert.sms_sent = sent
                    alert.save(update_fields=["sms_sent"])
                    counts["texts"] += sent
                if level == SlaAlert.Level.BREACHED and row.escalate_overdue and case.escalated_at is None:
                    locked = AfterSalesRequest.objects.select_for_update().get(pk=case.pk)
                    if locked.escalated_at is None and locked.closed_at is None:
                        locked.escalated_at = now
                        locked.save(update_fields=["escalated_at"])
                        AfterSalesHistory.objects.create(
                            request=locked, event=AfterSalesHistory.Event.ESCALATED, actor=None,
                            reason=f"مهلت {KIND_LABELS[kind]} گذشت.",
                        )
                        log_activity(actor=None, operation="after_sales.escalated", instance=locked, changes={"deadline": kind})
                        case.escalated_at = now
                        counts["escalated"] += 1
    return counts


# --- the survey --------------------------------------------------------------------


def render_survey(text, case):
    customer = case.customer
    return (
        text.replace("{نام}", getattr(customer, "full_name", "") or "")
        .replace("{پرونده}", f"#{case.pk}")
        .replace("{موضوع}", case.subject or "")
    )


def send_survey(case_id):
    """Ask the customer of a closed case for a score, when the company does.

    Run after the closing commits (`workflow.close`), so a text that fails
    never undoes the closing; its outcome is the SMS log's, and the history
    says it was sent."""
    row = settings_row()
    if not row.survey_sms or not sms_available():
        return False
    case = AfterSalesRequest.objects.select_related("customer").filter(pk=case_id).first()
    if case is None or case.closed_at is None:
        return False
    from communications.services import send_system_sms

    try:
        message = send_system_sms(body=render_survey(row.survey_text, case), customer=case.customer)
    except BusinessRuleError as error:
        logger.warning("after-sales survey for case %s not sent: %s", case_id, error)
        return False
    with transaction.atomic():
        AfterSalesHistory.objects.create(
            request=case, event=AfterSalesHistory.Event.SURVEY_SENT, actor=None,
            reason="پیامک نظرسنجی فرستاده شد." if message.status == message.Status.SENT else "پیامک نظرسنجی فرستاده نشد.",
        )
    return message.status == message.Status.SENT


# --- the bell ----------------------------------------------------------------------


BELL_LIMIT = 200


def _bell_queryset(user, now):
    """The cases the bell names for this reader, filtered in SQL so the polled
    badge is one COUNT (`bell_count`): an assignee's cases with an unmet
    deadline near or past, a manager's every case past one."""
    from django.db.models import DateTimeField, DurationField, ExpressionWrapper, F, Q, Value

    from aftersales.selectors import after_sales_requests_for

    scoped = _open_with_deadlines(after_sales_requests_for(user))
    if has_any_capability(user, "after_sales.manage"):
        return scoped.filter(
            Q(response_due__lte=now, responded_at__isnull=True)
            | Q(plan_due__lte=now, planned_at__isnull=True)
            | Q(resolution_due__lte=now)
        ), True
    near, whole = APPROACHING_PARTS

    def scaled(start, times):
        return ExpressionWrapper((start - F("created_at")) * times, output_field=DurationField())

    # A deadline already past is also four fifths gone, so one test covers both.
    return scoped.alias(
        elapsed=scaled(Value(now, output_field=DateTimeField()), whole),
        response_span=scaled(F("response_due"), near),
        plan_span=scaled(F("plan_due"), near),
        resolution_span=scaled(F("resolution_due"), near),
    ).filter(
        Q(response_due__isnull=False, responded_at__isnull=True, response_span__lte=F("elapsed"))
        | Q(plan_due__isnull=False, planned_at__isnull=True, plan_span__lte=F("elapsed"))
        | Q(resolution_due__isnull=False, resolution_span__lte=F("elapsed"))
    ), False


def bell_count(user, *, now):
    queryset, _ = _bell_queryset(user, now)
    return min(queryset.count(), BELL_LIMIT)


def bell_cases(user, *, now):
    """What the bell shows this reader. `[(case, kind, level, due)]`."""
    scoped, manager = _bell_queryset(user, now)
    found = []
    for case in scoped.select_related("customer").order_by("resolution_due", "id")[:BELL_LIMIT]:
        for kind, level, due in warnings_for(case, now):
            if manager and level != SlaAlert.Level.BREACHED:
                continue
            found.append((case, kind, level, due))
            break
    return found
