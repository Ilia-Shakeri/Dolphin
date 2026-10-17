"""Lead and campaign-person stages (2.40.57, BIZ-002).

Product owner, 2026-10-17:

* stages are the company's to shape, from a set default: for a lead «جدید،
  تماس اولیه، نیازسنجی، واجد شرایط، ارسال پیش‌فاکتور، مذاکره، برنده،
  بازنده»; a campaign person keeps its own five («جدید، تماس گرفته‌شده، در
  تعامل، تبدیل‌شده، ازدست‌رفته») — one data structure, two workflows;
* «برنده» and «بازنده» are final; going back from one needs a reason, and the
  history keeps it;
* skipping stages is allowed;
* «بازنده» needs a reason from a list, and «سایر» a note as well;
* a sales agent moves the leads that are theirs; a manager moves any in
  scope; every move is in the history;
* a definite sale is a valid invoice, never a stage set by hand.

Three controls, as everywhere:

* **feature availability** — moving a lead is part of `leads`, a campaign
  person part of `campaigns`; *shaping* the lists (adding, renaming,
  reordering, turning off) needs `customization`;
* **role permission** — moving needs the record's own write capability
  (`leads.manage`, `campaigns.work`); shaping needs `customization.manage`;
* **object scope** — the record's own, and a sales agent only their own.
"""

from django.db import transaction
from django.utils import timezone

from accounts.access import has_any_capability
from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.customer_backfill import clean_label, normalize_label
from sales.models import (
    LOST_NOTE_MAX_LENGTH,
    PIPELINE_LABEL_MAX_LENGTH,
    STAGE_REASON_MAX_LENGTH,
    Lead,
    LostReason,
    PipelineStage,
    StageChange,
    TargetAudienceMember,
)

LEAD = PipelineStage.Pipeline.LEAD
CAMPAIGN = PipelineStage.Pipeline.CAMPAIGN
OPEN, WON, LOST = PipelineStage.Kind.OPEN, PipelineStage.Kind.WON, PipelineStage.Kind.LOST
CONFIGURE_FEATURE = "customization"
CONFIGURE_CAPABILITY = "customization.manage"
OTHER_REASON = "other"
MAX_STAGES_PER_PIPELINE = 20
MAX_LOST_REASONS = 30

#: The seeded stages: (key, label, kind, qualifies, manual). Also read by the
#: migration that seeds them, so a fresh install and an upgraded one agree.
DEFAULT_STAGES = {
    LEAD: (
        ("new", "جدید", OPEN, False, True),
        ("first_contact", "تماس اولیه", OPEN, False, True),
        ("needs_analysis", "نیازسنجی", OPEN, False, True),
        ("qualified", "واجد شرایط", OPEN, True, True),
        ("quote_sent", "ارسال پیش‌فاکتور", OPEN, True, True),
        ("negotiation", "مذاکره", OPEN, True, True),
        ("won", "برنده", WON, True, True),
        ("lost", "بازنده", LOST, False, True),
    ),
    CAMPAIGN: (
        ("new", "جدید", OPEN, False, True),
        ("contacted", "تماس گرفته‌شده", OPEN, False, True),
        ("engaged", "در تعامل", OPEN, False, True),
        # Reached only through a valid invoice attributed to the campaign
        # (`sales.campaign_attribution`).
        ("converted", "تبدیل‌شده", WON, True, False),
        ("lost", "ازدست‌رفته", LOST, False, True),
    ),
}

#: (key, label, needs_note)
DEFAULT_LOST_REASONS = (
    ("price", "قیمت نامناسب", False),
    ("competitor", "خرید از رقیب", False),
    ("no_need", "عدم نیاز", False),
    ("unresponsive", "عدم پاسخ‌گویی پس از پیگیری‌های لازم", False),
    ("invalid_data", "نامعتبر بودن اطلاعات", False),
    ("purchase_cancelled", "لغو خرید", False),
    (OTHER_REASON, "سایر", True),
)

#: What `Lead.status` says for each kind of stage.
LEAD_STATUS_FOR_KIND = {
    OPEN: Lead.Status.PENDING,
    WON: Lead.Status.COMPLETED,
    LOST: Lead.Status.CANCELLED,
}


# --- reading -----------------------------------------------------------------------


def ensure_defaults():
    """The seeded stages and reasons, put back if a table is empty.

    Migration 0038 seeds them; this only matters where the tables were emptied
    afterwards (a test database flushed between tests), so a workflow is never
    without its stages.
    """
    for pipeline, rows in DEFAULT_STAGES.items():
        if PipelineStage.objects.filter(pipeline=pipeline).exists():
            continue
        for position, (key, label, kind, qualifies, manual) in enumerate(rows, start=1):
            PipelineStage.objects.get_or_create(
                pipeline=pipeline, key=key,
                defaults={"label": label, "kind": kind, "position": position, "qualifies": qualifies,
                          "manual": manual, "is_system": True},
            )
    if not LostReason.objects.exists():
        for position, (key, label, needs_note) in enumerate(DEFAULT_LOST_REASONS, start=1):
            LostReason.objects.get_or_create(
                key=key, defaults={"label": label, "needs_note": needs_note, "position": position, "is_system": True},
            )


def stages(pipeline, *, active_only=False):
    queryset = PipelineStage.objects.filter(pipeline=pipeline)
    if active_only:
        queryset = queryset.filter(is_active=True)
    rows = list(queryset.order_by("position", "id"))
    if not rows and not PipelineStage.objects.filter(pipeline=pipeline).exists():
        ensure_defaults()
        rows = list(queryset.order_by("position", "id"))
    return rows


def stage_by_key(pipeline):
    return {stage.key: stage for stage in stages(pipeline)}


def lost_reasons(*, active_only=False):
    queryset = LostReason.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    rows = list(queryset.order_by("position", "id"))
    if not rows and not LostReason.objects.exists():
        ensure_defaults()
        rows = list(queryset.order_by("position", "id"))
    return rows


def stage_label(pipeline, key, *, known=None):
    """A stage's name, or the key itself for one the table does not hold."""
    stage = (known if known is not None else stage_by_key(pipeline)).get(key)
    return stage.label if stage is not None else key


def first_open_stage(pipeline):
    """Where a new record starts: the first open stage still on."""
    return next((stage for stage in stages(pipeline) if stage.kind == OPEN and stage.is_active), None)


def qualifying_keys(pipeline):
    return {stage.key for stage in stages(pipeline) if stage.qualifies}


def serialize_stage(stage):
    return {
        "id": stage.pk, "pipeline": stage.pipeline, "key": stage.key, "label": stage.label,
        "kind": stage.kind, "kind_display": stage.get_kind_display(), "position": stage.position,
        "qualifies": stage.qualifies, "manual": stage.manual, "is_system": stage.is_system,
        "is_active": stage.is_active,
    }


def serialize_reason(reason):
    return {
        "id": reason.pk, "key": reason.key, "label": reason.label, "needs_note": reason.needs_note,
        "position": reason.position, "is_system": reason.is_system, "is_active": reason.is_active,
    }


def pipeline_payload():
    """Both workflows and the lost reasons, as a page embeds them."""
    return {
        "stages": {pipeline: [serialize_stage(stage) for stage in stages(pipeline)] for pipeline in (LEAD, CAMPAIGN)},
        "lost_reasons": [serialize_reason(reason) for reason in lost_reasons()],
    }


def serialize_change(change):
    actor = change.actor
    return {
        "id": change.pk, "from_stage": change.from_stage, "from_label": change.from_label,
        "to_stage": change.to_stage, "to_label": change.to_label,
        "lost_reason": change.lost_reason_key, "lost_reason_label": change.lost_reason_label,
        "note": change.note, "reason": change.reason, "reopened": change.reopened,
        "source": change.source, "source_display": change.get_source_display(),
        "actor": actor.pk if actor else None,
        "actor_display": (actor.get_full_name() or actor.username) if actor else "سامانه",
        "changed_at": change.changed_at.isoformat(),
    }


# --- one move ------------------------------------------------------------------------


def _clean_text(value, *, field, limit):
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise BusinessRuleError({field: f"این فیلد نباید بیش از {limit} نویسه داشته باشد."})
    return text


def _plan_move(pipeline, current_key, target_key, *, lost_reason, note, reason):
    """Check one move against the rules; what to write, or a clear refusal."""
    known = stage_by_key(pipeline)
    target = known.get(str(target_key or ""))
    if target is None:
        raise BusinessRuleError({"stage": "این مرحله وجود ندارد."})
    if target.key == current_key:
        raise BusinessConflictError({"stage": "هم‌اکنون در همین مرحله است."})
    if not target.is_active:
        raise BusinessRuleError({"stage": "این مرحله خاموش است و کسی به آن برده نمی‌شود."})
    if not target.manual:
        raise BusinessRuleError({"stage": "این مرحله با فاکتور معتبر می‌رسد و دستی تنظیم نمی‌شود."})
    current = known.get(current_key)
    if current is not None and not current.manual:
        raise BusinessConflictError({"stage": "این مرحله با فاکتور معتبر رسیده است و دستی تغییر نمی‌کند."})
    note = _clean_text(note, field="note", limit=LOST_NOTE_MAX_LENGTH)
    reason = _clean_text(reason, field="reason", limit=STAGE_REASON_MAX_LENGTH)
    reopened = current is not None and current.kind != OPEN
    if reopened and not reason:
        raise BusinessRuleError({"reason": "برای بیرون آوردن از مرحلهٔ پایانی، دلیل را بنویسید."})
    lost = None
    if target.kind == LOST:
        lost = next((item for item in lost_reasons(active_only=True) if item.key == str(lost_reason or "")), None)
        if lost is None:
            raise BusinessRuleError({"lost_reason": "دلیل را از فهرست انتخاب کنید."})
        if lost.needs_note and not note:
            raise BusinessRuleError({"note": "برای این دلیل، توضیح بنویسید."})
    return {"current": current, "target": target, "lost": lost, "note": note, "reason": reason, "reopened": reopened}


def _history(*, pipeline, plan, actor, source, current_key, lead=None, member=None):
    lost = plan["lost"]
    return StageChange.objects.create(
        pipeline=pipeline, lead=lead, member=member,
        from_stage=current_key or "", from_label=plan["current"].label if plan["current"] else (current_key or ""),
        to_stage=plan["target"].key, to_label=plan["target"].label,
        lost_reason_key=lost.key if lost else "", lost_reason_label=lost.label if lost else "",
        note=plan["note"],
        reason=plan["reason"], reopened=plan["reopened"], source=source, actor=actor,
    )


def _may_move_lead(actor, lead):
    """A sales agent's own leads: assigned to them, or theirs and unassigned."""
    if actor.role != User.Role.SALES_AGENT:
        return True
    if lead.assigned_to_id is not None:
        return lead.assigned_to_id == actor.pk
    return lead.created_by_id == actor.pk


@transaction.atomic
def set_lead_stage(*, actor, lead, stage, lost_reason="", note="", reason=""):
    """Move a lead to `stage`; `status` and the history follow."""
    from sales.services import _lock_operational_actor

    actor = _lock_operational_actor(actor)
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if not _may_move_lead(actor, locked):
        raise BusinessPermissionDenied("این سرنخ خارج از دسترسی شماست.")
    plan = _plan_move(LEAD, locked.stage, stage, lost_reason=lost_reason, note=note, reason=reason)
    previous = locked.stage
    target, lost = plan["target"], plan["lost"]
    now = timezone.now()
    locked.stage = target.key
    locked.status = LEAD_STATUS_FOR_KIND[target.kind]
    locked.lost_reason_key = lost.key if lost else ""
    locked.lost_reason = plan["note"] if lost else ""
    locked.stage_changed_at = now
    locked.closed_at = now if target.kind != OPEN else None
    locked.save(update_fields=[
        "stage", "status", "lost_reason_key", "lost_reason", "stage_changed_at", "closed_at", "updated_at",
    ])
    _history(pipeline=LEAD, plan=plan, actor=actor, source=StageChange.Source.MANUAL, current_key=previous, lead=locked)
    log_activity(
        actor=actor, operation="lead.stage_changed", instance=locked,
        changes={"from": previous, "to": target.key, "reopened": plan["reopened"],
                 "lost_reason": lost.key if lost else "", "reason_provided": bool(plan["reason"])},
    )
    return locked


def _may_move_member(actor, member):
    if actor.role != User.Role.SALES_AGENT:
        return True
    return member.assigned_to_id == actor.pk


@transaction.atomic
def set_member_stage(*, actor, member, stage, lost_reason="", note="", reason=""):
    """Move a campaign person to `stage` by hand.

    «تبدیل‌شده» is never typed in: it follows a valid attributed invoice
    (`sales.campaign_attribution`), and a converted person is not moved by
    hand either.
    """
    from sales.services import _lock_operational_actor

    actor = _lock_operational_actor(actor)
    locked = TargetAudienceMember.objects.select_for_update().get(pk=member.pk)
    if not _may_move_member(actor, locked):
        raise BusinessPermissionDenied("این مخاطب خارج از دسترسی شماست.")
    plan = _plan_move(CAMPAIGN, locked.stage, stage, lost_reason=lost_reason, note=note, reason=reason)
    previous = locked.stage
    target, lost = plan["target"], plan["lost"]
    locked.stage = target.key
    locked.lost_reason_key = lost.key if lost else ""
    locked.lost_reason = plan["note"] if lost else ""
    locked.updated_by = actor
    locked.save(update_fields=["stage", "lost_reason_key", "lost_reason", "updated_by", "updated_at"])
    _history(
        pipeline=CAMPAIGN, plan=plan, actor=actor, source=StageChange.Source.MANUAL, current_key=previous, member=locked,
    )
    log_activity(
        actor=actor, operation="campaign_member.stage_changed", instance=locked,
        changes={"from": previous, "to": target.key, "reopened": plan["reopened"],
                 "lost_reason": lost.key if lost else "", "reason_provided": bool(plan["reason"])},
    )
    return locked


def record_system_move(*, member, from_key, to_key, source):
    """History for a move the system made to a campaign person — a valid
    invoice converting them or releasing them, the first call moving them on."""
    known = stage_by_key(CAMPAIGN)
    StageChange.objects.create(
        pipeline=CAMPAIGN, member=member, from_stage=from_key or "",
        from_label=stage_label(CAMPAIGN, from_key, known=known) if from_key else "",
        to_stage=to_key, to_label=stage_label(CAMPAIGN, to_key, known=known), source=source,
    )


def history_for_lead(lead):
    return StageChange.objects.filter(lead=lead).select_related("actor").order_by("-changed_at", "-id")


def history_for_member(member):
    return StageChange.objects.filter(member=member).select_related("actor").order_by("-changed_at", "-id")


# --- shaping the lists (customization) ---------------------------------------------


def can_configure(user):
    return feature_enabled(CONFIGURE_FEATURE) and has_any_capability(user, CONFIGURE_CAPABILITY)


def _require_configurer(actor):
    if not can_configure(actor):
        raise BusinessPermissionDenied("تنظیم مراحل و دلیل‌ها مجاز نیست.")


def _clean_label(value, *, others):
    label = clean_label(value)
    if not label:
        raise BusinessRuleError({"label": "نام را بنویسید."})
    if len(label) > PIPELINE_LABEL_MAX_LENGTH:
        raise BusinessRuleError({"label": f"نام نباید بیش از {PIPELINE_LABEL_MAX_LENGTH} نویسه باشد."})
    if normalize_label(label) in {normalize_label(other) for other in others}:
        raise BusinessRuleError({"label": "این نام در همین فهرست هست."})
    return label


def _next_custom_key(keys):
    numbers = [int(key[1:]) for key in keys if key[:1] == "c" and key[1:].isdigit()]
    return f"c{max(numbers, default=0) + 1}"


def _check_pipeline(pipeline):
    if pipeline not in PipelineStage.Pipeline.values:
        raise BusinessRuleError({"pipeline": "بخش باید سرنخ یا افراد کمپین باشد."})


@transaction.atomic
def create_stage(*, actor, pipeline, label, qualifies=False):
    """A company's own open stage, placed after the last open one."""
    _require_configurer(actor)
    _check_pipeline(pipeline)
    existing = list(PipelineStage.objects.select_for_update().filter(pipeline=pipeline).order_by("position", "id"))
    if len(existing) >= MAX_STAGES_PER_PIPELINE:
        raise BusinessRuleError({"label": f"هر بخش حداکثر {MAX_STAGES_PER_PIPELINE} مرحله دارد."})
    label = _clean_label(label, others=[stage.label for stage in existing])
    last_open = max((index for index, stage in enumerate(existing) if stage.kind == OPEN), default=-1)
    ordered = existing[: last_open + 1] + [None] + existing[last_open + 1:]
    created = None
    for position, item in enumerate(ordered, start=1):
        if item is None:
            created = PipelineStage.objects.create(
                pipeline=pipeline, key=_next_custom_key([stage.key for stage in existing]), label=label,
                kind=OPEN, position=position, qualifies=bool(qualifies), is_system=False,
            )
        elif item.position != position:
            item.position = position
            item.save(update_fields=["position", "updated_at"])
    log_activity(actor=actor, operation="pipeline.stage_created", instance=created,
                 changes={"pipeline": pipeline, "key": created.key})
    return created


@transaction.atomic
def update_stage(*, actor, stage, **changes):
    """Rename, mark as qualifying, or turn an open stage off or on."""
    _require_configurer(actor)
    locked = PipelineStage.objects.select_for_update().get(pk=stage.pk)
    unknown = set(changes) - {"label", "qualifies", "is_active"}
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    changed = []
    if "label" in changes:
        others = PipelineStage.objects.filter(pipeline=locked.pipeline).exclude(pk=locked.pk).values_list("label", flat=True)
        label = _clean_label(changes["label"], others=list(others))
        if label != locked.label:
            locked.label = label
            changed.append("label")
    if "qualifies" in changes and bool(changes["qualifies"]) != locked.qualifies:
        if locked.kind == LOST:
            raise BusinessRuleError({"qualifies": "مرحلهٔ بازنده واجد شرایط شمرده نمی‌شود."})
        locked.qualifies = bool(changes["qualifies"])
        changed.append("qualifies")
    if "is_active" in changes and bool(changes["is_active"]) != locked.is_active:
        if locked.kind != OPEN:
            raise BusinessRuleError({"is_active": "مرحله‌های پایانی همیشه روشن‌اند."})
        if not changes["is_active"]:
            still_open = PipelineStage.objects.filter(
                pipeline=locked.pipeline, kind=OPEN, is_active=True,
            ).exclude(pk=locked.pk).exists()
            if not still_open:
                raise BusinessRuleError({"is_active": "دست‌کم یک مرحلهٔ باز باید روشن بماند."})
        locked.is_active = bool(changes["is_active"])
        changed.append("is_active")
    if changed:
        locked.save(update_fields=[*changed, "updated_at"])
        log_activity(actor=actor, operation="pipeline.stage_updated", instance=locked,
                     changes={"pipeline": locked.pipeline, "key": locked.key, "fields": sorted(changed)})
    return locked


@transaction.atomic
def move_stage(*, actor, stage, direction):
    """One place up or down among the open stages; the final two stay last."""
    _require_configurer(actor)
    if direction not in ("up", "down"):
        raise BusinessRuleError({"direction": "جهت باید بالا یا پایین باشد."})
    ordered = list(PipelineStage.objects.select_for_update().filter(pipeline=stage.pipeline).order_by("position", "id"))
    index = next(i for i, item in enumerate(ordered) if item.pk == stage.pk)
    if ordered[index].kind != OPEN:
        raise BusinessRuleError({"direction": "مرحله‌های پایانی جای خود را دارند."})
    other = index - 1 if direction == "up" else index + 1
    if 0 <= other < len(ordered) and ordered[other].kind == OPEN:
        ordered[index], ordered[other] = ordered[other], ordered[index]
    for position, item in enumerate(ordered, start=1):
        if item.position != position:
            item.position = position
            item.save(update_fields=["position", "updated_at"])
    return ordered


@transaction.atomic
def create_lost_reason(*, actor, label, needs_note=False):
    _require_configurer(actor)
    existing = list(LostReason.objects.select_for_update().order_by("position", "id"))
    if len(existing) >= MAX_LOST_REASONS:
        raise BusinessRuleError({"label": f"فهرست حداکثر {MAX_LOST_REASONS} دلیل دارد."})
    label = _clean_label(label, others=[reason.label for reason in existing])
    # Before «سایر», which stays last.
    other_index = next((i for i, reason in enumerate(existing) if reason.key == OTHER_REASON), len(existing))
    ordered = existing[:other_index] + [None] + existing[other_index:]
    created = None
    for position, item in enumerate(ordered, start=1):
        if item is None:
            created = LostReason.objects.create(
                key=_next_custom_key([reason.key for reason in existing]), label=label,
                needs_note=bool(needs_note), position=position,
            )
        elif item.position != position:
            item.position = position
            item.save(update_fields=["position", "updated_at"])
    log_activity(actor=actor, operation="pipeline.lost_reason_created", instance=created, changes={"key": created.key})
    return created


@transaction.atomic
def update_lost_reason(*, actor, reason, **changes):
    _require_configurer(actor)
    locked = LostReason.objects.select_for_update().get(pk=reason.pk)
    unknown = set(changes) - {"label", "needs_note", "is_active"}
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    changed = []
    if "label" in changes:
        others = LostReason.objects.exclude(pk=locked.pk).values_list("label", flat=True)
        label = _clean_label(changes["label"], others=list(others))
        if label != locked.label:
            locked.label = label
            changed.append("label")
    if "needs_note" in changes and bool(changes["needs_note"]) != locked.needs_note:
        if locked.key == OTHER_REASON:
            raise BusinessRuleError({"needs_note": "«سایر» همیشه توضیح می‌خواهد."})
        locked.needs_note = bool(changes["needs_note"])
        changed.append("needs_note")
    if "is_active" in changes and bool(changes["is_active"]) != locked.is_active:
        if locked.key == OTHER_REASON:
            raise BusinessRuleError({"is_active": "«سایر» همیشه روشن است."})
        locked.is_active = bool(changes["is_active"])
        changed.append("is_active")
    if changed:
        locked.save(update_fields=[*changed, "updated_at"])
        log_activity(actor=actor, operation="pipeline.lost_reason_updated", instance=locked,
                     changes={"key": locked.key, "fields": sorted(changed)})
    return locked


@transaction.atomic
def move_lost_reason(*, actor, reason, direction):
    _require_configurer(actor)
    if direction not in ("up", "down"):
        raise BusinessRuleError({"direction": "جهت باید بالا یا پایین باشد."})
    ordered = list(LostReason.objects.select_for_update().order_by("position", "id"))
    index = next(i for i, item in enumerate(ordered) if item.pk == reason.pk)
    other = index - 1 if direction == "up" else index + 1
    if 0 <= other < len(ordered):
        ordered[index], ordered[other] = ordered[other], ordered[index]
    for position, item in enumerate(ordered, start=1):
        if item.position != position:
            item.position = position
            item.save(update_fields=["position", "updated_at"])
    return ordered
