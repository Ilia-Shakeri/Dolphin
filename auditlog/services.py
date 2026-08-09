import re

from auditlog.models import ActivityLog
from common.request_context import clean_ip_address, clean_request_id, current_request_context


_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MONEY = re.compile(r"^\d{1,16}(?:\.\d{1,2})?$")
_ROLE_CODES = {"sales_agent", "sales_manager", "company_it", "platform_admin"}
_UNSET = object()


def _clean_changes(changes):
    cleaned = {}
    fields = changes.get("fields")
    if isinstance(fields, (list, tuple)):
        cleaned_fields = [field for field in fields if isinstance(field, str) and _FIELD_NAME.fullmatch(field)]
        if cleaned_fields:
            cleaned["fields"] = cleaned_fields
    for key in ("password_set", "password_changed", "reason_provided"):
        if isinstance(changes.get(key), bool):
            cleaned[key] = changes[key]
    for key in ("from_user", "to_user", "lead"):
        value = changes.get(key)
        if value is None or (isinstance(value, int) and not isinstance(value, bool)):
            if key in changes:
                cleaned[key] = value
    for key in ("from", "to"):
        value = changes.get(key)
        if value in _ROLE_CODES:
            cleaned[key] = value
    total_amount = changes.get("total_amount")
    if total_amount is not None and _MONEY.fullmatch(str(total_amount)):
        cleaned["total_amount"] = str(total_amount)
    return cleaned


def _clean_role_snapshot(value):
    return value if value in _ROLE_CODES else ""


def log_activity(
    *,
    actor,
    operation,
    instance,
    changes=None,
    request_id=_UNSET,
    ip_address=_UNSET,
    actor_role_snapshot=_UNSET,
    object_role_snapshot=_UNSET,
):
    context = current_request_context()
    if request_id is _UNSET:
        request_id = context.request_id
    if ip_address is _UNSET:
        ip_address = context.ip_address
    if actor_role_snapshot is _UNSET:
        actor_role_snapshot = getattr(actor, "role", "") if actor is not None else ""
    if object_role_snapshot is _UNSET:
        object_role_snapshot = getattr(instance, "role", "") if instance._meta.label_lower == "accounts.user" else ""
    return ActivityLog.objects.create(
        actor=actor,
        actor_role_snapshot=_clean_role_snapshot(actor_role_snapshot),
        operation=operation,
        object_type=instance._meta.label_lower,
        object_id=str(instance.pk),
        object_role_snapshot=_clean_role_snapshot(object_role_snapshot),
        safe_changes=_clean_changes(changes or {}),
        request_id=clean_request_id(request_id),
        ip_address=clean_ip_address(ip_address),
    )
