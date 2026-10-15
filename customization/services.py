"""Custom fields: their definitions and the values records carry (2.40.53).

Three controls, as everywhere:

* **feature availability** — `customization` (off by default): without it no
  field is shown, offered, exported, filtered or accepted, and every stored
  value stays where it is;
* **role permission** — `customization.manage` (Platform Admin by default, one
  row in the permission matrix) defines the fields; entering a value is part
  of editing the record, under that record's own permission;
* **object scope** — the record's own: a value is read and written through the
  record, never on its own.

Values are text on the record (`<entity>.custom_fields`, `{key: text}`): a
number as its decimal digits, a date as `YYYY-MM-DD`, a yes/no as `true` or
`false`, a choice as the choice itself. One form for every type keeps search,
filtering and the spreadsheet the same for all of them.
"""

import datetime
import unicodedata
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from accounts.access import has_any_capability
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from customization.models import (
    CHOICE_MAX_LENGTH,
    LABEL_MAX_LENGTH,
    MAX_CHOICES,
    MAX_FIELDS_PER_ENTITY,
    CustomFieldDefinition,
)

FEATURE = "customization"
CAPABILITY = "customization.manage"
TEXT_MAX = 500
LONG_TEXT_MAX = 4000
FLAGS = ("required", "show_in_list", "filterable", "searchable")
Type = CustomFieldDefinition.FieldType


def enabled():
    return feature_enabled(FEATURE)


def can_manage(user):
    return enabled() and has_any_capability(user, CAPABILITY)


def definitions_for(entity, *, active_only=True):
    """The entity's fields in their order; none without the feature."""
    if not enabled():
        return []
    queryset = CustomFieldDefinition.objects.filter(entity=entity)
    if active_only:
        queryset = queryset.filter(is_active=True)
    return list(queryset.order_by("position", "id"))


def serialize_definition(definition):
    return {
        "id": definition.pk, "entity": definition.entity, "key": definition.key, "label": definition.label,
        "field_type": definition.field_type, "field_type_display": definition.get_field_type_display(),
        "choices": list(definition.choices or []), "required": definition.required,
        "show_in_list": definition.show_in_list, "filterable": definition.filterable,
        "searchable": definition.searchable, "position": definition.position, "is_active": definition.is_active,
    }


def page_definitions(entity):
    """What a page embeds for its forms, list and filters (`json_script`)."""
    return [serialize_definition(definition) for definition in definitions_for(entity)]


# --- one value -------------------------------------------------------------------

def _text(value):
    return unicodedata.normalize("NFKC", str(value if value is not None else "")).strip()


def clean_value(definition, value):
    """The stored text for `value`, or `""` for none; `BusinessRuleError` when
    it does not fit the field's type."""
    text = _text(value)
    if isinstance(value, bool):
        text = "true" if value else "false"
    if text == "":
        return ""
    label = definition.label
    kind = definition.field_type
    if kind == Type.TEXT:
        if len(text) > TEXT_MAX:
            raise BusinessRuleError({"custom_fields": f"«{label}» نباید بیش از {TEXT_MAX} نویسه باشد."})
        return " ".join(text.split())
    if kind == Type.LONG_TEXT:
        if len(text) > LONG_TEXT_MAX:
            raise BusinessRuleError({"custom_fields": f"«{label}» نباید بیش از {LONG_TEXT_MAX} نویسه باشد."})
        return text
    if kind == Type.NUMBER:
        digits = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")).replace(",", "")
        try:
            number = Decimal(digits)
        except InvalidOperation:
            raise BusinessRuleError({"custom_fields": f"«{label}» باید عدد باشد."}) from None
        if not number.is_finite() or abs(number) >= Decimal("1e18"):
            raise BusinessRuleError({"custom_fields": f"«{label}» باید عدد باشد."})
        normalized = format(number.normalize(), "f")
        return normalized[:-2] if normalized.endswith(".0") else normalized
    if kind == Type.DATE:
        try:
            return datetime.date.fromisoformat(text).isoformat()
        except ValueError:
            raise BusinessRuleError({"custom_fields": f"«{label}» تاریخ درستی نیست."}) from None
    if kind == Type.CHOICE:
        if text not in (definition.choices or []):
            raise BusinessRuleError({"custom_fields": f"«{label}» را از فهرست انتخاب کنید."})
        return text
    if kind == Type.BOOLEAN:
        lowered = text.casefold()
        if lowered in ("true", "1", "yes", "بله", "آری"):
            return "true"
        if lowered in ("false", "0", "no", "خیر"):
            return "false"
        raise BusinessRuleError({"custom_fields": f"«{label}» باید بله یا خیر باشد."})
    raise BusinessRuleError({"custom_fields": f"«{label}» شناخته‌شده نیست."})


def clean_values(entity, incoming, *, existing=None, enforce_required=False):
    """Merge `incoming` (`{key: value}`) into `existing` and return the result.

    A key the entity has no active field for is refused, and so is anything at
    all without the feature. A value set to empty is removed. A field of a
    deactivated definition keeps whatever it held. With `enforce_required`, an
    active required field must end up with a value — what a person's own form
    or spreadsheet is held to, not an integration creating a record.
    """
    result = dict(existing or {})
    if incoming in (None, {}):
        incoming = {}
    if not isinstance(incoming, dict):
        raise BusinessRuleError({"custom_fields": "فیلدهای سفارشی باید به شکل نام و مقدار باشند."})
    if incoming and not enabled():
        raise BusinessRuleError({"custom_fields": "شخصی‌سازی در این استقرار فعال نیست."})
    definitions = {definition.key: definition for definition in definitions_for(entity)}
    for key, value in incoming.items():
        definition = definitions.get(key)
        if definition is None:
            raise BusinessRuleError({"custom_fields": "این فیلد سفارشی وجود ندارد یا غیرفعال است."})
        cleaned = clean_value(definition, value)
        if cleaned:
            result[key] = cleaned
        else:
            result.pop(key, None)
    if enforce_required:
        missing = [definition.label for definition in definitions.values() if definition.required and not result.get(definition.key)]
        if missing:
            raise BusinessRuleError({"custom_fields": "این فیلدها را پر کنید: " + "، ".join(f"«{label}»" for label in missing)})
    return result


def display_value(definition, value):
    """A stored value as a reader sees it in a spreadsheet: a date stays ISO
    there and in the panel's own script it becomes Jalali."""
    if value in (None, ""):
        return ""
    if definition.field_type == Type.BOOLEAN:
        return "بله" if value == "true" else "خیر"
    if definition.field_type == Type.DATE:
        from common.jalali import format_date

        return format_date(datetime.date.fromisoformat(value), persian_digits=False)
    return value


# --- definitions -------------------------------------------------------------------

def _clean_label(value):
    label = " ".join(_text(value).split())
    if not label:
        raise BusinessRuleError({"label": "نام فیلد را بنویسید."})
    if len(label) > LABEL_MAX_LENGTH:
        raise BusinessRuleError({"label": f"نام فیلد نباید بیش از {LABEL_MAX_LENGTH} نویسه باشد."})
    return label


def _clean_choices(value, field_type):
    if field_type != Type.CHOICE:
        return []
    if isinstance(value, str):
        value = value.splitlines()
    if not isinstance(value, (list, tuple)):
        raise BusinessRuleError({"choices": "گزینه‌ها را هر کدام در یک سطر بنویسید."})
    choices = []
    for item in value:
        text = " ".join(_text(item).split())
        if not text or text in choices:
            continue
        if len(text) > CHOICE_MAX_LENGTH:
            raise BusinessRuleError({"choices": f"هر گزینه حداکثر {CHOICE_MAX_LENGTH} نویسه است."})
        choices.append(text)
    if not choices:
        raise BusinessRuleError({"choices": "دست‌کم یک گزینه بنویسید."})
    if len(choices) > MAX_CHOICES:
        raise BusinessRuleError({"choices": f"حداکثر {MAX_CHOICES} گزینه."})
    return choices


def _require_manager(actor):
    if not can_manage(actor):
        raise BusinessPermissionDenied("مدیریت فیلدهای سفارشی مجاز نیست.")


def _clean_label_unique(entity, label, *, exclude=None):
    others = CustomFieldDefinition.objects.filter(entity=entity, label=label)
    if exclude is not None:
        others = others.exclude(pk=exclude)
    if others.exists():
        raise BusinessRuleError({"label": "فیلدی با همین نام برای این بخش هست."})


@transaction.atomic
def create_definition(*, actor, entity, label, field_type, choices=None, **flags):
    _require_manager(actor)
    if entity not in CustomFieldDefinition.Entity.values:
        raise BusinessRuleError({"entity": "این بخش فیلد سفارشی نمی‌پذیرد."})
    if field_type not in Type.values:
        raise BusinessRuleError({"field_type": "نوع فیلد را از فهرست انتخاب کنید."})
    existing = CustomFieldDefinition.objects.select_for_update().filter(entity=entity)
    if existing.count() >= MAX_FIELDS_PER_ENTITY:
        raise BusinessRuleError({"label": f"هر بخش حداکثر {MAX_FIELDS_PER_ENTITY} فیلد سفارشی دارد."})
    label = _clean_label(label)
    _clean_label_unique(entity, label)
    numbers = [int(key[3:]) for key in existing.values_list("key", flat=True)]
    definition = CustomFieldDefinition.objects.create(
        entity=entity, key=f"cf_{max(numbers, default=0) + 1}", label=label, field_type=field_type,
        choices=_clean_choices(choices or [], field_type),
        position=(existing.aggregate(top=Max("position"))["top"] or 0) + 1,
        created_by=actor,
        **{flag: bool(flags.get(flag, False)) for flag in FLAGS},
    )
    log_activity(actor=actor, operation="custom_field.created", instance=definition, changes={"fields": ["label", "field_type", *FLAGS]})
    return definition


@transaction.atomic
def update_definition(*, actor, definition, **changes):
    """Label, choices, the four flags, and active. The type is fixed once a
    field exists: a stored value of one type is not a value of another."""
    _require_manager(actor)
    locked = CustomFieldDefinition.objects.select_for_update().get(pk=definition.pk)
    changed = []
    if "label" in changes:
        label = _clean_label(changes["label"])
        _clean_label_unique(locked.entity, label, exclude=locked.pk)
        if label != locked.label:
            locked.label = label
            changed.append("label")
    if "choices" in changes and locked.field_type == Type.CHOICE:
        choices = _clean_choices(changes["choices"], locked.field_type)
        if choices != locked.choices:
            locked.choices = choices
            changed.append("choices")
    for flag in (*FLAGS, "is_active"):
        if flag in changes and bool(changes[flag]) != getattr(locked, flag):
            setattr(locked, flag, bool(changes[flag]))
            changed.append(flag)
    if changed:
        locked.save(update_fields=[*changed, "updated_at"])
        log_activity(actor=actor, operation="custom_field.updated", instance=locked, changes={"fields": changed})
    return locked


@transaction.atomic
def move_definition(*, actor, definition, direction):
    """One place up or down among its entity's fields."""
    _require_manager(actor)
    if direction not in ("up", "down"):
        raise BusinessRuleError({"direction": "جهت باید بالا یا پایین باشد."})
    ordered = list(
        CustomFieldDefinition.objects.select_for_update().filter(entity=definition.entity).order_by("position", "id")
    )
    index = next(i for i, item in enumerate(ordered) if item.pk == definition.pk)
    other = index - 1 if direction == "up" else index + 1
    if 0 <= other < len(ordered):
        ordered[index], ordered[other] = ordered[other], ordered[index]
    for position, item in enumerate(ordered, start=1):
        if item.position != position:
            item.position = position
            item.save(update_fields=["position", "updated_at"])
    return ordered
