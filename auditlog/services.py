import re

from auditlog.models import ActivityLog
from common.request_context import clean_ip_address, clean_request_id, current_request_context


_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MONEY = re.compile(r"^\d{1,16}(?:\.\d{1,2})?$")
_ROLE_CODES = {"sales_agent", "sales_manager", "company_it", "platform_admin"}
_POSTAL_STATUS = re.compile(r"^\S(?:.{0,78}\S)?$")
_CASE_STATUS = re.compile(r"^\S(?:.{0,78}\S)?$")
_UNSET = object()

# Inventory and billing keys. Each is either a row id, a whole quantity, a
# money string, or a value drawn from a fixed backend-owned vocabulary — never
# operator free text, which is what keeps the audit payload safe to read at a
# lower privilege than the row it describes.
_ID_KEYS = ("warehouse", "product", "customer", "invoice", "order", "quotation", "payment", "plan")
_QUANTITY_KEYS = ("quantity", "resulting_quantity", "item_count", "installment_count")
_MONEY_KEYS = ("total_amount", "amount", "allocated_amount")
# A ledger balance is legitimately negative when the customer is in credit, so
# it needs the signed form rather than the unsigned `_MONEY` used for amounts.
_SIGNED_MONEY = re.compile(r"^-?\d{1,16}(?:\.\d{1,2})?$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_CODE_KEYS = ("movement_type", "entry_type", "method", "status_from", "status_to", "number_kind")
_DOCUMENT_NUMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/._-]{0,63}$")


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
    for key in ("postal_from", "postal_to"):
        value = changes.get(key)
        if isinstance(value, str) and (value == "" or _POSTAL_STATUS.fullmatch(value)):
            cleaned[key] = value
    for key in ("case_from", "case_to"):
        value = changes.get(key)
        if isinstance(value, str) and (value == "" or _CASE_STATUS.fullmatch(value)):
            cleaned[key] = value
    for key in _ID_KEYS:
        value = changes.get(key)
        if key in changes and (value is None or (isinstance(value, int) and not isinstance(value, bool))):
            cleaned[key] = value
    for key in _QUANTITY_KEYS:
        value = changes.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) <= 10**12:
            cleaned[key] = value
    for key in _CODE_KEYS:
        value = changes.get(key)
        if isinstance(value, str) and _CODE.fullmatch(value):
            cleaned[key] = value
    number = changes.get("number")
    if isinstance(number, str) and _DOCUMENT_NUMBER.fullmatch(number):
        cleaned["number"] = number
    for key in _MONEY_KEYS:
        value = changes.get(key)
        if value is not None and _MONEY.fullmatch(str(value)):
            cleaned[key] = str(value)
    balance_after = changes.get("balance_after")
    if balance_after is not None and _SIGNED_MONEY.fullmatch(str(balance_after)):
        cleaned["balance_after"] = str(balance_after)
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
