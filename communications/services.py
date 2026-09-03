import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
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
from communications.models import InboundSMS, OutboundSMS
from sales.models import CustomerPhone


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
