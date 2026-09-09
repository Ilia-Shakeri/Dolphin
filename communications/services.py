import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.access import has_any_capability, is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from common.phones import normalize_customer_phone
from communications import sms
from communications.models import (
    InboundSMS,
    OutboundSMS,
    SmsCampaign,
    SmsCampaignRecipient,
    SmsTemplate,
)
from sales.models import Customer, CustomerPhone, Lead


PROVIDER_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$", flags=re.ASCII)
E164_NUMBER = re.compile(r"^\+[1-9][0-9]{7,14}$", flags=re.ASCII)
METADATA_KEY = re.compile(r"^[a-z][a-z0-9_]{0,49}$", flags=re.ASCII)
BLOCKED_METADATA_FRAGMENTS = (
    "auth",
    "body",
    "content",
    "key",
    "message",
    "password",
    "payload",
    "secret",
    "signature",
    "token",
)
MAX_METADATA_KEYS = 20
MAX_METADATA_TEXT = 256
MAX_METADATA_BYTES = 4096


class IdempotencyConflict(BusinessConflictError):
    pass


@dataclass(frozen=True)
class NormalizedInboundSMSEvent:
    provider_code: str
    external_message_id: str
    sender_normalized: str
    recipient_normalized: str
    provider_received_at: datetime
    metadata: Mapping[str, str | int | bool | None]
    direction: str = InboundSMS.Direction.INBOUND


@dataclass(frozen=True)
class StoredInboundSMS:
    message: InboundSMS
    created: bool


def _clean_metadata(metadata):
    if not isinstance(metadata, Mapping):
        raise BusinessRuleError({"metadata": "متادیتا باید یک شیء باشد."})
    if len(metadata) > MAX_METADATA_KEYS:
        raise BusinessRuleError({"metadata": f"متادیتا حداکثر می‌تواند {MAX_METADATA_KEYS} فیلد داشته باشد."})
    cleaned = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not METADATA_KEY.fullmatch(key):
            raise BusinessRuleError({"metadata": "نام یکی از فیلدهای متادیتا نامعتبر است."})
        if any(fragment in key for fragment in BLOCKED_METADATA_FRAGMENTS):
            raise BusinessRuleError({"metadata": "متادیتا شامل نام فیلد محدودشده است."})
        if value is not None and (isinstance(value, float) or not isinstance(value, (str, int, bool))):
            raise BusinessRuleError({"metadata": "مقادیر متادیتا باید مقدارهای ساده و محدود باشند."})
        if isinstance(value, str) and len(value) > MAX_METADATA_TEXT:
            raise BusinessRuleError({"metadata": f"متن متادیتا حداکثر می‌تواند {MAX_METADATA_TEXT} نویسه داشته باشد."})
        cleaned[key] = value
    if len(json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_METADATA_BYTES:
        raise BusinessRuleError({"metadata": f"متادیتا حداکثر می‌تواند {MAX_METADATA_BYTES} بایت باشد."})
    return cleaned


def _validate_event(event):
    errors = {}
    provider_code = str(event.provider_code).strip().lower()
    external_message_id = str(event.external_message_id).strip()
    if not PROVIDER_CODE.fullmatch(provider_code):
        errors["provider_code"] = "کد ارائه‌دهنده نامعتبر است."
    if not external_message_id or len(external_message_id) > 160:
        errors["external_message_id"] = "شناسه پیام خارجی نامعتبر است."
    if not E164_NUMBER.fullmatch(str(event.sender_normalized)):
        errors["sender_normalized"] = "شماره فرستنده باید در قالب استاندارد E.164 باشد."
    if not E164_NUMBER.fullmatch(str(event.recipient_normalized)):
        errors["recipient_normalized"] = "شماره گیرنده باید در قالب استاندارد E.164 باشد."
    if event.direction != InboundSMS.Direction.INBOUND:
        errors["direction"] = "فقط پیامک ورودی پذیرفته می‌شود."
    if not isinstance(event.provider_received_at, datetime) or timezone.is_naive(event.provider_received_at):
        errors["provider_received_at"] = "زمان دریافت از ارائه‌دهنده باید شامل منطقه زمانی باشد."
    if errors:
        raise BusinessRuleError(errors)
    return provider_code, external_message_id, _clean_metadata(event.metadata)


def _deterministic_relations(sender_normalized):
    try:
        customer_phone = (
            CustomerPhone.objects.select_related("customer")
            .get(normalized_phone=sender_normalized, is_active=True)
        )
    except (CustomerPhone.DoesNotExist, CustomerPhone.MultipleObjectsReturned):
        return None, None
    customer = customer_phone.customer
    leads = list(customer.leads.order_by("id")[:2])
    lead = leads[0] if len(leads) == 1 else None
    return customer, lead


def _same_canonical_event(message, event, metadata):
    return (
        message.sender_normalized == event.sender_normalized
        and message.recipient_normalized == event.recipient_normalized
        and message.provider_received_at == event.provider_received_at
        and message.direction == event.direction
        and message.metadata == metadata
    )


@transaction.atomic
def store_normalized_inbound_sms(*, event, actor=None, system_received_at=None):
    provider_code, external_message_id, metadata = _validate_event(event)
    customer, lead = _deterministic_relations(event.sender_normalized)
    defaults = {
        "sender_normalized": event.sender_normalized,
        "recipient_normalized": event.recipient_normalized,
        "provider_received_at": event.provider_received_at,
        "system_received_at": system_received_at or timezone.now(),
        "direction": event.direction,
        "metadata": metadata,
        "body_retention_policy": InboundSMS.BodyRetentionPolicy.NOT_RETAINED,
        "processing_state": (
            InboundSMS.ProcessingState.LINKED if customer else InboundSMS.ProcessingState.UNMATCHED
        ),
        "customer": customer,
        "lead": lead,
    }
    try:
        with transaction.atomic():
            message, created = InboundSMS.objects.get_or_create(
                provider_code=provider_code,
                external_message_id=external_message_id,
                defaults=defaults,
            )
    except IntegrityError:
        message = InboundSMS.objects.get(
            provider_code=provider_code,
            external_message_id=external_message_id,
        )
        created = False
    if not created and not _same_canonical_event(message, event, metadata):
        raise IdempotencyConflict({"external_message_id": "این شناسه قبلاً برای داده‌ای متفاوت استفاده شده است."})
    if created:
        log_activity(
            actor=actor,
            operation="inbound_sms.stored",
            instance=message,
            changes={
                "fields": [
                    "provider_code",
                    "external_message_id",
                    "direction",
                    "processing_state",
                    "customer",
                    "lead",
                ]
            },
        )
    return StoredInboundSMS(message=message, created=created)


# --- Outbound SMS ------------------------------------------------------------
#
# The permission model is deliberately conservative for a first version: only
# `sms.company` — the same capability the inbound report already requires,
# held by sales_manager, company_it and platform_admin, not sales_agent — may
# send. Whether an agent should be able to message their own customers is a
# real product question nobody has asked for yet; narrowing later is a
# capability addition, not a migration, so nothing here forecloses it.

SMS_BODY_MAX_LENGTH = 640  # ~4 concatenated GSM-7 segments; a generous, bounded cap, not a carrier's exact limit


def _lock_active_actor(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked):
        raise BusinessPermissionDenied("کاربر باید فعال باشد.")
    return locked


def _lock_sms_sender(actor):
    locked = _lock_active_actor(actor)
    if not has_any_capability(locked, "sms.company"):
        raise BusinessPermissionDenied("ارسال پیامک مجاز نیست.")
    return locked


def _clean_body(body):
    cleaned = unicodedata.normalize("NFKC", str(body or "")).strip()
    if not cleaned:
        raise BusinessRuleError({"body": "متن پیامک الزامی است."})
    if len(cleaned) > SMS_BODY_MAX_LENGTH:
        raise BusinessRuleError({"body": f"متن پیامک نباید بیش از {SMS_BODY_MAX_LENGTH} نویسه باشد."})
    return cleaned


def _resolve_recipient(*, customer, phone):
    if customer is not None:
        # `CustomerPhone.Meta.ordering` puts an active primary phone first;
        # a customer with no active phone at all has nothing to send to.
        primary = customer.phones.filter(is_active=True).first()
        if primary is None:
            raise BusinessRuleError({"customer": "این مشتری شماره تلفن فعال ندارد."})
        return primary.normalized_phone
    if phone:
        try:
            return normalize_customer_phone(phone)
        except ValidationError as error:
            raise BusinessRuleError({"phone": "؛ ".join(error.messages)}) from error
    raise BusinessRuleError({"phone": "شماره گیرنده یا مشتری الزامی است."})


def send_outbound_sms(*, actor, body, customer=None, lead=None, phone=""):
    """Send one SMS and record exactly one outcome row for the attempt.

    Validation that can be checked before anything is attempted (permission,
    an empty body, no usable recipient, no provider configured at all) raises
    `BusinessRuleError`/`BusinessPermissionDenied` and writes nothing. Once an
    attempt is made — the provider was at least reachable enough to answer —
    the outcome (`sent` or `failed`) is always persisted and returned, never
    raised, so a provider-side failure is an auditable fact, not a swallowed
    exception. The row-lock on the actor happens in its own short transaction,
    released before the network call: an outbound HTTP request never runs
    while holding a database row lock.
    """
    with transaction.atomic():
        locked_actor = _lock_sms_sender(actor)

    cleaned_body = _clean_body(body)
    if lead is not None and customer is None:
        customer = lead.customer
    if lead is not None and customer is not None and lead.customer_id != customer.pk:
        raise BusinessRuleError({"lead": "سرنخ متعلق به این مشتری نیست."})
    recipient = _resolve_recipient(customer=customer, phone=phone)

    if not sms.provider_is_available():
        raise BusinessRuleError({"provider": "سرویس ارسال پیامک برای این استقرار تنظیم نشده است."})

    result = sms.send_via_configured_provider(to=recipient, body=cleaned_body)

    with transaction.atomic():
        message = OutboundSMS.objects.create(
            provider_code=result.provider_code,
            recipient_normalized=recipient,
            body_text=cleaned_body,
            status=OutboundSMS.Status.SENT if result.success else OutboundSMS.Status.FAILED,
            status_detail=result.status_detail[:255],
            customer=customer,
            lead=lead,
            sent_by=locked_actor,
        )
        changes = {"fields": ["recipient_normalized", "status", "customer", "lead"]}
        if result.success:
            log_activity(actor=locked_actor, operation="outbound_sms.sent", instance=message, changes=changes)
        else:
            log_activity(actor=locked_actor, operation="outbound_sms.failed", instance=message, changes=changes)
    return message


# A group send is bounded so one mistaken selection cannot queue the entire
# customer book. Not a carrier limit — a deliberate blast radius, the same
# reasoning behind every other cap in this module.
SMS_CAMPAIGN_MAX_RECIPIENTS = 500

# How many recipients one dispatcher pass will actually send. Each is a
# provider HTTP round trip, so this bounds both the cron run and — far more
# importantly — the opportunistic flush that runs inside a page request.
SMS_CAMPAIGN_DISPATCH_BATCH = 25
SMS_CAMPAIGN_REQUEST_FLUSH_BATCH = 5

#: The one substitution a template may make. Kept to a single, obvious token
#: rather than a general expression language: anything richer is a product
#: decision about what a template may read, not a formatting convenience.
TEMPLATE_NAME_TOKEN = "{نام}"


def render_sms_template(body, *, customer=None, lead=None):
    """Substitute the recipient's own name into a template body.

    Falls back to an empty string rather than leaving the token visible: a
    message reading "سلام {نام}" delivered verbatim is worse than one reading
    "سلام" — the reader sees a broken system either way, but only the first
    tells them so in the message itself.
    """
    if TEMPLATE_NAME_TOKEN not in body:
        return body
    holder = customer or (lead.customer if lead is not None else None)
    name = (getattr(holder, "full_name", "") or "").strip()
    return body.replace(TEMPLATE_NAME_TOKEN, name).strip()


def create_sms_template(*, actor, title, body):
    """Templates are managed by the same capability that sends: a message body
    saved for reuse is not a more privileged thing than a message."""
    with transaction.atomic():
        locked_actor = _lock_sms_sender(actor)
        cleaned_title = unicodedata.normalize("NFKC", str(title or "")).strip()
        if not cleaned_title:
            raise BusinessRuleError({"title": "عنوان قالب الزامی است."})
        if len(cleaned_title) > 120:
            raise BusinessRuleError({"title": "عنوان قالب نباید بیش از ۱۲۰ نویسه باشد."})
        cleaned_body = _clean_body(body)
        if SmsTemplate.objects.filter(title=cleaned_title).exists():
            raise BusinessRuleError({"title": "قالبی با همین عنوان از قبل هست."})
        template = SmsTemplate.objects.create(
            title=cleaned_title,
            body_text=cleaned_body,
            created_by=locked_actor,
        )
        log_activity(
            actor=locked_actor,
            operation="sms_template.created",
            instance=template,
            changes={"fields": ["title", "body_text"]},
        )
    return template


def delete_sms_template(*, actor, template_id):
    with transaction.atomic():
        locked_actor = _lock_sms_sender(actor)
        template = SmsTemplate.objects.select_for_update().filter(pk=template_id).first()
        if template is None:
            raise BusinessRuleError({"template": "قالب پیدا نشد."})
        log_activity(
            actor=locked_actor,
            operation="sms_template.deleted",
            instance=template,
            changes={"fields": ["title"]},
        )
        template.delete()


def _collect_campaign_recipients(*, customer_ids, lead_ids, phones):
    """Turn the three ways of naming recipients into one de-duplicated list.

    Order matters only for which record a number is attributed to: a number
    reached first through a customer keeps that customer, so the campaign view
    and the ordinary outbound log both show a person rather than a bare number.
    """
    collected = {}

    for customer in Customer.objects.filter(pk__in=list(customer_ids)[:SMS_CAMPAIGN_MAX_RECIPIENTS]):
        phone = customer.phones.filter(is_active=True).first()
        if phone is None:
            continue
        collected.setdefault(phone.normalized_phone, {"customer": customer, "lead": None})

    leads = Lead.objects.filter(
        pk__in=list(lead_ids)[:SMS_CAMPAIGN_MAX_RECIPIENTS]
    ).select_related("customer")
    for lead in leads:
        if lead.customer_id is None:
            continue
        phone = lead.customer.phones.filter(is_active=True).first()
        if phone is None:
            continue
        existing = collected.get(phone.normalized_phone)
        if existing is None:
            collected[phone.normalized_phone] = {"customer": lead.customer, "lead": lead}
        elif existing["lead"] is None and existing["customer"] is not None and existing["customer"].pk == lead.customer_id:
            existing["lead"] = lead

    for raw in list(phones)[:SMS_CAMPAIGN_MAX_RECIPIENTS]:
        if not str(raw).strip():
            continue
        try:
            normalized = normalize_customer_phone(raw)
        except ValidationError as error:
            raise BusinessRuleError({"phones": "؛ ".join(error.messages)}) from error
        collected.setdefault(normalized, {"customer": None, "lead": None})

    if not collected:
        raise BusinessRuleError({"recipients": "دست‌کم یک گیرندهٔ معتبر لازم است."})
    if len(collected) > SMS_CAMPAIGN_MAX_RECIPIENTS:
        raise BusinessRuleError(
            {"recipients": f"هر ارسال گروهی حداکثر {SMS_CAMPAIGN_MAX_RECIPIENTS} گیرنده می‌پذیرد."}
        )
    return collected


def create_sms_campaign(*, actor, body, scheduled_for=None, customer_ids=(), lead_ids=(), phones=()):
    """Queue one group or scheduled send. Nothing is sent here.

    `scheduled_for` omitted means "as soon as the dispatcher next runs", which
    for a deployment with either cron or ordinary page traffic is effectively
    immediately. A time in the future is honoured.
    """
    cleaned_body = _clean_body(body)
    now = timezone.now()
    if scheduled_for is not None and scheduled_for < now - timedelta(minutes=5):
        raise BusinessRuleError({"scheduled_for": "زمان ارسال نمی‌تواند در گذشته باشد."})
    when = scheduled_for or now

    with transaction.atomic():
        locked_actor = _lock_sms_sender(actor)
        collected = _collect_campaign_recipients(
            customer_ids=customer_ids, lead_ids=lead_ids, phones=phones
        )
        campaign = SmsCampaign.objects.create(
            body_text=cleaned_body,
            scheduled_for=when,
            status=SmsCampaign.Status.SCHEDULED,
            created_by=locked_actor,
        )
        SmsCampaignRecipient.objects.bulk_create(
            [
                SmsCampaignRecipient(
                    campaign=campaign,
                    customer=entry["customer"],
                    lead=entry["lead"],
                    recipient_normalized=number,
                )
                for number, entry in collected.items()
            ]
        )
        log_activity(
            actor=locked_actor,
            operation="sms_campaign.created",
            instance=campaign,
            changes={"fields": ["body_text", "scheduled_for"], "recipients": len(collected)},
        )
    return campaign


def cancel_sms_campaign(*, actor, campaign_id):
    """Stop a campaign that has not finished. Anything already sent stays
    sent — this cancels the remainder, it does not recall messages."""
    with transaction.atomic():
        locked_actor = _lock_sms_sender(actor)
        campaign = SmsCampaign.objects.select_for_update().filter(pk=campaign_id).first()
        if campaign is None:
            raise BusinessRuleError({"campaign": "کارزار پیدا نشد."})
        if campaign.status in {SmsCampaign.Status.COMPLETED, SmsCampaign.Status.CANCELLED}:
            raise BusinessRuleError({"campaign": "این کارزار از قبل پایان یافته است."})
        campaign.status = SmsCampaign.Status.CANCELLED
        campaign.finished_at = timezone.now()
        campaign.save(update_fields=["status", "finished_at", "updated_at"])
        log_activity(
            actor=locked_actor,
            operation="sms_campaign.cancelled",
            instance=campaign,
            changes={"fields": ["status"]},
        )
    return campaign


def _send_one_campaign_recipient(campaign, claimed_id):
    """One recipient's provider call and its two records: the ordinary
    `OutboundSMS` row every send writes, and this recipient's own outcome.

    Returns True when the provider accepted it. Never raises for a provider
    failure — the same reasoning as `send_outbound_sms`: one unreachable
    number must not abandon the rest of the batch.
    """
    recipient = SmsCampaignRecipient.objects.select_related("customer", "lead").get(pk=claimed_id)
    body = render_sms_template(campaign.body_text, customer=recipient.customer, lead=recipient.lead)
    try:
        result = sms.send_via_configured_provider(to=recipient.recipient_normalized, body=body)
    except Exception as error:  # noqa: BLE001 — recorded as a failure, not swallowed
        SmsCampaignRecipient.objects.filter(pk=claimed_id).update(
            state=SmsCampaignRecipient.State.FAILED, detail=str(error)[:255]
        )
        return False

    with transaction.atomic():
        message = OutboundSMS.objects.create(
            provider_code=result.provider_code,
            recipient_normalized=recipient.recipient_normalized,
            body_text=body,
            status=OutboundSMS.Status.SENT if result.success else OutboundSMS.Status.FAILED,
            status_detail=result.status_detail[:255],
            customer=recipient.customer,
            lead=recipient.lead,
            sent_by=campaign.created_by,
        )
        SmsCampaignRecipient.objects.filter(pk=claimed_id).update(
            state=(
                SmsCampaignRecipient.State.SENT
                if result.success
                else SmsCampaignRecipient.State.FAILED
            ),
            detail=result.status_detail[:255],
            message=message,
        )
        log_activity(
            actor=campaign.created_by,
            operation="outbound_sms.sent" if result.success else "outbound_sms.failed",
            instance=message,
            changes={"fields": ["recipient_normalized", "status"], "campaign": campaign.pk},
        )
    return result.success


def dispatch_due_sms_campaigns(*, limit=None):
    """Send up to `limit` pending recipients across every campaign now due.

    Returns `(sent, failed)`.

    Called from exactly two places, both bounded: the `send_scheduled_sms`
    management command (cron — the repository's established pattern for
    periodic work, the same one `session-cleanup` and `dispatch_outbound_
    events` already use) and a small flush when someone opens the SMS page, so
    a deployment whose operator has not wired cron yet still sends rather than
    queueing forever.

    Each recipient is claimed under `select_for_update(skip_locked=True)`
    before its provider call, so two dispatchers running at once — cron and a
    page request, say — cannot both send the same message.
    """
    budget = SMS_CAMPAIGN_DISPATCH_BATCH if limit is None else limit
    if budget <= 0 or not sms.provider_is_available():
        return (0, 0)

    sent = failed = 0
    due = SmsCampaign.objects.filter(
        status__in=[SmsCampaign.Status.SCHEDULED, SmsCampaign.Status.SENDING],
        scheduled_for__lte=timezone.now(),
    ).order_by("scheduled_for", "id")

    for campaign in due:
        while sent + failed < budget:
            with transaction.atomic():
                recipient = (
                    SmsCampaignRecipient.objects.select_for_update(skip_locked=True)
                    .filter(campaign=campaign, state=SmsCampaignRecipient.State.PENDING)
                    .order_by("id")
                    .first()
                )
                if recipient is None:
                    break
                # Marked inside the same transaction that found it, so a second
                # dispatcher's `skip_locked` passes over it instead of sending
                # the same message twice.
                recipient.detail = "در حال ارسال"
                recipient.save(update_fields=["detail", "updated_at"])
                if campaign.status != SmsCampaign.Status.SENDING:
                    campaign.status = SmsCampaign.Status.SENDING
                    campaign.started_at = campaign.started_at or timezone.now()
                    campaign.save(update_fields=["status", "started_at", "updated_at"])
                claimed_id = recipient.pk

            if _send_one_campaign_recipient(campaign, claimed_id):
                sent += 1
            else:
                failed += 1

        # Closed only once nothing pending is left, so a campaign larger than
        # one batch stays `sending` across passes rather than finishing early.
        still_pending = SmsCampaignRecipient.objects.filter(
            campaign=campaign, state=SmsCampaignRecipient.State.PENDING
        ).exists()
        if not still_pending:
            SmsCampaign.objects.filter(pk=campaign.pk).exclude(
                status=SmsCampaign.Status.CANCELLED
            ).update(status=SmsCampaign.Status.COMPLETED, finished_at=timezone.now())

        if sent + failed >= budget:
            break
    return (sent, failed)
