"""Transactional inventory services.

Every level change goes through `record_stock_movement`. It takes the row lock
on the affected `StockItem` before reading it, so two concurrent issues of the
same product cannot both observe the pre-change level and drive stock negative.
The PostgreSQL concurrency suite exercises exactly that race.
"""

import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.access import is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from inventory.models import (
    IDEMPOTENCY_KEY_MAX_LENGTH,
    MAX_MONEY,
    MAX_QUANTITY,
    MOVEMENT_NOTES_MAX_LENGTH,
    MOVEMENT_REFERENCE_MAX_LENGTH,
    WAREHOUSE_ADDRESS_MAX_LENGTH,
    StockItem,
    StockMovement,
    Warehouse,
)
from sales.models import Product


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
WAREHOUSE_CREATE_FIELDS = {"code", "name", "address", "is_default"}
WAREHOUSE_UPDATE_FIELDS = {"name", "address", "is_default"}
MONEY = Decimal("0.01")
_PERSIAN_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})


def allow_negative_stock():
    """Whether an issue may drive a level below zero.

    Off by default: a warehouse that can go negative silently hides a counting
    error, and no approved contract asked for it. A deployment that genuinely
    sells before receipting turns it on explicitly.
    """
    return bool(getattr(settings, "INVENTORY_ALLOW_NEGATIVE_STOCK", False))


def _lock_active_actor(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked):
        raise BusinessPermissionDenied("Active user is required.")
    return locked


def _lock_inventory_manager(actor):
    locked = _lock_active_actor(actor)
    if locked.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("Inventory management is not allowed.")
    return locked


def _clean_single_line(value, *, field, limit, required=False):
    cleaned = " ".join(unicodedata.normalize("NFKC", str(value or "")).translate(_PERSIAN_LETTERS).split())
    if required and not cleaned:
        raise BusinessRuleError({field: "This field is required."})
    if len(cleaned) > limit:
        raise BusinessRuleError({field: f"Ensure this field has no more than {limit} characters."})
    return cleaned


def _clean_text(value, *, field, limit):
    text = unicodedata.normalize("NFKC", str(value or ""))
    if len(text) > limit:
        raise BusinessRuleError({field: f"Ensure this field has no more than {limit} characters."})
    return text


def _clean_warehouse_code(value):
    code = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    if not code or len(code) > 64:
        raise BusinessRuleError({"code": "Warehouse code is required."})
    if not all(character.isascii() and (character.isalnum() or character in "_-") for character in code):
        raise BusinessRuleError({"code": "Use lowercase ASCII letters, digits, underscore, or hyphen."})
    if not (code[0].isascii() and code[0].isalnum()):
        raise BusinessRuleError({"code": "Warehouse code must start with a letter or digit."})
    return code


def _clean_quantity(value, *, field="quantity"):
    if isinstance(value, bool) or not isinstance(value, int):
        raise BusinessRuleError({field: "Quantity must be a whole number."})
    if value < 1:
        raise BusinessRuleError({field: "Quantity must be positive."})
    if value > MAX_QUANTITY:
        raise BusinessRuleError({field: "Quantity is too large."})
    return value


def _clean_money(value, *, field, allow_none=False):
    if value is None:
        if allow_none:
            return None
        raise BusinessRuleError({field: "This field is required."})
    try:
        amount = Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError) as exc:
        raise BusinessRuleError({field: "Enter a valid amount."}) from exc
    if not amount.is_finite():
        raise BusinessRuleError({field: "Enter a valid amount."})
    amount = amount.quantize(MONEY, rounding=ROUND_HALF_UP)
    if amount < 0:
        raise BusinessRuleError({field: "Amount cannot be negative."})
    if amount > MAX_MONEY:
        raise BusinessRuleError({field: "Amount is too large."})
    return amount


@transaction.atomic
def create_warehouse(*, actor, **data):
    actor = _lock_inventory_manager(actor)
    unknown = set(data) - WAREHOUSE_CREATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    code = _clean_warehouse_code(data.get("code"))
    name = _clean_single_line(data.get("name"), field="name", limit=120, required=True)
    address = _clean_text(data.get("address", ""), field="address", limit=WAREHOUSE_ADDRESS_MAX_LENGTH)
    is_default = bool(data.get("is_default", False))
    if is_default:
        _clear_default_warehouse(actor=actor)
    try:
        warehouse = Warehouse.objects.create(
            code=code,
            name=name,
            normalized_name=name.casefold(),
            address=address,
            is_default=is_default,
            created_by=actor,
            updated_by=actor,
        )
    except IntegrityError as exc:
        raise BusinessConflictError({
            "code": "Warehouse code must be unique.",
            "name": "Warehouse name must be unique.",
        }) from exc
    log_activity(actor=actor, operation="warehouse.created", instance=warehouse, changes={"code": code})
    return warehouse


def _clear_default_warehouse(*, actor, keep_pk=None):
    current = Warehouse.objects.select_for_update().filter(is_default=True).first()
    if current is None or current.pk == keep_pk:
        return
    current.is_default = False
    current.updated_by = actor
    current.save(update_fields=["is_default", "updated_by", "updated_at"])


@transaction.atomic
def update_warehouse(*, actor, warehouse, **changes):
    actor = _lock_inventory_manager(actor)
    locked = Warehouse.objects.select_for_update().get(pk=warehouse.pk)
    unknown = set(changes) - WAREHOUSE_UPDATE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    if "name" in changes:
        name = _clean_single_line(changes["name"], field="name", limit=120, required=True)
        changes["name"] = name
        changes["normalized_name"] = name.casefold()
    if "address" in changes:
        changes["address"] = _clean_text(
            changes["address"], field="address", limit=WAREHOUSE_ADDRESS_MAX_LENGTH
        )
    if changes.get("is_default"):
        if not locked.is_active:
            raise BusinessConflictError({"is_default": "An inactive warehouse cannot be the default."})
        _clear_default_warehouse(actor=actor, keep_pk=locked.pk)
    changed_fields = [field for field, value in changes.items() if getattr(locked, field) != value]
    for field in changed_fields:
        setattr(locked, field, changes[field])
    if changed_fields:
        locked.updated_by = actor
        try:
            locked.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
        except IntegrityError as exc:
            raise BusinessConflictError({"name": "Warehouse name must be unique."}) from exc
        log_activity(
            actor=actor,
            operation="warehouse.updated",
            instance=locked,
            changes={"fields": sorted(changed_fields)},
        )
    return locked


@transaction.atomic
def deactivate_warehouse(*, actor, warehouse):
    actor = _lock_inventory_manager(actor)
    locked = Warehouse.objects.select_for_update().get(pk=warehouse.pk)
    if not locked.is_active:
        raise BusinessConflictError({"is_active": "Warehouse is already inactive."})
    # Deactivating a warehouse that still holds stock would strand that stock:
    # it stays in the ledger but leaves every level report. Transfer it first.
    if StockItem.objects.filter(warehouse=locked).exclude(quantity=0).exists():
        raise BusinessConflictError({
            "warehouse": "Move remaining stock out of this warehouse before deactivating it."
        })
    locked.is_active = False
    locked.is_default = False
    locked.updated_by = actor
    locked.save(update_fields=["is_active", "is_default", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="warehouse.deactivated", instance=locked)
    return locked


@transaction.atomic
def reactivate_warehouse(*, actor, warehouse):
    actor = _lock_inventory_manager(actor)
    locked = Warehouse.objects.select_for_update().get(pk=warehouse.pk)
    if locked.is_active:
        raise BusinessConflictError({"is_active": "Warehouse is already active."})
    locked.is_active = True
    locked.updated_by = actor
    locked.save(update_fields=["is_active", "updated_by", "updated_at"])
    log_activity(actor=actor, operation="warehouse.reactivated", instance=locked)
    return locked


def _lock_stock_item(*, warehouse, product):
    """Take the row lock, creating the row first if this pair is new.

    `get_or_create` can lose the create race; the loser sees the unique
    constraint and simply re-reads the row the winner made.
    """
    item = StockItem.objects.select_for_update().filter(warehouse=warehouse, product=product).first()
    if item is not None:
        return item
    try:
        StockItem.objects.create(warehouse=warehouse, product=product)
    except IntegrityError:
        pass
    return StockItem.objects.select_for_update().get(warehouse=warehouse, product=product)


@transaction.atomic
def record_stock_movement(
    *,
    actor,
    warehouse,
    product,
    movement_type,
    quantity,
    unit_cost=None,
    occurred_at=None,
    reference_kind=StockMovement.ReferenceKind.MANUAL,
    reference_id=None,
    reference_number="",
    idempotency_key="",
    notes="",
    require_manager=True,
):
    """Append one movement and update the derived level under a row lock.

    `require_manager` is False only for internal callers that already proved the
    actor may perform the *business* operation driving the movement (issuing an
    invoice, for example). Role permission is still checked there; it is never
    skipped, only checked once at the right layer.
    """
    actor = _lock_inventory_manager(actor) if require_manager else _lock_active_actor(actor)

    if movement_type not in StockMovement.MovementType.values:
        raise BusinessRuleError({"movement_type": "Unknown movement type."})
    quantity = _clean_quantity(quantity)
    notes = _clean_text(notes, field="notes", limit=MOVEMENT_NOTES_MAX_LENGTH)
    reference_number = _clean_single_line(
        reference_number, field="reference_number", limit=MOVEMENT_REFERENCE_MAX_LENGTH
    )
    idempotency_key = _clean_single_line(
        idempotency_key, field="idempotency_key", limit=IDEMPOTENCY_KEY_MAX_LENGTH
    )
    if reference_kind not in StockMovement.ReferenceKind.values:
        raise BusinessRuleError({"reference_kind": "Unknown reference kind."})
    if reference_kind == StockMovement.ReferenceKind.MANUAL:
        reference_id = None
    elif reference_id is None:
        raise BusinessRuleError({"reference_id": "A referenced movement needs its source id."})

    if idempotency_key:
        existing = StockMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            # A retried request must not apply the same movement twice.
            return existing

    incoming = movement_type in StockMovement.INCOMING
    if movement_type in StockMovement.COST_REQUIRED:
        unit_cost = _clean_money(unit_cost, field="unit_cost")
    elif incoming:
        unit_cost = _clean_money(unit_cost, field="unit_cost", allow_none=True)
    elif unit_cost is not None:
        raise BusinessRuleError({"unit_cost": "An outgoing movement consumes the average cost."})

    occurred_at = occurred_at or timezone.now()

    locked_warehouse = Warehouse.objects.select_for_update().get(pk=warehouse.pk)
    if not locked_warehouse.is_active:
        raise BusinessConflictError({"warehouse": "Warehouse is inactive."})
    locked_product = Product.objects.select_for_update().get(pk=product.pk)
    if not locked_product.is_active and incoming:
        raise BusinessConflictError({"product": "Product is inactive."})

    item = _lock_stock_item(warehouse=locked_warehouse, product=locked_product)
    previous_quantity = item.quantity
    previous_cost = item.average_cost

    if incoming:
        new_quantity = previous_quantity + quantity
        if unit_cost is None:
            # A return arrives at the cost it left at, which is the average in
            # force now. Nothing is invented.
            unit_cost = previous_cost
        if previous_quantity <= 0:
            new_cost = unit_cost
        else:
            total_value = previous_cost * previous_quantity + unit_cost * quantity
            new_cost = (total_value / (previous_quantity + quantity)).quantize(
                MONEY, rounding=ROUND_HALF_UP
            )
    else:
        new_quantity = previous_quantity - quantity
        if new_quantity < 0 and not allow_negative_stock():
            raise BusinessConflictError({
                "quantity": "Not enough stock in this warehouse for the requested quantity."
            })
        new_cost = previous_cost

    if new_quantity > MAX_QUANTITY or new_quantity < -MAX_QUANTITY:
        raise BusinessRuleError({"quantity": "Resulting stock level is out of range."})
    if new_cost > MAX_MONEY:
        raise BusinessRuleError({"unit_cost": "Resulting average cost is too large."})

    try:
        movement = StockMovement.objects.create(
            warehouse=locked_warehouse,
            product=locked_product,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            resulting_quantity=new_quantity,
            resulting_average_cost=new_cost,
            reference_kind=reference_kind,
            reference_id=reference_id,
            reference_number=reference_number,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at,
            created_by=actor,
            notes=notes,
        )
    except IntegrityError as exc:
        raise BusinessConflictError({"idempotency_key": "This movement was already recorded."}) from exc

    item.quantity = new_quantity
    item.average_cost = new_cost
    item.last_movement_at = occurred_at
    item.save(update_fields=["quantity", "average_cost", "last_movement_at", "updated_at"])

    log_activity(
        actor=actor,
        operation="stock_movement.recorded",
        instance=movement,
        changes={
            "warehouse": locked_warehouse.pk,
            "product": locked_product.pk,
            "movement_type": movement_type,
            "quantity": quantity,
            "resulting_quantity": new_quantity,
        },
    )
    return movement


@transaction.atomic
def transfer_stock(*, actor, from_warehouse, to_warehouse, product, quantity, occurred_at=None, notes=""):
    """Move stock between warehouses as two linked movements.

    The outgoing leg runs first so an insufficient level fails before anything
    is created; both legs share one transaction, so a failure leaves neither.
    """
    actor = _lock_inventory_manager(actor)
    if from_warehouse.pk == to_warehouse.pk:
        raise BusinessRuleError({"to_warehouse": "Choose a different destination warehouse."})
    occurred_at = occurred_at or timezone.now()
    outgoing = record_stock_movement(
        actor=actor,
        warehouse=from_warehouse,
        product=product,
        movement_type=StockMovement.MovementType.TRANSFER_OUT,
        quantity=quantity,
        occurred_at=occurred_at,
        reference_kind=StockMovement.ReferenceKind.TRANSFER,
        reference_id=to_warehouse.pk,
        notes=notes,
        require_manager=False,
    )
    incoming = record_stock_movement(
        actor=actor,
        warehouse=to_warehouse,
        product=product,
        movement_type=StockMovement.MovementType.TRANSFER_IN,
        quantity=quantity,
        # The stock keeps the cost it carried in the source warehouse, so a
        # transfer never changes total inventory value.
        unit_cost=outgoing.resulting_average_cost,
        occurred_at=occurred_at,
        reference_kind=StockMovement.ReferenceKind.TRANSFER,
        reference_id=from_warehouse.pk,
        notes=notes,
        require_manager=False,
    )
    return outgoing, incoming


def default_warehouse():
    return Warehouse.objects.filter(is_default=True, is_active=True).first()
