import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from django.db import IntegrityError, transaction
from django.utils import timezone

from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessRuleError
from communications.models import InboundSMS
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
