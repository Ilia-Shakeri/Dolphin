"""Campaign services (2.36.0): the campaign entity, its people, and their stages.

Everything here is gated by the `campaigns` feature at the API boundary
(`sales.campaign_views`); the services themselves enforce role capability and
object scope, as the rest of `sales` does. Nothing here reaches into billing —
invoices are attributed by `sales.campaign_attribution`, called from billing.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.access import has_any_capability, is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from common.phones import normalize_customer_phone
from sales.customer_backfill import clean_label, normalize_label
from sales.models import CAMPAIGN_NAME_MAX_LENGTH, Campaign, Customer, Lead, TargetAudienceMember
from sales.services import (
    ELEVATED_OPERATORS,
    _lock_active_actor,
    _lock_operational_actor,
    refresh_target_member_status,
)

SYSTEM_CAMPAIGNS = {
    "direct": ("ورودی مستقیم", Campaign.Channel.OTHER),
    "referral": ("معرفی", Campaign.Channel.REFERRAL),
    "legacy": ("بدون کمپین (قدیمی)", Campaign.Channel.OTHER),
}

#: Which status a campaign may move to from each status. Archived is final in
#: the panel; nothing is ever deleted by changing status.
STATUS_TRANSITIONS = {
    Campaign.Status.DRAFT: {Campaign.Status.ACTIVE, Campaign.Status.ARCHIVED},
    Campaign.Status.ACTIVE: {Campaign.Status.PAUSED, Campaign.Status.FINISHED},
    Campaign.Status.PAUSED: {Campaign.Status.ACTIVE, Campaign.Status.FINISHED},
    Campaign.Status.FINISHED: {Campaign.Status.ARCHIVED, Campaign.Status.ACTIVE},
    Campaign.Status.ARCHIVED: set(),
}

CAMPAIGN_EDITABLE = {"name", "channels", "starts_on", "ends_on", "target_count", "budget", "responsibles"}
MEMBER_STAGES_SETTABLE = {
    TargetAudienceMember.Stage.NEW,
    TargetAudienceMember.Stage.CONTACTED,
    TargetAudienceMember.Stage.ENGAGED,
    TargetAudienceMember.Stage.LOST,
}


def _require_manager(actor):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "campaigns.manage"):
        raise BusinessPermissionDenied("مدیریت کمپین‌ها مجاز نیست.")
    return actor


def _clean_name(value):
    name = clean_label(value)
    if not name:
        raise BusinessRuleError({"name": "نام کمپین الزامی است."})
    if len(name) > CAMPAIGN_NAME_MAX_LENGTH:
        raise BusinessRuleError({"name": f"نام کمپین نباید بیش از {CAMPAIGN_NAME_MAX_LENGTH} نویسه باشد."})
    return name, normalize_label(name)


def _validate_responsibles(users):
    for user in users:
        if not is_crm_identity(user) or not user.is_active or user.role not in {User.Role.SALES_AGENT, *ELEVATED_OPERATORS}:
            raise BusinessRuleError({"responsibles": "مسئول کمپین باید کاربر فعالِ فروش یا مدیریت باشد."})


def clean_channels(value):
    """A de-duplicated, ordered list of valid `Campaign.Channel` values (at least one)."""
    if isinstance(value, str) or not isinstance(value, (list, tuple, set)):
        raise BusinessRuleError({"channels": "راه‌های ارتباط باید فهرست باشد."})
    cleaned = []
    for item in value:
        if item not in Campaign.Channel.values:
            raise BusinessRuleError({"channels": "راه ارتباط نامعتبر است."})
        if item not in cleaned:
            cleaned.append(item)
    if not cleaned:
        raise BusinessRuleError({"channels": "حداقل یک راه ارتباط انتخاب کنید."})
    return cleaned


def channel_labels(campaign):
    labels = dict(Campaign.Channel.choices)
    values = campaign.channels or [campaign.channel]
    return [str(labels[value]) for value in values if value in labels]


def _validate_numbers(data):
    if data.get("target_count") is not None and data["target_count"] < 0:
        raise BusinessRuleError({"target_count": "هدف نمی‌تواند منفی باشد."})
    if data.get("budget") is not None and data["budget"] < 0:
        raise BusinessRuleError({"budget": "بودجه نمی‌تواند منفی باشد."})
    starts, ends = data.get("starts_on"), data.get("ends_on")
    if starts and ends and ends < starts:
        raise BusinessRuleError({"ends_on": "تاریخ پایان نمی‌تواند پیش از شروع باشد."})


@transaction.atomic
def ensure_system_campaigns(actor):
    """Create the three campaigns every deployment has. Idempotent."""
    actor = _lock_active_actor(actor)
    made = {}
    for key, (name, channel) in SYSTEM_CAMPAIGNS.items():
        campaign = Campaign.objects.filter(system_key=key).first()
        if campaign is None:
            clean, normalized = _clean_name(name)
            campaign, _ = Campaign.objects.get_or_create(
                normalized_name=normalized,
                defaults={
                    "name": clean, "channel": channel, "channels": [channel], "status": Campaign.Status.ACTIVE,
                    "system_key": key, "created_by": actor, "updated_by": actor,
                },
            )
            if not campaign.system_key:
                campaign.system_key = key
                campaign.save(update_fields=["system_key", "updated_at"])
        made[key] = campaign
    return made


@transaction.atomic
def create_campaign(*, actor, name, responsibles=(), **data):
    actor = _require_manager(actor)
    unknown = set(data) - CAMPAIGN_EDITABLE
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    clean, normalized = _clean_name(name)
    data["channels"] = clean_channels(data.get("channels", [Campaign.Channel.PHONE]))
    data["channel"] = data["channels"][0]
    _validate_numbers(data)
    _validate_responsibles(responsibles)
    try:
        with transaction.atomic():
            campaign = Campaign.objects.create(
                name=clean, normalized_name=normalized, created_by=actor, updated_by=actor, **data
            )
    except IntegrityError as exc:
        raise BusinessConflictError({"name": "کمپینی با این نام وجود دارد."}) from exc
    campaign.responsibles.set(responsibles)
    log_activity(actor=actor, operation="campaign.created", instance=campaign, changes={"fields": sorted(data)})
    return campaign


@transaction.atomic
def update_campaign(*, actor, campaign, **changes):
    actor = _require_manager(actor)
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    unknown = set(changes) - CAMPAIGN_EDITABLE
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    responsibles = changes.pop("responsibles", None)
    if "name" in changes:
        if locked.system_key:
            raise BusinessRuleError({"name": "نام کمپین سیستمی قابل تغییر نیست."})
        changes["name"], changes["normalized_name"] = _clean_name(changes["name"])
    if "channels" in changes:
        changes["channels"] = clean_channels(changes["channels"])
        changes["channel"] = changes["channels"][0]
    _validate_numbers({**{f: getattr(locked, f) for f in ("target_count", "budget", "starts_on", "ends_on")}, **changes})
    changed = [field for field, value in changes.items() if getattr(locked, field) != value]
    for field in changed:
        setattr(locked, field, changes[field])
    if changed:
        locked.updated_by = actor
        try:
            with transaction.atomic():
                locked.save(update_fields=[*changed, "updated_by", "updated_at"])
        except IntegrityError as exc:
            raise BusinessConflictError({"name": "کمپینی با این نام وجود دارد."}) from exc
    if responsibles is not None:
        _validate_responsibles(responsibles)
        locked.responsibles.set(responsibles)
        changed.append("responsibles")
    if changed:
        log_activity(actor=actor, operation="campaign.updated", instance=locked, changes={"fields": sorted(changed)})
    return locked


@transaction.atomic
def set_campaign_status(*, actor, campaign, status):
    actor = _require_manager(actor)
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    if status not in Campaign.Status.values:
        raise BusinessRuleError({"status": "وضعیت نامعتبر است."})
    if status not in STATUS_TRANSITIONS[locked.status]:
        raise BusinessConflictError({"status": "این تغییر وضعیت برای کمپین مجاز نیست."})
    if locked.system_key and status == Campaign.Status.ARCHIVED:
        raise BusinessConflictError({"status": "کمپین سیستمی بایگانی نمی‌شود."})
    previous = locked.status
    locked.status, locked.updated_by = status, actor
    locked.save(update_fields=["status", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="campaign.status_changed", instance=locked, changes={"from": previous, "to": status})
    return locked


def container_lead(campaign, actor):
    """The hidden work container other modules (interactions, sales,
    quotations…) point at for this campaign. Created on first use."""
    lead = campaign.leads.filter(source="campaign").order_by("id").first()
    if lead is not None:
        return lead
    return Lead.objects.create(
        customer=None, source="campaign", campaign_or_batch=campaign.name[:100],
        campaign=campaign, created_by=actor, source_payload={},
    )


@transaction.atomic
def add_campaign_member(*, actor, campaign, full_name, raw_phone, notes="", assigned_to=None):
    actor = _lock_operational_actor(actor)
    if actor.role == User.Role.SALES_AGENT:
        raise BusinessPermissionDenied("افزودن مخاطب به کمپین مجاز نیست.")
    locked = Campaign.objects.select_for_update().get(pk=campaign.pk)
    if locked.status == Campaign.Status.ARCHIVED:
        raise BusinessConflictError({"campaign": "کمپین بایگانی‌شده مخاطب تازه نمی‌پذیرد."})
    name = str(full_name).strip()
    if not name:
        raise BusinessRuleError({"full_name": "این فیلد الزامی است."})
    normalized = normalize_customer_phone(raw_phone)
    if TargetAudienceMember.objects.filter(campaign=locked, normalized_phone=normalized).exists():
        raise BusinessConflictError({"raw_phone": "این شماره قبلاً در این کمپین ثبت شده است."})
    lead = container_lead(locked, actor)
    was_customer = Customer.objects.filter(
        phones__normalized_phone=normalized, phones__is_active=True
    ).exists()
    fields = {}
    if assigned_to is not None:
        target = _agent_target(assigned_to)
        fields = {"assigned_to": target, "assigned_by": actor, "assigned_at": timezone.now()}
    try:
        with transaction.atomic():
            member = TargetAudienceMember.objects.create(
                lead=lead, campaign=locked, full_name=name, raw_phone=raw_phone, normalized_phone=normalized,
                status=TargetAudienceMember.Status.LEAD, notes=notes, created_by=actor, updated_by=actor,
                was_customer_on_entry=was_customer, **fields,
            )
    except IntegrityError as exc:
        raise BusinessConflictError({"raw_phone": "این شماره قبلاً در این کمپین ثبت شده است."}) from exc
    log_activity(actor=actor, operation="campaign_member.added", instance=member, changes={"campaign": locked.pk})
    return refresh_target_member_status(member=member, actor=actor)


def _agent_target(user):
    target = User.objects.filter(pk=user.pk, is_active=True).first()
    if target is None or not is_crm_identity(target) or target.role != User.Role.SALES_AGENT:
        raise BusinessRuleError({"assigned_to": "مقصد باید یک بازاریاب فعال باشد."})
    return target


@transaction.atomic
def assign_campaign_member(*, actor, member, to_user, reason=""):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("واگذاری مخاطب مجاز نیست.")
    locked = TargetAudienceMember.objects.select_for_update().get(pk=member.pk)
    target = _agent_target(to_user)
    if locked.assigned_to_id == target.pk:
        raise BusinessConflictError({"to_user": "این مخاطب قبلاً به این کاربر واگذار شده است."})
    previous = locked.assigned_to_id
    locked.assigned_to, locked.assigned_by, locked.assigned_at = target, actor, timezone.now()
    locked.updated_by = actor
    locked.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "updated_by", "updated_at"])
    log_activity(
        actor=actor, operation="campaign_member.assigned", instance=locked,
        changes={"from_user": previous, "to_user": target.pk, "reason_provided": bool(reason)},
    )
    return locked


@transaction.atomic
def set_member_stage(*, actor, member, stage, lost_reason=""):
    """Move a person between the stages a person may set by hand.

    `converted` is never typed in: it follows a valid attributed invoice.
    """
    actor = _lock_operational_actor(actor)
    locked = TargetAudienceMember.objects.select_for_update().get(pk=member.pk)
    if actor.role == User.Role.SALES_AGENT and locked.assigned_to_id != actor.pk:
        raise BusinessPermissionDenied("این مخاطب خارج از دسترسی شماست.")
    if stage not in MEMBER_STAGES_SETTABLE:
        raise BusinessRuleError({"stage": "این مرحله به‌صورت دستی قابل تنظیم نیست."})
    if locked.stage == TargetAudienceMember.Stage.CONVERTED:
        raise BusinessConflictError({"stage": "مخاطب تبدیل‌شده با فاکتور معتبر است و مرحله‌اش دستی تغییر نمی‌کند."})
    if stage == TargetAudienceMember.Stage.LOST and not str(lost_reason).strip():
        raise BusinessRuleError({"lost_reason": "دلیل ازدست‌رفتن را بنویسید."})
    previous = locked.stage
    locked.stage = stage
    locked.lost_reason = str(lost_reason).strip()[:300] if stage == TargetAudienceMember.Stage.LOST else ""
    locked.updated_by = actor
    locked.save(update_fields=["stage", "lost_reason", "updated_by", "updated_at"])
    log_activity(
        actor=actor, operation="campaign_member.stage_changed", instance=locked,
        changes={"from": previous, "to": stage},
    )
    return locked


def advance_stage_on_contact(member):
    """A first logged interaction moves a brand-new person to «تماس گرفته‌شده».

    Never moves anyone backwards, and never touches a converted or lost one.
    """
    if member is not None and member.stage == TargetAudienceMember.Stage.NEW:
        TargetAudienceMember.objects.filter(pk=member.pk, stage=TargetAudienceMember.Stage.NEW).update(
            stage=TargetAudienceMember.Stage.CONTACTED, updated_at=timezone.now()
        )
