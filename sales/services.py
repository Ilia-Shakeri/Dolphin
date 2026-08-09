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
    FREE_TEXT_MAX_LENGTH,
    INTERACTION_OUTCOME_MAX_LENGTH,
    Customer,
    CustomerPhone,
    Interaction,
    Lead,
    LeadAssignmentHistory,
    Product,
    Sale,
)
from sales.selectors import customers_for


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
VALID_ROLES = {value for value, _ in User.Role.choices}
OPERATIONAL_WRITERS = {User.Role.SALES_AGENT, *ELEVATED_OPERATORS}
MAX_MONEY = Decimal("9999999999999999.99")
CUSTOMER_MUTABLE_FIELDS = {"full_name", "national_id", "email", "province", "city", "address", "notes"}
LEAD_MUTABLE_FIELDS = {"source", "campaign_or_batch", "interested_product", "next_follow_up_at", "notes"}
PHONE_MUTABLE_FIELDS = {"raw_phone", "label", "is_primary", "is_active"}
PRODUCT_MUTABLE_FIELDS = {"sku", "name", "current_price", "description"}
INTERACTION_CREATE_FIELDS = {"phone", "direction", "outcome", "occurred_at", "next_follow_up_at", "notes"}
SALE_CREATE_FIELDS = {"sold_at", "notes"}
CUSTOMER_TEXT_LIMITS = {"address": CUSTOMER_ADDRESS_MAX_LENGTH, "notes": FREE_TEXT_MAX_LENGTH}
LEAD_TEXT_LIMITS = {"notes": FREE_TEXT_MAX_LENGTH}
PRODUCT_TEXT_LIMITS = {"description": FREE_TEXT_MAX_LENGTH}
INTERACTION_TEXT_LIMITS = {"notes": FREE_TEXT_MAX_LENGTH}
SALE_TEXT_LIMITS = {"notes": FREE_TEXT_MAX_LENGTH}


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


@transaction.atomic
def create_customer_with_phone(*, actor, phone=None, **data):
    actor = _lock_operational_actor(actor)
    unknown = set(data) - CUSTOMER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, CUSTOMER_TEXT_LIMITS)
    customer = Customer.objects.create(created_by=actor, **data)
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
    return locked


@transaction.atomic
def create_customer_phone(*, actor, customer, raw_phone, label="", is_primary=False, is_active=True):
    actor = _lock_operational_actor(actor)
    if not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("Customer is outside your scope.")
    normalized = normalize_customer_phone(raw_phone)
    try:
        return CustomerPhone.objects.create(
            customer=customer,
            raw_phone=raw_phone,
            normalized_phone=normalized,
            label=label,
            is_primary=is_primary,
            is_active=is_active,
        )
    except IntegrityError as exc:
        raise BusinessConflictError({"raw_phone": "Active phone identity or primary-phone constraint failed."}) from exc


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
    return locked


@transaction.atomic
def create_lead(*, actor, customer, **data):
    actor = _lock_operational_actor(actor)
    unknown = set(data) - LEAD_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, LEAD_TEXT_LIMITS)
    if not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("Customer is outside your scope.")
    return Lead.objects.create(customer=customer, created_by=actor, source_payload={}, **data)


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
    return locked


@transaction.atomic
def create_product(*, actor, **data):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product management is not allowed.")
    unknown = set(data) - PRODUCT_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, PRODUCT_TEXT_LIMITS)
    try:
        product = Product.objects.create(created_by=actor, updated_by=actor, **data)
    except IntegrityError as exc:
        raise BusinessConflictError({"sku": "SKU already exists or product data is invalid."}) from exc
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
            raise BusinessConflictError({"sku": "SKU already exists or product data is invalid."}) from exc
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
def record_interaction(*, actor, lead, **data):
    actor = _lock_operational_actor(actor)
    unknown = set(data) - INTERACTION_CREATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    _validate_text_lengths(data, INTERACTION_TEXT_LIMITS)
    _validate_interaction_data(data)
    locked_lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if actor.role == User.Role.SALES_AGENT and locked_lead.assigned_to_id != actor.pk:
        raise BusinessPermissionDenied("Lead is outside your scope.")
    return Interaction.objects.create(lead=locked_lead, customer=locked_lead.customer, agent=actor, **data)


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


@transaction.atomic
def deactivate_customer(*, actor, customer):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Customer deactivation is not allowed.")
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("Customer is outside your scope.")
    if not customer.is_active:
        raise BusinessConflictError({"is_active": "Customer is already inactive."})
    customer.is_active = False
    customer.save(update_fields=["is_active", "updated_at"])
    log_activity(actor=actor, operation="customer.deactivated", instance=customer)
    return customer


@transaction.atomic
def deactivate_product(*, actor, product):
    actor = _lock_active_actor(actor)
    if actor.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Product management is not allowed.")
    product = Product.objects.select_for_update().get(pk=product.pk)
    if not product.is_active:
        raise BusinessConflictError({"is_active": "Product is already inactive."})
    product.is_active = False
    product.updated_by = actor
    product.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="product.deactivated", instance=product)
    return product
