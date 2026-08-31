import re
import unicodedata
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.access import has_any_capability, is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from common.phones import normalize_customer_phone
from sales.models import (
    CUSTOMER_ADDRESS_MAX_LENGTH,
    CUSTOMER_CATEGORY_MAX_LENGTH,
    CUSTOMER_POSTAL_CODE_MAX_LENGTH,
    FREE_TEXT_MAX_LENGTH,
    INTERACTION_OUTCOME_MAX_LENGTH,
    Customer,
    CustomerPhone,
    Interaction,
    Lead,
    LeadAssignmentHistory,
    Product,
    ProductCategory,
    Sale,
    SalesDocument,
    PostalStatusHistory,
    TargetAudienceMember,
)
from sales.selectors import customers_for, leads_for, sales_for, target_audience_for


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
VALID_ROLES = {value for value, _ in User.Role.choices}
OPERATIONAL_WRITERS = {User.Role.SALES_AGENT, *ELEVATED_OPERATORS}
MAX_MONEY = Decimal("9999999999999999.99")
CUSTOMER_MUTABLE_FIELDS = {
    "full_name",
    "kind",
    "economic_code",
    "national_id",
    "email",
    "province",
    "city",
    "postal_code",
    "category",
    "address",
    "notes",
}
# `status` is set by the person working the campaign, not by the server: it
# records their judgement of where the campaign stands. The three permitted
# values are fixed by Lead.Status and checked by _validate_lead_status.
LEAD_MUTABLE_FIELDS = {"source", "campaign_or_batch", "interested_product", "next_follow_up_at", "notes", "status"}
PHONE_MUTABLE_FIELDS = {"raw_phone", "label", "is_primary", "is_active"}
PRODUCT_MUTABLE_FIELDS = {"sku", "name", "category", "brand", "barcode", "unit", "current_price", "description"}
PRODUCT_CATEGORY_CREATE_FIELDS = {"code", "name", "description", "display_order"}
PRODUCT_CATEGORY_UPDATE_FIELDS = {"name", "description", "display_order"}
INTERACTION_CREATE_FIELDS = {"phone", "direction", "outcome", "occurred_at", "next_follow_up_at", "notes"}
SALE_CREATE_FIELDS = {"sold_at", "notes"}
CUSTOMER_TEXT_LIMITS = {
    "postal_code": CUSTOMER_POSTAL_CODE_MAX_LENGTH,
    "category": CUSTOMER_CATEGORY_MAX_LENGTH,
    "address": CUSTOMER_ADDRESS_MAX_LENGTH,
    "notes": FREE_TEXT_MAX_LENGTH,
}
LEAD_TEXT_LIMITS = {"notes": FREE_TEXT_MAX_LENGTH}
CUSTOMER_TEXT_LIMITS["economic_code"] = 32

PRODUCT_TEXT_LIMITS = {
    "brand": 120,
    "barcode": 64,
    "description": FREE_TEXT_MAX_LENGTH,
}
PRODUCT_CATEGORY_TEXT_LIMITS = {"description": 2000}
INTERACTION_TEXT_LIMITS = {"notes": FREE_TEXT_MAX_LENGTH}
SALE_TEXT_LIMITS = {"notes": FREE_TEXT_MAX_LENGTH}
SALES_DOCUMENT_TEXT_LIMITS = {
    "document_number": 64,
    "postal_status": 80,
    "notes": FREE_TEXT_MAX_LENGTH,
}


def _validate_lead_status(data):
    """Refuse a status outside the three states a campaign is tracked in."""
    if "status" in data and data["status"] not in Lead.Status.values:
        raise BusinessRuleError({"status": "یکی از سه وضعیت کمپین را انتخاب کنید."})


def _validate_text_lengths(values, limits):
    errors = {
        field: f"این فیلد نباید بیش از {limit} نویسه داشته باشد."
        for field, limit in limits.items()
        if field in values and isinstance(values[field], str) and len(values[field]) > limit
    }
    if errors:
        raise BusinessRuleError(errors)


def _validate_interaction_data(data):
    errors = {}
    if data.get("direction") not in Interaction.Direction.values:
        errors["direction"] = "جهت باید ورودی یا خروجی باشد."
    outcome = data.get("outcome")
    if not isinstance(outcome, str) or not outcome.strip():
        errors["outcome"] = "نتیجه تماس الزامی است."
    elif len(outcome.strip()) > INTERACTION_OUTCOME_MAX_LENGTH:
        errors["outcome"] = (
            f"این فیلد نباید بیش از {INTERACTION_OUTCOME_MAX_LENGTH} نویسه داشته باشد."
        )
    if errors:
        raise BusinessRuleError(errors)
    data["outcome"] = outcome.strip()


def _lock_active_actor(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked) or locked.role not in VALID_ROLES:
        raise BusinessPermissionDenied("کاربر باید فعال باشد.")
    return locked


def _lock_operational_actor(actor):
    locked = _lock_active_actor(actor)
    if locked.role not in OPERATIONAL_WRITERS:
        raise BusinessPermissionDenied("انجام این تغییر عملیاتی مجاز نیست.")
    return locked


_CATEGORY_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", flags=re.ASCII)
_PRODUCT_BARCODE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$", flags=re.ASCII)
_PERSIAN_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})


def _clean_category_name(value):
    name = " ".join(unicodedata.normalize("NFKC", str(value)).translate(_PERSIAN_LETTERS).split())
    if not name:
        raise BusinessRuleError({"name": "نام دسته‌بندی الزامی است."})
    if len(name) > 120:
        raise BusinessRuleError({"name": "این فیلد نباید بیش از ۱۲۰ نویسه داشته باشد."})
    return name, name.casefold()


def _clean_category_code(value):
    code = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if not _CATEGORY_CODE.fullmatch(code):
        raise BusinessRuleError({"code": "فقط از حروف انگلیسی کوچک، عدد، خط زیر یا خط تیره استفاده کنید."})
    return code


def _clean_product_barcode(value):
    barcode = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    if barcode and not _PRODUCT_BARCODE.fullmatch(barcode):
        raise BusinessRuleError({"barcode": "فقط از حروف انگلیسی، عدد، نقطه، خط زیر یا خط تیره استفاده کنید."})
    return barcode


def _clean_single_line(value, *, field, limit):
    cleaned = " ".join(unicodedata.normalize("NFKC", str(value or "")).split())
    if len(cleaned) > limit:
        raise BusinessRuleError({field: f"این فیلد نباید بیش از {limit} نویسه داشته باشد."})
    return cleaned


def _validate_customer_kind(actor, data):
    """A customer's kind must be real, and must be one this actor may work.

    A marketer's scope is the individual book (`customers_for`). Without this
    check the API would let one create a legal customer and then be unable to
    read back the record they had just written — the write would succeed and the
    customer would be invisible to its own author. Refusing the write is the
    honest answer.
    """
    if "kind" not in data:
        return
    kind = (data["kind"] or "").strip()
    if kind not in Customer.Kind.values:
        raise BusinessRuleError({"kind": "نوع مشتری را از فهرست انتخاب کنید."})
    if actor.role == User.Role.SALES_AGENT and kind != Customer.Kind.INDIVIDUAL:
        raise BusinessPermissionDenied("مشتریان حقوقی خارج از دسترسی شماست.")
    data["kind"] = kind


@transaction.atomic
def create_customer_with_phone(*, actor, phone=None, **data):
    actor = _lock_operational_actor(actor)
    unknown = set(data) - CUSTOMER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    _validate_text_lengths(data, CUSTOMER_TEXT_LIMITS)
    _validate_customer_kind(actor, data)
    customer = Customer.objects.create(created_by=actor, **data)
    log_activity(
        actor=actor,
        operation="customer.created",
        instance=customer,
        changes={"fields": sorted(data)},
    )
    if phone:
        create_customer_phone(actor=actor, customer=customer, **phone)
    return customer


@transaction.atomic
def update_customer(*, actor, customer, **changes):
    actor = _lock_operational_actor(actor)
    locked = Customer.objects.select_for_update().get(pk=customer.pk)
    if not customers_for(actor).filter(pk=locked.pk).exists():
        raise BusinessPermissionDenied("این مشتری خارج از دسترسی شماست.")
    unknown = set(changes) - CUSTOMER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    _validate_text_lengths(changes, CUSTOMER_TEXT_LIMITS)
    _validate_customer_kind(actor, changes)
    changed_fields = []
    for field, value in changes.items():
        if getattr(locked, field) != value:
            setattr(locked, field, value)
            changed_fields.append(field)
    if changed_fields:
        locked.save(update_fields=[*changed_fields, "updated_at"])
        log_activity(
            actor=actor,
            operation="customer.updated",
            instance=locked,
            changes={"fields": sorted(changed_fields)},
        )
    return locked


@transaction.atomic
def create_customer_phone(*, actor, customer, raw_phone, label="", is_primary=False, is_active=True):
    actor = _lock_operational_actor(actor)
    if not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("این مشتری خارج از دسترسی شماست.")
    normalized = normalize_customer_phone(raw_phone)
    try:
        created = CustomerPhone.objects.create(
            customer=customer,
            raw_phone=raw_phone,
            normalized_phone=normalized,
            label=label,
            is_primary=is_primary,
            is_active=is_active,
        )
    except IntegrityError as exc:
        raise BusinessConflictError({"raw_phone": "محدودیت شماره فعال یا شماره اصلی نقض شده است."}) from exc
    # A customer's reachable number is the field most worth tampering with, so
    # every change to one is recorded. The number itself stays out of the audit
    # payload, which carries field names rather than customer data.
    log_activity(
        actor=actor,
        operation="customer_phone.created",
        instance=created,
        changes={"customer": customer.pk},
    )
    # This number may sit in one or more campaign audiences; being a customer
    # now is the further state, so those entries follow.
    refresh_target_members_for_phone(normalized_phone=normalized, actor=actor)
    return created


@transaction.atomic
def update_customer_phone(*, actor, phone, **changes):
    actor = _lock_operational_actor(actor)
    locked = CustomerPhone.objects.select_for_update().select_related("customer").get(pk=phone.pk)
    if not customers_for(actor).filter(pk=locked.customer_id).exists():
        raise BusinessPermissionDenied("این مشتری خارج از دسترسی شماست.")
    unknown = set(changes) - PHONE_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    if "raw_phone" in changes:
        changes["normalized_phone"] = normalize_customer_phone(changes["raw_phone"])
    changed_fields = []
    for field, value in changes.items():
        if getattr(locked, field) != value:
            setattr(locked, field, value)
            changed_fields.append(field)
    if changed_fields:
        try:
            locked.save(update_fields=[*changed_fields, "updated_at"])
        except IntegrityError as exc:
            raise BusinessConflictError({"raw_phone": "محدودیت شماره فعال یا شماره اصلی نقض شده است."}) from exc
        log_activity(
            actor=actor,
            operation="customer_phone.updated",
            instance=locked,
            changes={"customer": locked.customer_id, "fields": sorted(changed_fields)},
        )
        if "normalized_phone" in changed_fields:
            refresh_target_members_for_phone(
                normalized_phone=locked.normalized_phone, actor=actor
            )
    return locked


@transaction.atomic
def deactivate_customer_phone(*, actor, phone):
    actor = _lock_operational_actor(actor)
    locked = CustomerPhone.objects.select_for_update().select_related("customer").get(pk=phone.pk)
    if not customers_for(actor).filter(pk=locked.customer_id).exists():
        raise BusinessPermissionDenied("این مشتری خارج از دسترسی شماست.")
    if not locked.is_active:
        raise BusinessConflictError({"is_active": "این تلفن مشتری قبلاً غیرفعال شده است."})
    locked.is_active = False
    locked.is_primary = False
    locked.save(update_fields=["is_active", "is_primary", "updated_at"])
    log_activity(actor=actor, operation="customer_phone.deactivated", instance=locked)
    return locked


@transaction.atomic
def create_lead(*, actor, customer=None, **data):
    """Start a campaign.

    `customer` is optional: a campaign is worked from its target audience, and
    the people in it are not customers yet. When one is named it still has to
    be inside the caller's scope.
    """
    actor = _lock_operational_actor(actor)
    unknown = set(data) - LEAD_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    _validate_text_lengths(data, LEAD_TEXT_LIMITS)
    _validate_lead_status(data)
    if customer is not None and not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("این مشتری خارج از دسترسی شماست.")
    lead = Lead.objects.create(customer=customer, created_by=actor, source_payload={}, **data)
    log_activity(
        actor=actor,
        operation="lead.created",
        instance=lead,
        changes={"customer": customer.pk if customer else None, "fields": sorted(data)},
    )
    return lead


@transaction.atomic
def update_lead(*, actor, lead, **changes):
    actor = _lock_operational_actor(actor)
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if actor.role == User.Role.SALES_AGENT and locked.assigned_to_id != actor.pk:
        raise BusinessPermissionDenied("این سرنخ خارج از دسترسی شماست.")
    if "customer" in changes:
        if changes["customer"].pk != locked.customer_id:
            raise BusinessRuleError({"customer": "مشتری سرنخ قابل تغییر نیست."})
        changes.pop("customer")
    unknown = set(changes) - LEAD_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    _validate_text_lengths(changes, LEAD_TEXT_LIMITS)
    _validate_lead_status(changes)
    changed_fields = []
    for field, value in changes.items():
        current_id = getattr(locked, f"{field}_id", None) if field in {"customer", "interested_product"} else None
        value_id = value.pk if field in {"customer", "interested_product"} and value is not None else None
        if field in {"customer", "interested_product"}:
            changed = current_id != value_id
        else:
            changed = getattr(locked, field) != value
        if changed:
            setattr(locked, field, value)
            changed_fields.append(field)
    if changed_fields:
        locked.save(update_fields=[*changed_fields, "updated_at"])
        log_activity(
            actor=actor,
            operation="lead.updated",
            instance=locked,
            changes={"customer": locked.customer_id, "fields": sorted(changed_fields)},
        )
    return locked


@transaction.atomic
def create_product_category(*, actor, **data):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "product_categories.manage"):
        raise BusinessPermissionDenied("مدیریت دسته‌بندی کالا مجاز نیست.")
    unknown = set(data) - PRODUCT_CATEGORY_CREATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    _validate_text_lengths(data, PRODUCT_CATEGORY_TEXT_LIMITS)
    name, normalized_name = _clean_category_name(data.get("name", ""))
    code = _clean_category_code(data.get("code", ""))
    display_order = data.get("display_order", 0)
    if isinstance(display_order, bool) or not isinstance(display_order, int) or display_order < 0:
        raise BusinessRuleError({"display_order": "ترتیب نمایش باید عددی صحیح و غیرمنفی باشد."})
    try:
        category = ProductCategory.objects.create(
            code=code,
            name=name,
            normalized_name=normalized_name,
            description=data.get("description", ""),
            display_order=display_order,
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError as exc:
        raise BusinessConflictError({
            "code": "کد دسته‌بندی باید یکتا باشد.",
            "name": "نام یکتاشده دسته‌بندی باید یکتا باشد.",
        }) from exc
    log_activity(
        actor=actor,
        operation="product_category.created",
        instance=category,
        changes={"fields": sorted(PRODUCT_CATEGORY_CREATE_FIELDS.intersection(data))},
    )
    return category


@transaction.atomic
def update_product_category(*, actor, category, **changes):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "product_categories.manage"):
        raise BusinessPermissionDenied("مدیریت دسته‌بندی کالا مجاز نیست.")
    locked = ProductCategory.objects.select_for_update().get(pk=category.pk)
    unknown = set(changes) - PRODUCT_CATEGORY_UPDATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    _validate_text_lengths(changes, PRODUCT_CATEGORY_TEXT_LIMITS)
    if "name" in changes:
        changes["name"], changes["normalized_name"] = _clean_category_name(changes["name"])
    if "display_order" in changes:
        display_order = changes["display_order"]
        if isinstance(display_order, bool) or not isinstance(display_order, int) or display_order < 0:
            raise BusinessRuleError({"display_order": "ترتیب نمایش باید عددی صحیح و غیرمنفی باشد."})
    changed_fields = []
    for field, value in changes.items():
        if getattr(locked, field) != value:
            setattr(locked, field, value)
            changed_fields.append(field)
    if changed_fields:
        locked.updated_by = actor
        try:
            locked.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
        except IntegrityError as exc:
            raise BusinessConflictError({"name": "نام یکتاشده این دسته‌بندی قبلاً استفاده شده است."}) from exc
        log_activity(
            actor=actor,
            operation="product_category.updated",
            instance=locked,
            changes={"fields": sorted(changed_fields)},
        )
    return locked


def _prepare_product_values(data):
    prepared = dict(data)
    if "category" in prepared and prepared["category"] is not None:
        category = ProductCategory.objects.select_for_update().filter(
            pk=prepared["category"].pk,
            is_active=True,
        ).first()
        if category is None:
            raise BusinessRuleError({"category": "یک دسته‌بندی فعال را انتخاب کنید."})
        prepared["category"] = category
    if "brand" in prepared:
        prepared["brand"] = _clean_single_line(prepared["brand"], field="brand", limit=120)
    if "barcode" in prepared:
        prepared["barcode"] = _clean_product_barcode(prepared["barcode"])
    if "unit" in prepared:
        # The database constraint would catch this too, but only as an
        # IntegrityError that this module reports as a SKU conflict — a message
        # naming the wrong field. Checked here so the caller is told what is
        # actually wrong. Blank is allowed: products created before the field
        # existed have no unit, and a default would print a wrong word on an
        # invoice.
        unit = (prepared["unit"] or "").strip()
        if unit and unit not in Product.Unit.values:
            raise BusinessRuleError({"unit": "واحد را از فهرست انتخاب کنید."})
        prepared["unit"] = unit
    return prepared


@transaction.atomic
def create_product(*, actor, **data):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "products.manage"):
        raise BusinessPermissionDenied("مدیریت کالا مجاز نیست.")
    unknown = set(data) - PRODUCT_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    _validate_text_lengths(data, PRODUCT_TEXT_LIMITS)
    data = _prepare_product_values(data)
    try:
        product = Product.objects.create(created_by=actor, updated_by=actor, **data)
    except IntegrityError as exc:
        raise BusinessConflictError({
            "sku": "این کد کالا قبلاً استفاده شده یا اطلاعات کالا نامعتبر است.",
            "barcode": "بارکد غیرخالی باید یکتا باشد.",
        }) from exc
    log_activity(actor=actor, operation="product.created", instance=product, changes={"fields": sorted(data)})
    return product


@transaction.atomic
def update_product(*, actor, product, **changes):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "products.manage"):
        raise BusinessPermissionDenied("مدیریت کالا مجاز نیست.")
    locked = Product.objects.select_for_update().get(pk=product.pk)
    unknown = set(changes) - PRODUCT_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    _validate_text_lengths(changes, PRODUCT_TEXT_LIMITS)
    changes = _prepare_product_values(changes)
    changed_fields = []
    for field, value in changes.items():
        current = getattr(locked, f"{field}_id") if field == "category" else getattr(locked, field)
        incoming = value.pk if field == "category" and value is not None else value
        if current != incoming:
            setattr(locked, field, value)
            changed_fields.append(field)
    if changed_fields:
        locked.updated_by = actor
        try:
            locked.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
        except IntegrityError as exc:
            raise BusinessConflictError({
                "sku": "این کد کالا قبلاً استفاده شده یا اطلاعات کالا نامعتبر است.",
                "barcode": "بارکد غیرخالی باید یکتا باشد.",
            }) from exc
        log_activity(actor=actor, operation="product.updated", instance=locked, changes={"fields": sorted(changed_fields)})
    return locked


@transaction.atomic
def reassign_lead(*, actor, lead, to_user, reason=""):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("واگذاری مجدد سرنخ مجاز نیست.")
    target = User.objects.select_for_update().get(pk=to_user.pk)
    if not is_crm_identity(target) or target.role != User.Role.SALES_AGENT:
        raise BusinessRuleError({"to_user": "مقصد باید یک بازاریاب فعال باشد."})
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    previous = locked.assigned_to
    if previous == target:
        raise BusinessConflictError({"to_user": "این سرنخ قبلاً به این کاربر واگذار شده است."})
    locked.assigned_to = target
    locked.assigned_by = actor
    locked.assigned_at = timezone.now()
    locked.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "updated_at"])
    LeadAssignmentHistory.objects.create(lead=locked, from_user=previous, to_user=target, changed_by=actor, reason=reason)
    log_activity(
        actor=actor,
        operation="lead.reassigned",
        instance=locked,
        changes={"from_user": previous.pk if previous else None, "to_user": target.pk, "reason_provided": bool(reason)},
    )
    return locked


def assign_lead(*, actor, lead, to_user, reason=""):
    return reassign_lead(actor=actor, lead=lead, to_user=to_user, reason=reason)


@transaction.atomic
def record_interaction(*, actor, lead, target_member=None, **data):
    """Log a call.

    A call is recorded against whoever was actually spoken to. Early in a
    campaign that is a target-audience identity with no customer record yet, so
    `target_member` may be given instead of relying on the lead's customer. When
    the identity has already been matched to a customer, both are stored.

    Logging a call is what moves an identity to "در تعامل", so the derived
    status is refreshed here rather than by a signal — the write and the
    conclusion drawn from it stay in one transaction.
    """
    actor = _lock_operational_actor(actor)
    unknown = set(data) - INTERACTION_CREATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    _validate_text_lengths(data, INTERACTION_TEXT_LIMITS)
    _validate_interaction_data(data)
    locked_lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if actor.role == User.Role.SALES_AGENT and locked_lead.assigned_to_id != actor.pk:
        raise BusinessPermissionDenied("این سرنخ خارج از دسترسی شماست.")
    customer = locked_lead.customer
    if target_member is not None:
        if target_member.lead_id != locked_lead.pk:
            raise BusinessRuleError({"target_member": "این شناسه متعلق به کمپین دیگری است."})
        if not target_audience_for(actor).filter(pk=target_member.pk).exists():
            raise BusinessPermissionDenied("این مخاطب هدف خارج از دسترسی شماست.")
        customer = target_member.customer or customer
    interaction = Interaction.objects.create(
        lead=locked_lead, customer=customer, target_member=target_member, agent=actor, **data
    )
    if target_member is not None:
        refresh_target_member_status(member=target_member, actor=actor)
    next_follow_up_at = data.get("next_follow_up_at")
    if next_follow_up_at is not None and locked_lead.next_follow_up_at != next_follow_up_at:
        locked_lead.next_follow_up_at = next_follow_up_at
        locked_lead.save(update_fields=["next_follow_up_at", "updated_at"])
    return interaction


@transaction.atomic
def mark_sale(*, actor, lead, product=None, quantity=1, total_amount=None, **data):
    actor = _lock_operational_actor(actor)
    unknown = set(data) - SALE_CREATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    _validate_text_lengths(data, SALE_TEXT_LIMITS)
    locked_lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if actor.role == User.Role.SALES_AGENT and locked_lead.assigned_to_id != actor.pk:
        raise BusinessPermissionDenied("این سرنخ خارج از دسترسی شماست.")
    if quantity < 1:
        raise BusinessRuleError({"quantity": "تعداد باید مثبت باشد."})
    unit_price = None
    if product:
        product = Product.objects.select_for_update().get(pk=product.pk)
        if not product.is_active:
            raise BusinessConflictError({"product": "کالا غیرفعال است."})
        unit_price = product.current_price
        total_amount = unit_price * quantity
    elif total_amount is None:
        raise BusinessRuleError({"total_amount": "بدون انتخاب کالا، وارد کردن مبلغ الزامی است."})
    total_amount = Decimal(total_amount)
    if total_amount < 0:
        raise BusinessRuleError({"total_amount": "مبلغ نمی‌تواند منفی باشد."})
    if total_amount > MAX_MONEY:
        raise BusinessRuleError({"total_amount": "مبلغ بیش از حد مجاز است."})
    if locked_lead.customer_id is None:
        raise BusinessRuleError({
            "customer": "پیش از ثبت نتیجه این کمپین، مشتری را مشخص کنید."
        })
    # `sold_at` is NOT NULL with no database default. The serializer defaults it
    # to now, so the panel always supplies one — but a caller that does not (a
    # command, an import, a future endpoint) hit an IntegrityError instead of
    # the BusinessRuleError every other missing field here raises, surfacing as
    # a 500 rather than a 400. Defaulting to the serializer's own choice keeps
    # the two in step and closes that path without changing what the panel does.
    data.setdefault("sold_at", timezone.now())
    sale = Sale.objects.create(
        lead=locked_lead,
        customer=locked_lead.customer,
        sold_by=actor,
        product=product,
        quantity=quantity,
        unit_price_snapshot=unit_price,
        total_amount=total_amount,
        status=Sale.Status.CONFIRMED,
        **data,
    )
    log_activity(actor=actor, operation="sale.created", instance=sale, changes={"lead": locked_lead.pk, "total_amount": str(total_amount)})
    return sale


@transaction.atomic
def cancel_sale(*, actor, sale, reason=""):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("لغو فروش مجاز نیست.")
    locked = Sale.objects.select_for_update().get(pk=sale.pk)
    if locked.status == Sale.Status.CANCELLED:
        raise BusinessConflictError({"status": "این فروش قبلاً لغو شده است."})
    locked.status = Sale.Status.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    log_activity(actor=actor, operation="sale.cancelled", instance=locked, changes={"reason_provided": bool(reason)})
    return locked


def cancel_or_correct_sale(*, actor, sale, operation="cancel", reason="", correction=None):
    if operation != "cancel" or correction:
        raise BusinessRuleError({"operation": "قواعد اصلاح فروش هنوز تأیید نشده است."})
    return cancel_sale(actor=actor, sale=sale, reason=reason)


def _clean_required_text(value, *, field, limit):
    value = value.strip() if isinstance(value, str) else ""
    if not value:
        raise BusinessRuleError({field: "این فیلد الزامی است."})
    if any(character in value for character in "\r\n\t"):
        raise BusinessRuleError({field: "این مقدار باید تک‌خطی باشد."})
    if len(value) > limit:
        raise BusinessRuleError({field: f"این فیلد نباید بیش از {limit} نویسه داشته باشد."})
    return value


@transaction.atomic
def register_sales_document(*, actor, customer, document_number, postal_status, sale=None, notes=""):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "sales_documents.manage"):
        raise BusinessPermissionDenied("ثبت سند فروش مجاز نیست.")
    locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if not customers_for(actor).filter(pk=locked_customer.pk).exists():
        raise BusinessPermissionDenied("این مشتری خارج از دسترسی شماست.")
    locked_sale = None
    if sale is not None:
        locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if not sales_for(actor).filter(pk=locked_sale.pk).exists():
            raise BusinessPermissionDenied("این فروش خارج از دسترسی شماست.")
        if locked_sale.customer_id != locked_customer.pk:
            raise BusinessRuleError({"sale": "فروش باید متعلق به مشتری انتخاب‌شده باشد."})
    document_number = _clean_required_text(document_number, field="document_number", limit=64)
    postal_status = _clean_required_text(postal_status, field="postal_status", limit=80)
    _validate_text_lengths({"notes": notes}, SALES_DOCUMENT_TEXT_LIMITS)
    try:
        document = SalesDocument.objects.create(
            customer=locked_customer,
            sale=locked_sale,
            document_number=document_number,
            province_snapshot=locked_customer.province,
            city_snapshot=locked_customer.city,
            postal_code_snapshot=locked_customer.postal_code,
            address_snapshot=locked_customer.address,
            postal_status=postal_status,
            registered_by=actor,
            notes=notes,
        )
    except IntegrityError as exc:
        raise BusinessConflictError({"document_number": "شماره سند قبلاً استفاده شده یا اطلاعات نامعتبر است."}) from exc
    PostalStatusHistory.objects.create(
        document=document,
        from_status="",
        to_status=postal_status,
        changed_by=actor,
    )
    log_activity(
        actor=actor,
        operation="sales_document.registered",
        instance=document,
        changes={"fields": ["customer", "sale", "document_number", "postal_status", "address_snapshot"]},
    )
    return document


@transaction.atomic
def transition_postal_status(*, actor, document, to_status, reason=""):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "sales_documents.manage"):
        raise BusinessPermissionDenied("تغییر وضعیت پستی مجاز نیست.")
    locked = SalesDocument.objects.select_for_update().get(pk=document.pk)
    if not locked.is_active:
        raise BusinessConflictError({"is_active": "سند غیرفعال نمی‌تواند وضعیت پستی خود را تغییر دهد."})
    to_status = _clean_required_text(to_status, field="to_status", limit=80)
    if len(reason) > 500:
        raise BusinessRuleError({"reason": "این فیلد نباید بیش از ۵۰۰ نویسه داشته باشد."})
    if locked.postal_status == to_status:
        raise BusinessConflictError({"to_status": "وضعیت پستی هم‌اکنون همین مقدار است."})
    previous = locked.postal_status
    locked.postal_status = to_status
    locked.save(update_fields=["postal_status", "updated_at"])
    PostalStatusHistory.objects.create(
        document=locked,
        from_status=previous,
        to_status=to_status,
        changed_by=actor,
        reason=reason,
    )
    log_activity(
        actor=actor,
        operation="sales_document.postal_status_changed",
        instance=locked,
        changes={"postal_from": previous, "postal_to": to_status, "reason_provided": bool(reason)},
    )
    return locked


@transaction.atomic
def deactivate_sales_document(*, actor, document):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "sales_documents.manage"):
        raise BusinessPermissionDenied("غیرفعال‌سازی سند فروش مجاز نیست.")
    locked = SalesDocument.objects.select_for_update().get(pk=document.pk)
    if not locked.is_active:
        raise BusinessConflictError({"is_active": "این سند فروش قبلاً غیرفعال شده است."})
    locked.is_active = False
    locked.save(update_fields=["is_active", "updated_at"])
    log_activity(actor=actor, operation="sales_document.deactivated", instance=locked)
    return locked


@transaction.atomic
def set_customer_active(*, actor, customer, is_active):
    """Turn a customer on or off. Platform Admin only.

    Deactivating hides the customer from day-to-day work; it never removes a
    row. Every order, invoice, payment and ledger entry stays exactly as it
    was, which is why this is reversible and why nothing here deletes.
    """
    actor = _require_status_administrator(actor)
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("این مشتری خارج از دسترسی شماست.")
    is_active = bool(is_active)
    if customer.is_active == is_active:
        state = "فعال" if is_active else "غیرفعال"
        raise BusinessConflictError({"is_active": f"این مشتری هم‌اکنون {state} است."})
    customer.is_active = is_active
    customer.save(update_fields=["is_active", "updated_at"])
    log_activity(
        actor=actor,
        operation="customer.reactivated" if is_active else "customer.deactivated",
        instance=customer,
    )
    return customer


def deactivate_customer(*, actor, customer):
    """Kept as the name the API route and older callers already use."""
    return set_customer_active(actor=actor, customer=customer, is_active=False)


@transaction.atomic
def set_product_active(*, actor, product, is_active):
    """Turn a product on or off. Platform Admin only.

    Activation decides whether the product can still be sold, so it sits with
    the same role that owns customer activation. Deactivating removes nothing:
    every past sale, order line and invoice line keeps its snapshot, which is
    why this is reversible.
    """
    actor = _require_status_administrator(actor)
    product = Product.objects.select_for_update().get(pk=product.pk)
    is_active = bool(is_active)
    if product.is_active == is_active:
        state = "فعال" if is_active else "غیرفعال"
        raise BusinessConflictError({"is_active": f"این کالا هم‌اکنون {state} است."})
    product.is_active = is_active
    product.updated_by = actor
    product.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(
        actor=actor,
        operation="product.reactivated" if is_active else "product.deactivated",
        instance=product,
    )
    return product


@transaction.atomic
def deactivate_product(*, actor, product):
    # Activation decides whether the product can still be sold, so Client-1
    # keeps it with the Platform Admin. Every other product edit stays with the
    # operational roles.
    actor = _require_status_administrator(actor)
    product = Product.objects.select_for_update().get(pk=product.pk)
    if not product.is_active:
        raise BusinessConflictError({"is_active": "این کالا قبلاً غیرفعال شده است."})
    product.is_active = False
    product.updated_by = actor
    product.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="product.deactivated", instance=product)
    return product


@transaction.atomic
def deactivate_product_category(*, actor, category):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "product_categories.manage"):
        raise BusinessPermissionDenied("مدیریت دسته‌بندی کالا مجاز نیست.")
    category = ProductCategory.objects.select_for_update().get(pk=category.pk)
    if not category.is_active:
        raise BusinessConflictError({"is_active": "این دسته‌بندی کالا قبلاً غیرفعال شده است."})
    if Product.objects.select_for_update().filter(category=category, is_active=True).exists():
        raise BusinessConflictError({
            "category": "پیش از غیرفعال‌سازی این دسته‌بندی، کالاهای فعال آن را جابه‌جا یا غیرفعال کنید."
        })
    category.is_active = False
    category.updated_by = actor
    category.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="product_category.deactivated", instance=category)
    return category


@transaction.atomic
def reactivate_product_category(*, actor, category):
    actor = _lock_active_actor(actor)
    if not has_any_capability(actor, "product_categories.manage"):
        raise BusinessPermissionDenied("مدیریت دسته‌بندی کالا مجاز نیست.")
    category = ProductCategory.objects.select_for_update().get(pk=category.pk)
    if category.is_active:
        raise BusinessConflictError({"is_active": "این دسته‌بندی کالا قبلاً فعال شده است."})
    category.is_active = True
    category.updated_by = actor
    category.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="product_category.reactivated", instance=category)
    return category


# --- Target audience ("جامعه هدف") ------------------------------------------
#
# The people a campaign is worked from. Only an elevated role may edit the list;
# a marketer reads the audience of the campaigns assigned to them. That split is
# enforced here, not in the template — a hidden button is not authorization.

#: `status` is absent on purpose: it is derived from what actually happened and
#: is never typed in. See `refresh_target_member_status`.
TARGET_MEMBER_MUTABLE_FIELDS = {"full_name", "raw_phone", "notes"}
TARGET_MEMBER_TEXT_LIMITS = {"full_name": 255, "raw_phone": 40, "notes": FREE_TEXT_MAX_LENGTH}
#: Kept as an empty set so callers that still consult it read "nothing may be
#: assigned by hand" rather than crashing on a missing name.
TARGET_MEMBER_ASSIGNABLE_STATUSES = frozenset()


#: Roles that may turn a business record on or off, or move an order through
#: its lifecycle. Client-1 gives `sales_manager` the same functional access as
#: `platform_admin`; what stays Platform-Admin-only is the security and
#: administration plane — user accounts, sessions, the deployment itself — not
#: business workflow. `company_it` is a technical role and is deliberately not
#: here: it administers the deployment, it does not run the shop.
STATUS_ADMINISTRATORS = frozenset({User.Role.SALES_MANAGER, User.Role.PLATFORM_ADMIN})


def _require_status_administrator(actor):
    """Turning a record on or off, for the roles that run the business.

    Activation decides whether a product can still be sold and whether a
    customer can still be worked — an operational decision, so the store
    manager holds it alongside the platform administrator. Every marketer edit
    stays out.
    """
    actor = _lock_operational_actor(actor)
    if actor.role not in STATUS_ADMINISTRATORS:
        raise BusinessPermissionDenied("تغییر وضعیت فعال‌بودن مجاز نیست.")
    return actor


def _require_target_audience_editor(actor):
    actor = _lock_operational_actor(actor)
    if actor.role == User.Role.SALES_AGENT:
        raise BusinessPermissionDenied("ویرایش مخاطبان هدف مجاز نیست.")
    return actor


def _derived_target_status(member):
    """The status the world implies for this identity, or None to keep it.

    Two rules, in priority order, exactly as the product states them: an
    identity that exists in the customer book is a customer; an identity the
    call centre has spoken to is engaged. Being a customer outranks being
    engaged, so the checks run in that order.
    """
    customer = (
        Customer.objects.filter(
            phones__normalized_phone=member.normalized_phone, phones__is_active=True
        )
        .order_by("pk")
        .first()
    )
    if customer is not None:
        return TargetAudienceMember.Status.CUSTOMER, customer
    if member.interactions.exists():
        return TargetAudienceMember.Status.ENGAGED, None
    return None, None


@transaction.atomic
def refresh_target_member_status(*, member, actor=None):
    """Apply the derived-status rules to one identity.

    Called after anything that could change the answer: a call logged, a
    customer created, a phone number edited. It writes only when the answer
    actually differs, so it is safe to call often and leaves no audit noise.
    """
    locked = TargetAudienceMember.objects.select_for_update().get(pk=member.pk)
    derived, customer = _derived_target_status(locked)
    if derived is None or locked.status == derived:
        return locked
    previous = locked.status
    locked.status = derived
    fields = ["status", "updated_at"]
    if customer is not None and locked.customer_id != customer.pk:
        locked.customer = customer
        fields.insert(1, "customer")
    if actor is not None:
        locked.updated_by = actor
        fields.insert(1, "updated_by")
    locked.save(update_fields=fields)
    log_activity(
        actor=actor or locked.updated_by,
        operation="target_audience.status_derived",
        instance=locked,
        changes={"lead": locked.lead_id, "from": previous, "to": derived},
    )
    return locked


def refresh_target_members_for_phone(*, normalized_phone, actor=None):
    """Re-derive every campaign entry that shares one phone number.

    The same person can sit in several campaigns; becoming a customer makes
    every one of those entries a customer.
    """
    for member in TargetAudienceMember.objects.filter(normalized_phone=normalized_phone):
        refresh_target_member_status(member=member, actor=actor)


@transaction.atomic
def add_target_audience_member(*, actor, lead, full_name, raw_phone, status="", notes=""):
    actor = _require_target_audience_editor(actor)
    locked_lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if not leads_for(actor).filter(pk=locked_lead.pk).exists():
        raise BusinessPermissionDenied("این سرنخ خارج از دسترسی شماست.")
    data = {"full_name": full_name, "raw_phone": raw_phone, "notes": notes}
    _validate_text_lengths(data, TARGET_MEMBER_TEXT_LIMITS)
    if not str(full_name).strip():
        raise BusinessRuleError({"full_name": "این فیلد الزامی است."})
    if status:
        raise BusinessRuleError({"status": "وضعیت به‌صورت خودکار تعیین می‌شود و قابل تنظیم نیست."})
    # Every identity enters the audience as a lead. Where it goes from there is
    # decided by what happens to it, not by what anyone types.
    status = TargetAudienceMember.Status.LEAD
    normalized = normalize_customer_phone(raw_phone)
    try:
        member = TargetAudienceMember.objects.create(
            lead=locked_lead,
            full_name=str(full_name).strip(),
            raw_phone=raw_phone,
            normalized_phone=normalized,
            status=status,
            notes=notes,
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError as exc:
        raise BusinessConflictError(
            {"raw_phone": "این شماره قبلاً در این کمپین ثبت شده است."}
        ) from exc
    log_activity(
        actor=actor,
        operation="target_audience.added",
        instance=member,
        changes={"lead": locked_lead.pk, "status": status},
    )
    # A number that already belongs to a customer starts as one.
    return refresh_target_member_status(member=member, actor=actor)


@transaction.atomic
def update_target_audience_member(*, actor, member, **changes):
    actor = _require_target_audience_editor(actor)
    locked = (
        TargetAudienceMember.objects.select_for_update().select_related("lead").get(pk=member.pk)
    )
    if not target_audience_for(actor).filter(pk=locked.pk).exists():
        raise BusinessPermissionDenied("این مخاطب هدف خارج از دسترسی شماست.")
    unknown = set(changes) - TARGET_MEMBER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    _validate_text_lengths(changes, TARGET_MEMBER_TEXT_LIMITS)
    if "raw_phone" in changes:
        changes["normalized_phone"] = normalize_customer_phone(changes["raw_phone"])
    if "full_name" in changes:
        changes["full_name"] = str(changes["full_name"]).strip()
        if not changes["full_name"]:
            raise BusinessRuleError({"full_name": "این فیلد الزامی است."})
    changed_fields = []
    for field, value in changes.items():
        if getattr(locked, field) != value:
            setattr(locked, field, value)
            changed_fields.append(field)
    if changed_fields:
        locked.updated_by = actor
        try:
            locked.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
        except IntegrityError as exc:
            raise BusinessConflictError(
                {"raw_phone": "این شماره قبلاً در این کمپین ثبت شده است."}
            ) from exc
        log_activity(
            actor=actor,
            operation="target_audience.updated",
            instance=locked,
            changes={"lead": locked.lead_id, "fields": sorted(changed_fields)},
        )
    return refresh_target_member_status(member=locked, actor=actor)
