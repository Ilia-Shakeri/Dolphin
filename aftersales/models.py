from django.conf import settings
from django.db import models
from django.db.models import Q

from sales.models import Customer, Sale, SalesDocument, TimeStampedModel

KEY_MAX = 40
LABEL_MAX = 60
KEY_SHAPE = r"\A[a-z][a-z0-9_]{0,39}\Z"
PRIORITIES = ("normal", "urgent", "critical")
RESULTS = ("resolved", "unresolved", "agreed")


class CaseType(TimeStampedModel):
    """What a case is about (2.40.60, BIZ-008): «شکایت، تعمیر، گارانتی،
    پرسش، مرجوعی، پیگیری ارسال، سایر» by default; a company adds its own.
    A type may keep its own stage list and its own deadlines, and starts new
    cases at its default priority. Never deleted, only turned off."""

    key = models.CharField(max_length=KEY_MAX, unique=True)
    label = models.CharField(max_length=LABEL_MAX)
    default_priority = models.CharField(max_length=10, default="normal")
    position = models.PositiveSmallIntegerField(default=0)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(key__regex=KEY_SHAPE), name="case_type_key_shape"),
            models.CheckConstraint(condition=Q(label__regex=r"\S"), name="case_type_label_nonblank"),
            models.CheckConstraint(condition=Q(default_priority__in=PRIORITIES), name="case_type_priority_valid"),
        ]


class CaseStage(TimeStampedModel):
    """One stage of a case (2.40.60). The seven defaults belong to no type and
    serve every type without a list of its own; a type's own list replaces
    them for that type. Exactly one closed stage per list, last."""

    class Kind(models.TextChoices):
        OPEN = "open", "باز"
        CLOSED = "closed", "بسته"

    case_type = models.ForeignKey(CaseType, null=True, blank=True, on_delete=models.PROTECT, related_name="stages")
    key = models.CharField(max_length=KEY_MAX)
    label = models.CharField(max_length=LABEL_MAX)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.OPEN)
    position = models.PositiveSmallIntegerField(default=0)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["case_type_id", "position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["case_type", "key"], name="uniq_case_stage_key"),
            models.UniqueConstraint(fields=["key"], condition=Q(case_type__isnull=True), name="uniq_default_case_stage_key"),
            models.CheckConstraint(condition=Q(key__regex=KEY_SHAPE), name="case_stage_key_shape"),
            models.CheckConstraint(condition=Q(label__regex=r"\S"), name="case_stage_label_nonblank"),
            models.CheckConstraint(condition=Q(kind__in=["open", "closed"]), name="case_stage_kind_valid"),
            models.CheckConstraint(condition=Q(kind="open") | Q(is_active=True), name="case_stage_closed_stays_on"),
        ]


class SlaPolicy(TimeStampedModel):
    """How fast a case of one priority is answered and solved (2.40.60).

    `case_type` empty is the company's rule for that priority; a type may set
    its own. Each limit is an amount and a unit, `hour` or `day`, counted in
    the company's working time (`aftersales.sla`). Empty means no deadline —
    a critical case's resolution is set per type (owner: «زمان حل نهایی با
    توجه به نوع مشکل تعیین شود»)."""

    UNITS = ("hour", "day")

    priority = models.CharField(max_length=10)
    case_type = models.ForeignKey(CaseType, null=True, blank=True, on_delete=models.PROTECT, related_name="sla_policies")
    response_value = models.PositiveSmallIntegerField(null=True, blank=True)
    response_unit = models.CharField(max_length=4, default="hour")
    plan_value = models.PositiveSmallIntegerField(null=True, blank=True)
    plan_unit = models.CharField(max_length=4, default="hour")
    resolution_value = models.PositiveSmallIntegerField(null=True, blank=True)
    resolution_unit = models.CharField(max_length=4, default="day")

    class Meta:
        ordering = ["case_type_id", "priority", "id"]
        constraints = [
            models.UniqueConstraint(fields=["priority", "case_type"], name="uniq_sla_priority_type"),
            models.UniqueConstraint(fields=["priority"], condition=Q(case_type__isnull=True), name="uniq_default_sla_priority"),
            models.CheckConstraint(condition=Q(priority__in=PRIORITIES), name="sla_priority_valid"),
            models.CheckConstraint(
                condition=Q(response_unit__in=["hour", "day"]) & Q(plan_unit__in=["hour", "day"])
                & Q(resolution_unit__in=["hour", "day"]),
                name="sla_units_valid",
            ),
        ]


class WorkingCalendar(models.Model):
    """The company's working week, one row (2.40.60): `hours` is
    `{python weekday: [opens, closes]}` in Tehran time; a day absent is
    closed. `skip_holidays` takes the listed holidays out of every deadline."""

    hours = models.JSONField(default=dict)
    skip_holidays = models.BooleanField(default=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(pk=1), name="working_calendar_singleton")]


class Holiday(models.Model):
    """A day the company does not count (2.40.60). Fixed solar holidays are
    added a year at a time; lunar ones are entered from the official calendar
    each year — Dolphin does not guess a lunar date. Removable: a calendar
    entry, not a business record."""

    day = models.DateField(unique=True)
    title = models.CharField(max_length=120)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["day"]
        constraints = [models.CheckConstraint(condition=Q(title__regex=r"\S"), name="holiday_title_nonblank")]


DEFAULT_SURVEY_TEXT = (
    "{نام} گرامی، پروندهٔ {پرونده} بسته شد. لطفاً رضایت خود را با پاسخ یک عدد از ۱ (کم) تا ۵ (زیاد) "
    "به همین پیامک اعلام کنید."
)


class AfterSalesSettings(models.Model):
    """What happens around a deadline and after a case closes, one row (2.40.61, BIZ-008).

    Panel warnings are always on. `sms_alerts` also texts the assignee (and
    the managers, once a deadline has passed); `escalate_overdue` hands an
    overdue case to the managers; `survey_sms` asks the customer for a
    satisfaction score when a case closes, in `survey_text`. Every text needs
    the outbound SMS feature and a configured provider.
    """

    sms_alerts = models.BooleanField(default=False)
    escalate_overdue = models.BooleanField(default=False)
    survey_sms = models.BooleanField(default=False)
    survey_text = models.CharField(max_length=500, default=DEFAULT_SURVEY_TEXT)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="after_sales_settings_singleton"),
            models.CheckConstraint(condition=Q(survey_text__regex=r"\S"), name="after_sales_survey_text_nonblank"),
        ]


class AfterSalesRequest(TimeStampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="after_sales_requests")
    sale = models.ForeignKey(Sale, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_requests")
    document = models.ForeignKey(SalesDocument, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_requests")
    subject = models.CharField(max_length=200)
    description = models.CharField(max_length=4000)
    status = models.CharField(max_length=80, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_after_sales_requests")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_after_sales_requests")
    closed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    #: The follow-up calendar's own field on Lead (`next_follow_up_at`) named
    #: this exact gap in DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §7 phase E: the
    #: lead side of the calendar shipped in 1.7.1, the after-sales side never
    #: had a field to draw from. Mirrors that one directly — same shape, same
    #: "null means nothing scheduled" meaning — set only through
    #: `schedule_after_sales_appointment` (aftersales/services.py), never
    #: through the general create/update path.
    next_appointment_at = models.DateTimeField(null=True, blank=True, db_index=True)
    #: 2.40.60 (BIZ-008): what the case is, where it stands, how urgent, and
    #: how it ended. `status` stays, mirroring the stage's name from now on;
    #: a case from before keeps the words it had.
    case_type = models.ForeignKey(CaseType, null=True, blank=True, on_delete=models.PROTECT, related_name="cases")
    stage = models.CharField(max_length=KEY_MAX, default="registered", db_index=True)
    priority = models.CharField(max_length=10, default="normal", db_index=True)
    #: Set when closed: «حل‌شده»، «حل‌نشده»، «مختومه با توافق مشتری». Empty on
    #: a case closed before 2.40.60 — not guessed.
    final_result = models.CharField(max_length=12, blank=True)
    #: The deadlines, written when the case is made or its priority or type
    #: changes (`aftersales.sla`), and when each was met.
    response_due = models.DateTimeField(null=True, blank=True, db_index=True)
    plan_due = models.DateTimeField(null=True, blank=True)
    resolution_due = models.DateTimeField(null=True, blank=True, db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    planned_at = models.DateTimeField(null=True, blank=True)
    #: Handed to the managers when a deadline passed unmet (2.40.61, when the
    #: company turns `AfterSalesSettings.escalate_overdue` on).
    escalated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(priority__in=PRIORITIES), name="after_sales_priority_valid"),
            models.CheckConstraint(condition=Q(final_result__in=["", *RESULTS]), name="after_sales_final_result_valid"),
            models.CheckConstraint(condition=Q(stage__regex=KEY_SHAPE), name="after_sales_stage_key_shape"),
            models.CheckConstraint(condition=models.Q(subject__regex=r"\S"), name="after_sales_subject_nonblank"),
            models.CheckConstraint(condition=models.Q(description__regex=r"\S"), name="after_sales_description_nonblank"),
            models.CheckConstraint(condition=models.Q(status__regex=r"\S"), name="after_sales_status_nonblank"),
        ]
        indexes = [
            models.Index(fields=["assigned_to", "status", "-created_at"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["assigned_to", "next_appointment_at"]),
        ]


class AfterSalesHistory(models.Model):
    class Event(models.TextChoices):
        CREATED = "created", "Created"
        ASSIGNED = "assigned", "Assigned"
        STATUS_CHANGED = "status_changed", "Status changed"
        CLOSED = "closed", "Closed"
        APPOINTMENT_SCHEDULED = "appointment_scheduled", "Appointment scheduled"
        # 2.40.60
        REOPENED = "reopened", "Reopened"
        PRIORITY_CHANGED = "priority_changed", "Priority changed"
        TYPE_CHANGED = "type_changed", "Type changed"
        PLANNED = "planned", "Plan recorded"
        # 2.40.61
        ESCALATED = "escalated", "Escalated"
        SURVEY_SENT = "survey_sent", "Survey sent"

    request = models.ForeignKey(AfterSalesRequest, on_delete=models.PROTECT, related_name="history")
    event = models.CharField(max_length=32, choices=Event.choices)
    #: Empty for what the system did on its own: an escalation, a survey (2.40.61).
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_changes")
    from_status = models.CharField(max_length=80, blank=True)
    to_status = models.CharField(max_length=80, blank=True)
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_assignments_lost")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="after_sales_assignments_received")
    #: Set only on an `appointment_scheduled` row — the value `next_
    #: appointment_at` was changed to (null clears a scheduled appointment).
    appointment_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(event__in=[
                    "created", "assigned", "status_changed", "closed", "appointment_scheduled",
                    "reopened", "priority_changed", "type_changed", "planned", "escalated", "survey_sent",
                ]),
                name="after_sales_history_event_valid",
            ),
        ]
        indexes = [models.Index(fields=["request", "-created_at"])]


class SlaAlert(models.Model):
    """One warning about one deadline, sent once (2.40.61).

    `approaching` is written when four fifths of the time is gone, `breached`
    when the deadline passes unmet. What it set off — a text, an escalation —
    happened once, because the row exists only once."""

    class Kind(models.TextChoices):
        RESPONSE = "response", "پاسخ اولیه"
        PLAN = "plan", "برنامهٔ رسیدگی"
        RESOLUTION = "resolution", "حل پرونده"

    class Level(models.TextChoices):
        APPROACHING = "approaching", "نزدیک مهلت"
        BREACHED = "breached", "گذشته از مهلت"

    request = models.ForeignKey(AfterSalesRequest, on_delete=models.PROTECT, related_name="sla_alerts")
    kind = models.CharField(max_length=12, choices=Kind.choices)
    level = models.CharField(max_length=12, choices=Level.choices)
    due_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    sms_sent = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["request", "kind", "level", "due_at"], name="uniq_sla_alert"),
            models.CheckConstraint(condition=Q(kind__in=["response", "plan", "resolution"]), name="sla_alert_kind_valid"),
            models.CheckConstraint(condition=Q(level__in=["approaching", "breached"]), name="sla_alert_level_valid"),
        ]
