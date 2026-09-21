"""The post-carrier API connection: read/update the settings row, and a
real "تست اتصال" against whatever URL an operator entered.

Product-owner request 2026-09-21: «تنظیمات سامانه پست هم مثل پیامک باید
صفحه برای تنظیم کردن api داشته باشه». Deliberately the same shape as
`communications/sms_provider_settings.py` and `communications/sms.py`
together — one settings row, one update service, one connectivity test —
simplified to the one auth shape (`PostProviderSettings.api_key_header`) a
tracking/status API actually needs, not the SMS module's oauth2 flow, which
exists there because one real gateway needed it and none is being
integrated here.

**This module does not touch `sales/postal.py`'s carrier seam.** `carrier_for`
still returns `ManualCarrier` regardless of what is saved here — nothing
maps a specific provider's status vocabulary onto the four postal states,
because no specific provider is integrated (CLAUDE.md §30). What exists here
is real, saved, testable connection settings a future `PostalCarrier`
subclass can be built against with no settings-page change, exactly what
`sales/postal.py`'s own docstring says a future provider adds.
"""

import unicodedata
import urllib.request
from dataclasses import dataclass

from django.db import transaction

from auditlog.services import log_activity
from common.exceptions import BusinessRuleError
from common.http_probe import MAX_RESPONSE_DETAIL, run_http_probe

LABEL_MAX_LENGTH = 120
URL_MAX_LENGTH = 500
HEADER_NAME_MAX_LENGTH = 80
KEY_MAX_LENGTH = 255
ACCOUNT_CODE_MAX_LENGTH = 120

#: Every field `update_post_provider_settings` may touch — "independent and
#: optional" contract, same as `communications.sms_provider_settings.
#: UPDATABLE_FIELDS`: any subset may be sent, and each changes only itself.
UPDATABLE_FIELDS = (
    "is_enabled", "label", "base_url", "api_key_header", "api_key",
    "sender_account_code", "timeout_seconds", "test_url",
)


@dataclass(frozen=True)
class PostProviderTestResult:
    success: bool
    #: Short, safe-to-store diagnostic text — an HTTP status and a truncated
    #: response body, or a connection-error class name. Never a header, a
    #: key, or anything else this row holds.
    status_detail: str


def get_post_provider_settings():
    from sales.models import PostProviderSettings

    row, _ = PostProviderSettings.objects.get_or_create(singleton=PostProviderSettings.SINGLETON)
    return row


def _clean_text(value, *, field, limit, required=False):
    cleaned = unicodedata.normalize("NFKC", str(value or "")).strip()
    if required and not cleaned:
        raise BusinessRuleError({field: "این فیلد الزامی است."})
    if len(cleaned) > limit:
        raise BusinessRuleError({field: f"حداکثر {limit} نویسه مجاز است."})
    return cleaned


@transaction.atomic
def update_post_provider_settings(*, actor, **changes):
    """Apply any subset of `UPDATABLE_FIELDS`; every field independent —
    mirrors `communications.sms_provider_settings.update_sms_provider_
    settings`'s own contract exactly.
    """
    from sales.models import PostProviderSettings

    unknown = set(changes) - set(UPDATABLE_FIELDS)
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})

    row = PostProviderSettings.objects.select_for_update().get_or_create(
        singleton=PostProviderSettings.SINGLETON
    )[0]

    if "label" in changes:
        row.label = _clean_text(changes["label"], field="label", limit=LABEL_MAX_LENGTH)
    if "base_url" in changes:
        row.base_url = _clean_text(changes["base_url"], field="base_url", limit=URL_MAX_LENGTH)
    if "api_key_header" in changes:
        row.api_key_header = _clean_text(
            changes["api_key_header"], field="api_key_header", limit=HEADER_NAME_MAX_LENGTH
        )
    if "api_key" in changes:
        row.api_key = _clean_text(changes["api_key"], field="api_key", limit=KEY_MAX_LENGTH)
    if "sender_account_code" in changes:
        row.sender_account_code = _clean_text(
            changes["sender_account_code"], field="sender_account_code", limit=ACCOUNT_CODE_MAX_LENGTH
        )
    if "timeout_seconds" in changes:
        try:
            seconds = int(changes["timeout_seconds"])
        except (TypeError, ValueError) as error:
            raise BusinessRuleError({"timeout_seconds": "زمان انتظار باید عدد صحیح باشد."}) from error
        if not (1 <= seconds <= 120):
            raise BusinessRuleError({"timeout_seconds": "زمان انتظار باید بین ۱ تا ۱۲۰ ثانیه باشد."})
        row.timeout_seconds = seconds
    if "test_url" in changes:
        row.test_url = _clean_text(changes["test_url"], field="test_url", limit=URL_MAX_LENGTH)
    if "is_enabled" in changes:
        row.is_enabled = bool(changes["is_enabled"])

    if row.is_enabled and not row.base_url:
        raise BusinessRuleError({"base_url": "برای فعال‌سازی، نشانی سرویس الزامی است."})

    row.updated_by = actor
    row.save()
    log_activity(
        actor=actor,
        operation="post_provider_settings.updated",
        instance=row,
        changes={"fields": sorted(set(changes) & set(UPDATABLE_FIELDS))},
    )
    return row


def test_connectivity(row):
    """Calls `row`'s optional `test_url` (a GET) with the configured header
    key, for the settings page's own "تست اتصال" button.

    Takes the row directly rather than requiring `is_enabled` — an operator
    testing credentials before switching the connection on is the normal
    order of operations, the same choice `communications.sms.test_
    connectivity` makes for `config_from_row` over `resolve_config`.
    """
    test_url = (row.test_url or "").strip()
    if not test_url:
        return PostProviderTestResult(success=False, status_detail="نشانی آزمایشی تنظیم نشده است.")

    headers = {}
    if row.api_key and row.api_key_header:
        headers[row.api_key_header] = row.api_key

    request = urllib.request.Request(test_url, headers=headers, method="GET")
    status, response_text, error_detail = run_http_probe(request, timeout=row.timeout_seconds)
    if error_detail is not None:
        return PostProviderTestResult(success=False, status_detail=error_detail)
    success = 200 <= status <= 299
    detail = f"HTTP {status}: {response_text[:MAX_RESPONSE_DETAIL]}".strip()
    return PostProviderTestResult(success=success, status_detail=detail)
