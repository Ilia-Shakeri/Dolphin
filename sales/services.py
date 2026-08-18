import re
import unicodedata
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.access import is_crm_identity
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
PRODUCT_MUTABLE_FIELDS = {"sku", "name", "category", "brand", "barcode", "current_price", "description"}
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
        raise BusinessRuleError({"status": "Choose one of the three campaign states."})


def _validate_text_lengths(values, limits):
    errors = {
        field: f"Ensure this field has no more than {limit} characters."
        for field, limit in limits.items()
        if field in values and isinstance(values[field], str) and len(values[field]) > limit
    }
    if errors:
        raise BusinessRuleError(errors)


def _validate_interaction_data(data):
    errors = {}
    if data.get("direction") not in Interaction.Direction.values:
        errors["direction"] = "Direction must be inbound or outbound."
    outcome = data.get("outcome")
    if not isinstance(outcome, str) or not outcome.strip():
        errors["outcome"] = "Outcome is required."
    elif len(outcome.strip()) > INTERACTION_OUTCOME_MAX_LENGTH:
        errors["outcome"] = (
            f"Ensure this field has no more than {INTERACTION_OUTCOME_MAX_LENGTH} characters."
        )
    if errors:
        raise BusinessRuleError(errors)
    data["outcome"] = outcome.strip()


def _lock_active_actor(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked) or locked.role not in VALID_ROLES:
        raise BusinessPermissionDenied("Active user is required.")
    return locked


def _lock_operational_actor(actor):
    locked = _lock_active_actor(actor)
    if locked.role not in OPERATIONAL_WRITERS:
        raise BusinessPermissionDenied("Operational changes are not allowed.")
    return locked


_CATEGORY_CODE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", flags=re.ASCII)
_PRODUCT_BARCODE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$", flags=re.ASCII)
_PERSIAN_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})


def _clean_category_name(value):
    name = " ".join(unicodedata.normalize("NFKC", str(value)).translate(_PERSIAN_LETTERS).split())
    if not name:
        raise BusinessRuleError({"name": "Category name is required."})
    if len(name) > 120:
        raise BusinessRuleError({"name": "Ensure this field has no more than 120 characters."})
    return name, name.casefold()


def _clean_category_code(value):
    code = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if not _CATEGORY_CODE.fullmatch(code):
        raise BusinessRuleError({"code": "Use lowercase ASCII letters, digits, underscore, or hyphen."})
    return code


def _clean_product_barcode(value):
    barcode = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    if barcode and not _PRODUCT_BARCODE.fullmatch(barcode):
        raise BusinessRuleError({"barcode": "Use ASCII letters, digits, dot, underscore, or hyphen."})
    return barcode


def _clean_single_line(value, *, field, limit):
    cleaned = " ".join(unicodedata.normalize("NFKC", str(value or "")).split())
    if len(cleaned) > limit:
        raise BusinessRuleError({field: f"Ensure this field has no more than {limit} characters."})
    return cleaned


@transaction.atomic
def create_customer_with_phone(*, actor, phone=None, **data):
    actor = _lock_operational_actor(actor)
    unknown = set(data) - CUSTOMER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, CUSTOMER_TEXT_LIMITS)
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
        raise BusinessPermissionDenied("Customer is outside your scope.")
    unknown = set(changes) - CUSTOMER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    _validate_text_lengths(changes, CUSTOMER_TEXT_LIMITS)
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
        raise BusinessPermissionDenied("Customer is outside your scope.")
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
        raise BusinessConflictError({"raw_phone": "Active phone identity or primary-phone constraint failed."}) from exc
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
        raise BusinessPermissionDenied("Customer is outside your scope.")
    unknown = set(changes) - PHONE_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
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
            raise BusinessConflictError({"raw_phone": "Active phone identity or primary-phone constraint failed."}) from exc
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
        raise BusinessPermissionDenied("Customer is outside your scope.")
    if not locked.is_active:
        raise BusinessConflictError({"is_active": "Customer phone is already inactive."})
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
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, LEAD_TEXT_LIMITS)
    _validate_lead_status(data)
    if customer is not None and not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("Customer is outside your scope.")
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
        raise BusinessPermissionDenied("Lead is outside your scope.")
    if "customer" in changes:
        if changes["customer"].pk != locked.customer_id:
            raise BusinessRuleError({"customer": "Lead customer cannot change."})
        changes.pop("customer")
    unknown = set(changes) - LEAD_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
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
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product category management is not allowed.")
    unknown = set(data) - PRODUCT_CATEGORY_CREATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, PRODUCT_CATEGORY_TEXT_LIMITS)
    name, normalized_name = _clean_category_name(data.get("name", ""))
    code = _clean_category_code(data.get("code", ""))
    display_order = data.get("display_order", 0)
    if isinstance(display_order, bool) or not isinstance(display_order, int) or display_order < 0:
        raise BusinessRuleError({"display_order": "Display order must be a non-negative integer."})
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
            "code": "Category code must be unique.",
            "name": "Normalized category name must be unique.",
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
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product category management is not allowed.")
    locked = ProductCategory.objects.select_for_update().get(pk=category.pk)
    unknown = set(changes) - PRODUCT_CATEGORY_UPDATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    _validate_text_lengths(changes, PRODUCT_CATEGORY_TEXT_LIMITS)
    if "name" in changes:
        changes["name"], changes["normalized_name"] = _clean_category_name(changes["name"])
    if "display_order" in changes:
        display_order = changes["display_order"]
        if isinstance(display_order, bool) or not isinstance(display_order, int) or display_order < 0:
            raise BusinessRuleError({"display_order": "Display order must be a non-negative integer."})
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
            raise BusinessConflictError({"name": "Normalized category name already exists."}) from exc
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
            raise BusinessRuleError({"category": "Select an active category."})
        prepared["category"] = category
    if "brand" in prepared:
        prepared["brand"] = _clean_single_line(prepared["brand"], field="brand", limit=120)
    if "barcode" in prepared:
        prepared["barcode"] = _clean_product_barcode(prepared["barcode"])
    return prepared


@transaction.atomic
def create_product(*, actor, **data):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product management is not allowed.")
    unknown = set(data) - PRODUCT_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, PRODUCT_TEXT_LIMITS)
    data = _prepare_product_values(data)
    try:
        product = Product.objects.create(created_by=actor, updated_by=actor, **data)
    except IntegrityError as exc:
        raise BusinessConflictError({
            "sku": "SKU already exists or product data is invalid.",
            "barcode": "Nonblank barcode must be unique.",
        }) from exc
    log_activity(actor=actor, operation="product.created", instance=product, changes={"fields": sorted(data)})
    return product


@transaction.atomic
def update_product(*, actor, product, **changes):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product management is not allowed.")
    locked = Product.objects.select_for_update().get(pk=product.pk)
    unknown = set(changes) - PRODUCT_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
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
                "sku": "SKU already exists or product data is invalid.",
                "barcode": "Nonblank barcode must be unique.",
            }) from exc
        log_activity(actor=actor, operation="product.updated", instance=locked, changes={"fields": sorted(changed_fields)})
    return locked


@transaction.atomic
def reassign_lead(*, actor, lead, to_user, reason=""):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Lead reassignment is not allowed.")
    target = User.objects.select_for_update().get(pk=to_user.pk)
    if not is_crm_identity(target) or target.role != User.Role.SALES_AGENT:
        raise BusinessRuleError({"to_user": "Target must be an active Sales Agent."})
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    previous = locked.assigned_to
    if previous == target:
        raise BusinessConflictError({"to_user": "Lead is already assigned to this user."})
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
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, INTERACTION_TEXT_LIMITS)
    _validate_interaction_data(data)
    locked_lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if actor.role == User.Role.SALES_AGENT and locked_lead.assigned_to_id != actor.pk:
        raise BusinessPermissionDenied("Lead is outside your scope.")
    customer = locked_lead.customer
    if target_member is not None:
        if target_member.lead_id != locked_lead.pk:
            raise BusinessRuleError({"target_member": "That identity belongs to another campaign."})
        if not target_audience_for(actor).filter(pk=target_member.pk).exists():
            raise BusinessPermissionDenied("Target audience entry is outside your scope.")
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
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, SALE_TEXT_LIMITS)
    locked_lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if actor.role == User.Role.SALES_AGENT and locked_lead.assigned_to_id != actor.pk:
        raise BusinessPermissionDenied("Lead is outside your scope.")
    if quantity < 1:
        raise BusinessRuleError({"quantity": "Quantity must be positive."})
    unit_price = None
    if product:
        product = Product.objects.select_for_update().get(pk=product.pk)
        if not product.is_active:
            raise BusinessConflictError({"product": "Product is inactive."})
        unit_price = product.current_price
        total_amount = unit_price * quantity
    elif total_amount is None:
        raise BusinessRuleError({"total_amount": "Amount is required without a product."})
    total_amount = Decimal(total_amount)
    if total_amount < 0:
        raise BusinessRuleError({"total_amount": "Amount cannot be negative."})
    if total_amount > MAX_MONEY:
        raise BusinessRuleError({"total_amount": "Amount is too large."})
    if locked_lead.customer_id is None:
        raise BusinessRuleError({
            "customer": "Record the customer before logging a result for this campaign."
        })
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
        raise BusinessPermissionDenied("Sale cancellation is not allowed.")
    locked = Sale.objects.select_for_update().get(pk=sale.pk)
    if locked.status == Sale.Status.CANCELLED:
        raise BusinessConflictError({"status": "Sale is already cancelled."})
    locked.status = Sale.Status.CANCELLED
    locked.save(update_fields=["status", "updated_at"])
    log_activity(actor=actor, operation="sale.cancelled", instance=locked, changes={"reason_provided": bool(reason)})
    return locked


def cancel_or_correct_sale(*, actor, sale, operation="cancel", reason="", correction=None):
    if operation != "cancel" or correction:
        raise BusinessRuleError({"operation": "Sale correction rules are not approved."})
    return cancel_sale(actor=actor, sale=sale, reason=reason)


def _clean_required_text(value, *, field, limit):
    value = value.strip() if isinstance(value, str) else ""
    if not value:
        raise BusinessRuleError({field: "This field is required."})
    if any(character in value for character in "\r\n\t"):
        raise BusinessRuleError({field: "Use a single-line value."})
    if len(value) > limit:
        raise BusinessRuleError({field: f"Ensure this field has no more than {limit} characters."})
    return value


@transaction.atomic
def register_sales_document(*, actor, customer, document_number, postal_status, sale=None, notes=""):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Sales document registration is not allowed.")
    locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if not customers_for(actor).filter(pk=locked_customer.pk).exists():
        raise BusinessPermissionDenied("Customer is outside your scope.")
    locked_sale = None
    if sale is not None:
        locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if not sales_for(actor).filter(pk=locked_sale.pk).exists():
            raise BusinessPermissionDenied("Sale is outside your scope.")
        if locked_sale.customer_id != locked_customer.pk:
            raise BusinessRuleError({"sale": "Sale must belong to the selected customer."})
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
        raise BusinessConflictError({"document_number": "Document number already exists or data is invalid."}) from exc
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
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Postal status transition is not allowed.")
    locked = SalesDocument.objects.select_for_update().get(pk=document.pk)
    if not locked.is_active:
        raise BusinessConflictError({"is_active": "Inactive document cannot change postal status."})
    to_status = _clean_required_text(to_status, field="to_status", limit=80)
    if len(reason) > 500:
        raise BusinessRuleError({"reason": "Ensure this field has no more than 500 characters."})
    if locked.postal_status == to_status:
        raise BusinessConflictError({"to_status": "Postal status is already set to this value."})
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
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Sales document deactivation is not allowed.")
    locked = SalesDocument.objects.select_for_update().get(pk=document.pk)
    if not locked.is_active:
        raise BusinessConflictError({"is_active": "Sales document is already inactive."})
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
        raise BusinessPermissionDenied("Customer is outside your scope.")
    is_active = bool(is_active)
    if customer.is_active == is_active:
        state = "active" if is_active else "inactive"
        raise BusinessConflictError({"is_active": f"Customer is already {state}."})
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
        state = "active" if is_active else "inactive"
        raise BusinessConflictError({"is_active": f"Product is already {state}."})
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
        raise BusinessConflictError({"is_active": "Product is already inactive."})
    product.is_active = False
    product.updated_by = actor
    product.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="product.deactivated", instance=product)
    return product


@transaction.atomic
def deactivate_product_category(*, actor, category):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product category management is not allowed.")
    category = ProductCategory.objects.select_for_update().get(pk=category.pk)
    if not category.is_active:
        raise BusinessConflictError({"is_active": "Product category is already inactive."})
    if Product.objects.select_for_update().filter(category=category, is_active=True).exists():
        raise BusinessConflictError({
            "category": "Move or deactivate active products before deactivating this category."
        })
    category.is_active = False
    category.updated_by = actor
    category.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="product_category.deactivated", instance=category)
    return category


@transaction.atomic
def reactivate_product_category(*, actor, category):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product category management is not allowed.")
    category = ProductCategory.objects.select_for_update().get(pk=category.pk)
    if category.is_active:
        raise BusinessConflictError({"is_active": "Product category is already active."})
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
        raise BusinessPermissionDenied("Changing activation state is not allowed.")
    return actor


def _require_target_audience_editor(actor):
    actor = _lock_operational_actor(actor)
    if actor.role == User.Role.SALES_AGENT:
        raise BusinessPermissionDenied("Editing the target audience is not allowed.")
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
        raise BusinessPermissionDenied("Lead is outside your scope.")
    data = {"full_name": full_name, "raw_phone": raw_phone, "notes": notes}
    _validate_text_lengths(data, TARGET_MEMBER_TEXT_LIMITS)
    if not str(full_name).strip():
        raise BusinessRuleError({"full_name": "This field is required."})
    if status:
        raise BusinessRuleError({"status": "Status is derived and cannot be set."})
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
            {"raw_phone": "This number is already in this campaign."}
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
        raise BusinessPermissionDenied("Target audience entry is outside your scope.")
    unknown = set(changes) - TARGET_MEMBER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    _validate_text_lengths(changes, TARGET_MEMBER_TEXT_LIMITS)
    if "raw_phone" in changes:
        changes["normalized_phone"] = normalize_customer_phone(changes["raw_phone"])
    if "full_name" in changes:
        changes["full_name"] = str(changes["full_name"]).strip()
        if not changes["full_name"]:
            raise BusinessRuleError({"full_name": "This field is required."})
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
                {"raw_phone": "This number is already in this campaign."}
            ) from exc
        log_activity(
            actor=actor,
            operation="target_audience.updated",
            instance=locked,
            changes={"lead": locked.lead_id, "fields": sorted(changed_fields)},
        )
    return refresh_target_member_status(member=locked, actor=actor)
