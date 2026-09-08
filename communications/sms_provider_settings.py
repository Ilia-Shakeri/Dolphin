"""The SMS provider settings singleton: read/update, and a connectivity test.

Same shape as `common/branding.py`'s `get_brand_settings`/
`update_brand_settings` — one row, created empty on first read, never
raising. `communications/sms.py` is the only other reader that matters at
send time; this module is what the settings page itself calls.
"""

import json
import unicodedata

from django.db import transaction

from auditlog.services import log_activity
from common.exceptions import BusinessRuleError
from communications.models import SmsProviderSettings

LABEL_MAX_LENGTH = 120
URL_MAX_LENGTH = 500
TEXT_MAX_LENGTH = 255

#: Every field `update_sms_provider_settings` may touch — kept as one tuple
#: so the "independent and optional" contract (any subset may be sent) and
#: the audit log's field-name list are read off the same source, rather than
#: two lists that could drift apart.
UPDATABLE_FIELDS = (
    "is_enabled", "label", "auth_mode", "recipient_number_style", "send_url",
    "body_template", "headers", "sender_id", "timeout_seconds",
    "token_url", "token_username", "token_password", "token_extra_params",
    "test_url",
)


def get_sms_provider_settings():
    row, _ = SmsProviderSettings.objects.get_or_create(singleton=SmsProviderSettings.SINGLETON)
    return row


def _clean_text(value, *, field, limit, required=False):
    cleaned = unicodedata.normalize("NFKC", str(value or "")).strip()
    if required and not cleaned:
        raise BusinessRuleError({field: "این فیلد الزامی است."})
    if len(cleaned) > limit:
        raise BusinessRuleError({field: f"حداکثر {limit} نویسه مجاز است."})
    return cleaned


def _clean_json_object(value, *, field):
    """A blank value is allowed everywhere this is used (no extra headers/
    params is a normal, valid configuration) — only a *non-blank* value that
    fails to parse as a JSON object is rejected.
    """
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    try:
        parsed = json.loads(cleaned)
    except ValueError as error:
        raise BusinessRuleError({field: "این فیلد باید یک شیء JSON معتبر باشد."}) from error
    if not isinstance(parsed, (dict, list)):
        raise BusinessRuleError({field: "این فیلد باید یک شیء یا آرایهٔ JSON باشد."})
    return cleaned


@transaction.atomic
def update_sms_provider_settings(*, actor, **changes):
    """Apply any subset of `UPDATABLE_FIELDS`; every field independent.

    Mirrors `common.branding.update_brand_settings`'s own contract: sending
    only `is_enabled` toggles the switch without touching anything else
    already configured.
    """
    unknown = set(changes) - set(UPDATABLE_FIELDS)
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})

    row = SmsProviderSettings.objects.select_for_update().get_or_create(
        singleton=SmsProviderSettings.SINGLETON
    )[0]

    if "label" in changes:
        row.label = _clean_text(changes["label"], field="label", limit=LABEL_MAX_LENGTH)
    if "auth_mode" in changes:
        value = str(changes["auth_mode"] or "").strip()
        if value not in SmsProviderSettings.AuthMode.values:
            raise BusinessRuleError({"auth_mode": "روش احراز هویت نامعتبر است."})
        row.auth_mode = value
    if "recipient_number_style" in changes:
        value = str(changes["recipient_number_style"] or "").strip()
        if value not in SmsProviderSettings.NumberStyle.values:
            raise BusinessRuleError({"recipient_number_style": "قالب شمارهٔ گیرنده نامعتبر است."})
        row.recipient_number_style = value
    if "send_url" in changes:
        row.send_url = _clean_text(changes["send_url"], field="send_url", limit=URL_MAX_LENGTH)
    if "body_template" in changes:
        row.body_template = _clean_json_object(changes["body_template"], field="body_template")
    if "headers" in changes:
        row.headers = _clean_json_object(changes["headers"], field="headers")
    if "sender_id" in changes:
        row.sender_id = _clean_text(changes["sender_id"], field="sender_id", limit=32)
    if "timeout_seconds" in changes:
        try:
            seconds = int(changes["timeout_seconds"])
        except (TypeError, ValueError) as error:
            raise BusinessRuleError({"timeout_seconds": "زمان انتظار باید عدد صحیح باشد."}) from error
        if not (1 <= seconds <= 120):
            raise BusinessRuleError({"timeout_seconds": "زمان انتظار باید بین ۱ تا ۱۲۰ ثانیه باشد."})
        row.timeout_seconds = seconds
    if "token_url" in changes:
        row.token_url = _clean_text(changes["token_url"], field="token_url", limit=URL_MAX_LENGTH)
    if "token_username" in changes:
        row.token_username = _clean_text(changes["token_username"], field="token_username", limit=TEXT_MAX_LENGTH)
    if "token_password" in changes:
        row.token_password = _clean_text(changes["token_password"], field="token_password", limit=TEXT_MAX_LENGTH)
    if "token_extra_params" in changes:
        row.token_extra_params = _clean_json_object(changes["token_extra_params"], field="token_extra_params")
    if "test_url" in changes:
        row.test_url = _clean_text(changes["test_url"], field="test_url", limit=URL_MAX_LENGTH)
    if "is_enabled" in changes:
        row.is_enabled = bool(changes["is_enabled"])

    if row.auth_mode == SmsProviderSettings.AuthMode.OAUTH2_PASSWORD and row.is_enabled and not row.token_url:
        raise BusinessRuleError({"token_url": "برای روش OAuth2 نشانی دریافت توکن الزامی است."})
    if row.is_enabled and not row.send_url:
        raise BusinessRuleError({"send_url": "برای فعال‌سازی، نشانی ارسال الزامی است."})

    row.updated_by = actor
    row.save()
    log_activity(
        actor=actor,
        operation="sms_provider_settings.updated",
        instance=row,
        changes={"fields": sorted(set(changes) & set(UPDATABLE_FIELDS))},
    )
    return row
