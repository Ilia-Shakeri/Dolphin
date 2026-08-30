"""Quotation, Order, and Invoice services.

Shape shared by all three:

* a document is created `draft` with a number taken from the gap-free counter;
* lines may be replaced only while it is `draft`, and every replacement
  recomputes the four stored header amounts from the lines;
* a status change is checked against that document's declared transition table,
  so an unlisted jump is refused rather than silently applied;
* issuing an Invoice is the only operation with side effects outside billing —
  it deducts stock (when a warehouse is named) and posts to the customer ledger,
  both inside the same transaction as the status change.
"""

import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.access import is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from billing.ledger import append_ledger_entry
from billing.money import (
    clean_money,
    clean_quantity,
    default_tax_rate,
    document_totals,
    line_amounts,
    quantize_money,
)
from billing.models import (
    FREE_TEXT_MAX_LENGTH,
    LINE_DESCRIPTION_MAX_LENGTH,
    CustomerLedgerEntry,
    Invoice,
    InvoiceItem,
    Order,
    OrderItem,
    Quotation,
    QuotationItem,
)
from billing.numbering import next_document_number
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from inventory.models import StockItem, StockMovement, Warehouse
from inventory.services import record_stock_movement
from sales.models import Customer, Lead, Product
from billing.selectors import invoices_for, orders_for
from sales.selectors import customers_for, leads_for


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
DOCUMENT_WRITERS = {User.Role.SALES_AGENT, *ELEVATED_OPERATORS}
QUOTATION_HEADER_FIELDS = {"discount_amount", "tax_rate", "valid_until", "notes"}
#: `warehouse` is here because the order, not the invoice, is what moves stock.
ORDER_HEADER_FIELDS = {"discount_amount", "tax_rate", "expected_delivery_at", "notes", "warehouse", "shipping_method"}
INVOICE_HEADER_FIELDS = {
    "discount_amount", "tax_rate", "due_at", "notes", "warehouse", "invoice_type",
    # The date the operator writes on the document. Not `issued_at`, which is
    # the system's record of issuing and which a draft may not have at all.
    "document_date",
}


def max_document_items():
    return int(getattr(settings, "BILLING_MAX_DOCUMENT_ITEMS", 200))


def _lock_active_actor(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked):
        raise BusinessPermissionDenied("Active user is required.")
    return locked


def _lock_document_writer(actor):
    locked = _lock_active_actor(actor)
    if locked.role not in DOCUMENT_WRITERS:
        raise BusinessPermissionDenied("Commercial document changes are not allowed.")
    if locked.role == User.Role.SALES_AGENT and locked.workstream == User.Workstream.AFTER_SALES:
        raise BusinessPermissionDenied("Commercial document changes are not allowed.")
    return locked


def _lock_billing_manager(actor):
    locked = _lock_active_actor(actor)
    if locked.role not in ELEVATED_OPERATORS:
        raise BusinessPermissionDenied("This billing operation is not allowed.")
    return locked


def _clean_text(value, *, field, limit):
    text = unicodedata.normalize("NFKC", str(value or ""))
    if len(text) > limit:
        raise BusinessRuleError({field: f"Ensure this field has no more than {limit} characters."})
    return text


def _in_scope_customer(actor, customer):
    if not customers_for(actor).filter(pk=customer.pk).exists():
        raise BusinessPermissionDenied("Customer is outside your scope.")
    locked = Customer.objects.select_for_update().get(pk=customer.pk)
    if not locked.is_active:
        raise BusinessConflictError({"customer": "Customer is inactive."})
    return locked


def _in_scope_lead(actor, lead, customer):
    if lead is None:
        return None
    if not leads_for(actor).filter(pk=lead.pk).exists():
        raise BusinessPermissionDenied("Lead is outside your scope.")
    locked = Lead.objects.select_for_update().get(pk=lead.pk)
    if locked.customer_id != customer.pk:
        raise BusinessRuleError({"lead": "Lead must belong to the selected customer."})
    return locked


def _build_lines(items):
    """Validate a whole item list and return prepared line values.

    Prices and product names are snapshotted here, at the moment the line is
    written, so a later catalogue change never rewrites an existing document.
    """
    if not isinstance(items, (list, tuple)):
        raise BusinessRuleError({"items": "Provide a list of document lines."})
    if not items:
        raise BusinessRuleError({"items": "A document needs at least one line."})
    if len(items) > max_document_items():
        raise BusinessRuleError({"items": f"A document may carry at most {max_document_items()} lines."})

    prepared = []
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise BusinessRuleError({"items": "Each document line must be an object."})
        unknown = set(raw) - {
            "product", "quantity", "unit_price", "discount_percent", "discount_amount", "description",
        }
        if unknown:
            raise BusinessRuleError({"items": f"Line {index}: unknown field {sorted(unknown)[0]}."})
        product = raw.get("product")
        if not isinstance(product, Product):
            raise BusinessRuleError({"items": f"Line {index}: a product is required."})
        locked_product = Product.objects.select_for_update().filter(pk=product.pk).first()
        if locked_product is None or not locked_product.is_active:
            raise BusinessRuleError({"items": f"Line {index}: product is inactive."})
        quantity = clean_quantity(raw.get("quantity"), field="items")
        unit_price = raw.get("unit_price")
        unit_price = (
            locked_product.current_price
            if unit_price is None
            else clean_money(unit_price, field="items")
        )
        percent, discount, total = line_amounts(
            quantity=quantity,
            unit_price=unit_price,
            discount_percent=raw.get("discount_percent"),
            discount_amount=raw.get("discount_amount"),
        )
        prepared.append({
            "line_number": index,
            "product": locked_product,
            "product_name_snapshot": locked_product.name,
            "product_sku_snapshot": locked_product.sku,
            "description": _clean_text(
                raw.get("description", ""), field="items", limit=LINE_DESCRIPTION_MAX_LENGTH
            ),
            "quantity": quantity,
            "unit_price": unit_price,
            "discount_percent": percent,
            "discount_amount": discount,
            "line_total": total,
        })
    return prepared


def _apply_totals(document, prepared_lines, *, header_discount, tax_rate):
    subtotal, discount, rate, tax, total = document_totals(
        line_totals=[line["line_total"] for line in prepared_lines],
        header_discount=header_discount,
        tax_rate=tax_rate,
    )
    document.subtotal_amount = subtotal
    document.discount_amount = discount
    document.tax_rate = rate
    document.tax_amount = tax
    document.total_amount = total
    return document


def _require_editable(document):
    if document.status not in document.EDITABLE_STATUSES:
        raise BusinessConflictError({
            "status": "Only a draft document can be changed. Cancel it and issue a new one instead."
        })


def _check_transition(document, to_status):
    if to_status not in type(document).Status.values:
        raise BusinessRuleError({"status": "Unknown status."})
    allowed = document.TRANSITIONS.get(document.status, frozenset())
    if to_status not in allowed:
        raise BusinessConflictError({
            "status": f"A document in '{document.status}' cannot move to '{to_status}'."
        })


def _create_document(*, actor, model, item_model, customer, lead, items, header, extra_fields):
    prepared = _build_lines(items)
    document = model(
        number=next_document_number(model.NUMBER_KIND),
        customer=customer,
        customer_name_snapshot=customer.full_name,
        notes=_clean_text(header.get("notes", ""), field="notes", limit=FREE_TEXT_MAX_LENGTH),
        created_by=actor,
        **extra_fields,
    )
    if lead is not None:
        document.lead = lead
    _apply_totals(
        document,
        prepared,
        header_discount=header.get("discount_amount"),
        tax_rate=header.get("tax_rate") if header.get("tax_rate") is not None else default_tax_rate(),
    )
    try:
        document.save()
    except IntegrityError as exc:
        raise BusinessConflictError({"number": "Document number is already in use."}) from exc
    item_model.objects.bulk_create([
        item_model(**{model.__name__.lower(): document}, **line) for line in prepared
    ])
    return document


def _replace_items(*, actor, document, item_model, items, relation):
    _require_editable(document)
    prepared = _build_lines(items)
    # The old lines are removed and rewritten as one set: a partial update
    # could leave the header totals disagreeing with the lines, and a draft has
    # no external readers that a delete could surprise.
    item_model.objects.filter(**{relation: document}).delete()
    item_model.objects.bulk_create([
        item_model(**{relation: document}, **line) for line in prepared
    ])
    _apply_totals(
        document,
        prepared,
        header_discount=document.discount_amount,
        tax_rate=document.tax_rate,
    )
    document.save(update_fields=[
        "subtotal_amount", "discount_amount", "tax_rate", "tax_amount", "total_amount", "updated_at",
    ])
    return document


def _recompute_from_stored_lines(document, item_model, relation, *, header_discount, tax_rate):
    totals = list(
        item_model.objects.filter(**{relation: document}).values_list("line_total", flat=True)
    )
    if not totals:
        raise BusinessRuleError({"items": "A document needs at least one line."})
    return _apply_totals(
        document,
        [{"line_total": value} for value in totals],
        header_discount=header_discount,
        tax_rate=tax_rate,
    )


# --- Quotation ---------------------------------------------------------------

@transaction.atomic
def create_quotation(*, actor, customer, items, lead=None, **header):
    actor = _lock_document_writer(actor)
    unknown = set(header) - QUOTATION_HEADER_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    locked_customer = _in_scope_customer(actor, customer)
    locked_lead = _in_scope_lead(actor, lead, locked_customer)
    valid_until = header.get("valid_until")
    if valid_until is None:
        valid_until = timezone.now() + timedelta(
            days=int(getattr(settings, "BILLING_QUOTATION_VALID_DAYS", 30))
        )
    quotation = _create_document(
        actor=actor,
        model=Quotation,
        item_model=QuotationItem,
        customer=locked_customer,
        lead=locked_lead,
        items=items,
        header=header,
        extra_fields={"status": Quotation.Status.DRAFT, "valid_until": valid_until},
    )
    log_activity(
        actor=actor,
        operation="quotation.created",
        instance=quotation,
        changes={
            "customer": locked_customer.pk,
            "number": quotation.number,
            "total_amount": str(quotation.total_amount),
            "item_count": len(items),
        },
    )
    return quotation


@transaction.atomic
def update_quotation(*, actor, quotation, **changes):
    actor = _lock_document_writer(actor)
    locked = Quotation.objects.select_for_update().get(pk=quotation.pk)
    _require_editable(locked)
    unknown = set(changes) - QUOTATION_HEADER_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    if "notes" in changes:
        changes["notes"] = _clean_text(changes["notes"], field="notes", limit=FREE_TEXT_MAX_LENGTH)
    header_discount = changes.get("discount_amount", locked.discount_amount)
    tax_rate = changes.get("tax_rate", locked.tax_rate)
    for field in ("valid_until", "notes"):
        if field in changes:
            setattr(locked, field, changes[field])
    _recompute_from_stored_lines(
        locked, QuotationItem, "quotation", header_discount=header_discount, tax_rate=tax_rate
    )
    locked.save()
    log_activity(
        actor=actor,
        operation="quotation.updated",
        instance=locked,
        changes={"number": locked.number, "total_amount": str(locked.total_amount)},
    )
    return locked


@transaction.atomic
def replace_quotation_items(*, actor, quotation, items):
    actor = _lock_document_writer(actor)
    locked = Quotation.objects.select_for_update().get(pk=quotation.pk)
    document = _replace_items(
        actor=actor, document=locked, item_model=QuotationItem, items=items, relation="quotation"
    )
    log_activity(
        actor=actor,
        operation="quotation.items_replaced",
        instance=document,
        changes={"number": document.number, "item_count": len(items), "total_amount": str(document.total_amount)},
    )
    return document


@transaction.atomic
def transition_quotation(*, actor, quotation, to_status, reason=""):
    actor = _lock_document_writer(actor)
    locked = Quotation.objects.select_for_update().get(pk=quotation.pk)
    _check_transition(locked, to_status)
    if to_status == Quotation.Status.SENT and not locked.items.exists():
        raise BusinessConflictError({"items": "A quotation needs at least one line before it is sent."})
    previous = locked.status
    locked.status = to_status
    update_fields = ["status", "updated_at"]
    if to_status == Quotation.Status.SENT and locked.issued_at is None:
        locked.issued_at = timezone.now()
        update_fields.append("issued_at")
    locked.save(update_fields=update_fields)
    log_activity(
        actor=actor,
        operation="quotation.status_changed",
        instance=locked,
        changes={
            "number": locked.number,
            "status_from": previous,
            "status_to": to_status,
            "reason_provided": bool(reason),
        },
    )
    return locked


# --- Order -------------------------------------------------------------------

@transaction.atomic
def create_order(*, actor, customer, items, lead=None, quotation=None, **header):
    actor = _lock_document_writer(actor)
    unknown = set(header) - ORDER_HEADER_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    locked_customer = _in_scope_customer(actor, customer)
    locked_lead = _in_scope_lead(actor, lead, locked_customer)
    locked_quotation = None
    if quotation is not None:
        locked_quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
        if locked_quotation.customer_id != locked_customer.pk:
            raise BusinessRuleError({"quotation": "Quotation must belong to the selected customer."})
    order = _create_document(
        actor=actor,
        model=Order,
        item_model=OrderItem,
        customer=locked_customer,
        lead=locked_lead,
        items=items,
        header=header,
        extra_fields={
            "status": Order.Status.DRAFT,
            "quotation": locked_quotation,
            "expected_delivery_at": header.get("expected_delivery_at"),
            # The order is what moves stock, so it is the order that names the
            # warehouse the goods leave from.
            "warehouse": _resolve_warehouse(header.get("warehouse")),
            "shipping_method": header.get("shipping_method") or "",
        },
    )
    log_activity(
        actor=actor,
        operation="order.created",
        instance=order,
        changes={
            "customer": locked_customer.pk,
            "number": order.number,
            "total_amount": str(order.total_amount),
            "item_count": len(items),
        },
    )
    return order


@transaction.atomic
def update_order(*, actor, order, **changes):
    actor = _lock_document_writer(actor)
    locked = Order.objects.select_for_update().get(pk=order.pk)
    _require_editable(locked)
    unknown = set(changes) - ORDER_HEADER_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    if "notes" in changes:
        changes["notes"] = _clean_text(changes["notes"], field="notes", limit=FREE_TEXT_MAX_LENGTH)
    header_discount = changes.get("discount_amount", locked.discount_amount)
    tax_rate = changes.get("tax_rate", locked.tax_rate)
    for field in ("expected_delivery_at", "notes"):
        if field in changes:
            setattr(locked, field, changes[field])
    _recompute_from_stored_lines(
        locked, OrderItem, "order", header_discount=header_discount, tax_rate=tax_rate
    )
    locked.save()
    log_activity(
        actor=actor,
        operation="order.updated",
        instance=locked,
        changes={"number": locked.number, "total_amount": str(locked.total_amount)},
    )
    return locked


@transaction.atomic
def replace_order_items(*, actor, order, items):
    """Replace an order's lines, reconciling stock when it is already approved.

    A draft order moves nothing. An approved one has already taken its goods out
    of the warehouse, so the edit moves only the difference: extra quantity
    leaves, removed quantity comes back. If the increase cannot be covered the
    order is cancelled with the reason on it rather than approved against stock
    that is not there.
    """
    actor = _lock_document_writer(actor)
    locked = Order.objects.select_for_update().get(pk=order.pk)
    # What the warehouse is holding for this order *before* the edit.
    previous_quantities = _order_quantities(locked) if locked.stock_applied else {}

    document = _replace_items(
        actor=actor, document=locked, item_model=OrderItem, items=items, relation="order"
    )

    if previous_quantities:
        occurred_at = timezone.now()
        reconciled = _reconcile_order_stock(
            actor=actor, order=document, previous=previous_quantities, occurred_at=occurred_at
        )
        if not reconciled:
            return _cancel_for_shortage(actor=actor, order=document, occurred_at=occurred_at)
        document.save(update_fields=["stock_applied", "stock_revision", "updated_at"])

    log_activity(
        actor=actor,
        operation="order.items_replaced",
        instance=document,
        changes={"number": document.number, "item_count": len(items), "total_amount": str(document.total_amount)},
    )
    return document



# --- Order inventory lifecycle ----------------------------------------------
#
# Stock belongs to the order, and only to the order. Goods leave the warehouse
# once when the order is approved and come back once if it is cancelled; an
# approved order that is edited moves only the difference. Invoices never touch
# stock at all, so the same goods can never leave twice for one sale.
#
# "Once" survives retries because every movement carries an idempotency key
# derived from the order and its revision counter, and because `stock_applied`
# records whether the deduction has already happened.

#: Appended to an order's note when the warehouse cannot cover it.
ORDER_SHORTAGE_NOTE = "موجودی کافی نبود"


def _order_quantities(order):
    """What the order asks of the warehouse, per product."""
    quantities = {}
    for item in order.items.all():
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
    return quantities


def _available_quantity(*, warehouse_id, product_id):
    stock = StockItem.objects.filter(warehouse_id=warehouse_id, product_id=product_id).first()
    return stock.quantity if stock is not None else 0


def _shortage_for(*, warehouse_id, required):
    """The first product the warehouse cannot cover, or None.

    Checked before anything is written, so a shortfall never leaves the order
    half-deducted.
    """
    for product_id, quantity in required.items():
        if quantity <= 0:
            continue
        if _available_quantity(warehouse_id=warehouse_id, product_id=product_id) < quantity:
            return product_id
    return None


def _append_order_note(order, sentence):
    """Add a sentence to the order note without losing what is already there."""
    existing = (order.notes or "").strip()
    if sentence in existing:
        return existing
    combined = f"{existing}\n{sentence}".strip() if existing else sentence
    return combined[:FREE_TEXT_MAX_LENGTH]


def _cancel_for_shortage(*, actor, order, occurred_at):
    """Cancel an order the warehouse cannot cover, and say why on the order."""
    order.status = Order.Status.CANCELLED
    order.notes = _append_order_note(order, ORDER_SHORTAGE_NOTE)
    order.save(update_fields=["status", "notes", "updated_at"])
    log_activity(
        actor=actor,
        operation="order.cancelled_for_shortage",
        instance=order,
        changes={"number": order.number, "reason": ORDER_SHORTAGE_NOTE},
    )
    return order


def _move_order_stock(*, actor, order, product_id, quantity, movement_type, occurred_at, key):
    product = Product.objects.get(pk=product_id)
    record_stock_movement(
        actor=actor,
        warehouse=order.warehouse,
        product=product,
        movement_type=movement_type,
        quantity=quantity,
        occurred_at=occurred_at,
        reference_kind=StockMovement.ReferenceKind.ORDER,
        reference_id=order.pk,
        reference_number=order.number,
        idempotency_key=key,
        require_manager=False,
    )


def _apply_order_stock(*, actor, order, occurred_at):
    """Deduct an approved order from stock. Returns False on a shortage.

    Idempotent twice over: it returns immediately when the deduction has already
    been applied, and each movement carries a key derived from the order, so a
    retry that gets past the flag still cannot move the same goods again.
    """
    if order.stock_applied or order.warehouse_id is None:
        return True
    required = _order_quantities(order)
    if _shortage_for(warehouse_id=order.warehouse_id, required=required) is not None:
        return False
    for product_id, quantity in sorted(required.items()):
        _move_order_stock(
            actor=actor,
            order=order,
            product_id=product_id,
            quantity=quantity,
            movement_type=StockMovement.MovementType.SALE,
            occurred_at=occurred_at,
            key=f"order:{order.pk}:approve:{product_id}",
        )
    order.stock_applied = True
    return True


def _release_order_stock(*, actor, order, occurred_at):
    """Give an approved order's goods back, exactly once."""
    if not order.stock_applied or order.warehouse_id is None:
        return
    for product_id, quantity in sorted(_order_quantities(order).items()):
        _move_order_stock(
            actor=actor,
            order=order,
            product_id=product_id,
            quantity=quantity,
            movement_type=StockMovement.MovementType.RETURN_IN,
            occurred_at=occurred_at,
            key=f"order:{order.pk}:release:{order.stock_revision}:{product_id}",
        )
    order.stock_applied = False


def _reconcile_order_stock(*, actor, order, previous, occurred_at):
    """Move only the difference after an approved order is edited.

    `previous` is what the order asked for before the edit. Anything now asked
    for beyond that is deducted; anything no longer asked for is returned. A
    shortfall on the increase leaves the whole edit unapplied, and the caller
    cancels the order.
    """
    if not order.stock_applied or order.warehouse_id is None:
        return True
    current = _order_quantities(order)
    increases = {}
    decreases = {}
    for product_id in set(previous) | set(current):
        delta = current.get(product_id, 0) - previous.get(product_id, 0)
        if delta > 0:
            increases[product_id] = delta
        elif delta < 0:
            decreases[product_id] = -delta
    if not increases and not decreases:
        return True
    if _shortage_for(warehouse_id=order.warehouse_id, required=increases) is not None:
        return False

    revision = order.stock_revision + 1
    for product_id, quantity in sorted(decreases.items()):
        _move_order_stock(
            actor=actor,
            order=order,
            product_id=product_id,
            quantity=quantity,
            movement_type=StockMovement.MovementType.RETURN_IN,
            occurred_at=occurred_at,
            key=f"order:{order.pk}:reconcile:{revision}:in:{product_id}",
        )
    for product_id, quantity in sorted(increases.items()):
        _move_order_stock(
            actor=actor,
            order=order,
            product_id=product_id,
            quantity=quantity,
            movement_type=StockMovement.MovementType.SALE,
            occurred_at=occurred_at,
            key=f"order:{order.pk}:reconcile:{revision}:out:{product_id}",
        )
    order.stock_revision = revision
    return True


@transaction.atomic
def transition_order(*, actor, order, to_status, reason=""):
    actor = _lock_document_writer(actor)
    locked = Order.objects.select_for_update().get(pk=order.pk)
    _check_transition(locked, to_status)
    if to_status == Order.Status.CONFIRMED and not locked.items.exists():
        raise BusinessConflictError({"items": "An order needs at least one line before it is confirmed."})
    previous = locked.status
    occurred_at = timezone.now()

    # Approval is what moves goods. If the warehouse cannot cover the order it
    # is cancelled with the reason on it, rather than approved against stock
    # that does not exist.
    if to_status == Order.Status.CONFIRMED:
        if not _apply_order_stock(actor=actor, order=locked, occurred_at=occurred_at):
            return _cancel_for_shortage(actor=actor, order=locked, occurred_at=occurred_at)

    # Cancelling an approved order gives the goods back, once.
    if to_status == Order.Status.CANCELLED and previous in {
        Order.Status.CONFIRMED, Order.Status.FULFILLED
    }:
        _release_order_stock(actor=actor, order=locked, occurred_at=occurred_at)

    locked.status = to_status
    update_fields = ["status", "stock_applied", "stock_revision", "updated_at"]
    if to_status == Order.Status.CONFIRMED and locked.confirmed_at is None:
        locked.confirmed_at = occurred_at
        update_fields.append("confirmed_at")
    locked.save(update_fields=update_fields)
    log_activity(
        actor=actor,
        operation="order.status_changed",
        instance=locked,
        changes={
            "number": locked.number,
            "status_from": previous,
            "status_to": to_status,
            "reason_provided": bool(reason),
            "stock_applied": locked.stock_applied,
        },
    )
    return locked


def _copy_lines(source_items):
    """Reproduce stored lines as line input for a new document.

    A line's discount is carried across in the form it was given. Copying a
    percentage line as a bare amount produced identical money on a document that
    then read "0%" — the totals agreed, but what the customer accepted was no
    longer legible as accepted. `line_amounts` refuses both forms at once, so
    exactly one is sent.
    """
    lines = []
    for item in source_items:
        line = {
            "product": item.product,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "description": item.description,
        }
        if item.discount_percent:
            line["discount_percent"] = item.discount_percent
        else:
            line["discount_amount"] = item.discount_amount
        lines.append(line)
    return lines


@transaction.atomic
def convert_quotation_to_order(*, actor, quotation, warehouse=None):
    """Copy an accepted quotation into a new draft order.

    A copy, not a conversion: the quotation keeps its own number, status, and
    line snapshot. Nothing about the accepted document is rewritten, so what the
    customer accepted stays readable exactly as accepted.

    `warehouse` names where the goods will leave from when the order is
    approved. A quotation has no warehouse of its own, so it has to be supplied
    here or the resulting order has no stock effect.
    """
    actor = _lock_document_writer(actor)
    locked = Quotation.objects.select_for_update().get(pk=quotation.pk)
    if locked.status != Quotation.Status.ACCEPTED:
        raise BusinessConflictError({"status": "Only an accepted quotation can become an order."})
    if locked.orders.exclude(status=Order.Status.CANCELLED).exists():
        raise BusinessConflictError({"quotation": "This quotation already has an order."})
    items = _copy_lines(locked.items.select_related("product").all())
    order = create_order(
        actor=actor,
        customer=locked.customer,
        items=items,
        lead=locked.lead,
        quotation=locked,
        discount_amount=locked.discount_amount,
        tax_rate=locked.tax_rate,
        notes=locked.notes,
        warehouse=warehouse,
    )
    return order


# --- Invoice -----------------------------------------------------------------

def _resolve_warehouse(warehouse):
    if warehouse is None:
        return None
    locked = Warehouse.objects.select_for_update().get(pk=warehouse.pk)
    if not locked.is_active:
        raise BusinessConflictError({"warehouse": "Warehouse is inactive."})
    return locked


@transaction.atomic
def create_invoice(*, actor, customer, items, order=None, quotation=None, sale=None, **header):
    actor = _lock_document_writer(actor)
    unknown = set(header) - INVOICE_HEADER_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    locked_customer = _in_scope_customer(actor, customer)
    locked_order = None
    if order is not None:
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.customer_id != locked_customer.pk:
            raise BusinessRuleError({"order": "Order must belong to the selected customer."})
    locked_quotation = None
    if quotation is not None:
        locked_quotation = Quotation.objects.select_for_update().get(pk=quotation.pk)
        if locked_quotation.customer_id != locked_customer.pk:
            raise BusinessRuleError({"quotation": "Quotation must belong to the selected customer."})
    if sale is not None and sale.customer_id != locked_customer.pk:
        raise BusinessRuleError({"sale": "Sale must belong to the selected customer."})

    invoice_type = header.get("invoice_type")
    if invoice_type is not None and invoice_type not in Invoice.InvoiceType.values:
        # Checked here as well as by the serializer, because the service is the
        # boundary a script or a management command also comes through, and the
        # database constraint would report this as something else entirely.
        raise BusinessRuleError({"invoice_type": "Select an invoice type from the list."})

    due_at = header.get("due_at")
    if due_at is None:
        due_days = int(getattr(settings, "BILLING_INVOICE_DUE_DAYS", 0))
        due_at = timezone.now() + timedelta(days=due_days) if due_days else None

    invoice = _create_document(
        actor=actor,
        model=Invoice,
        item_model=InvoiceItem,
        customer=locked_customer,
        lead=None,
        items=items,
        header=header,
        extra_fields={
            "status": Invoice.Status.DRAFT,
            # `_create_document` reads only the header fields it names, so this
            # has to travel here rather than in `header` - accepting the value
            # and then not writing it is worse than refusing it.
            "invoice_type": invoice_type or Invoice.InvoiceType.UNOFFICIAL,
            "order": locked_order,
            "quotation": locked_quotation,
            "sale": sale,
            "warehouse": _resolve_warehouse(header.get("warehouse")),
            "due_at": due_at,
            # Same reason as `invoice_type` above: `_create_document` writes only
            # the fields named here, so accepting the value and then not storing
            # it would be worse than refusing it.
            "document_date": header.get("document_date"),
        },
    )
    log_activity(
        actor=actor,
        operation="invoice.created",
        instance=invoice,
        changes={
            "customer": locked_customer.pk,
            "number": invoice.number,
            "total_amount": str(invoice.total_amount),
            "item_count": len(items),
        },
    )
    return invoice


#: The one field an operator may still correct once an invoice is issued.
#:
#: Everything else on the header either moves money (`discount_amount`,
#: `tax_rate`, `document_date` feeding the tax point) or changes the document's
#: legal shape (`invoice_type`, `warehouse`) — an issued invoice is a snapshot
#: a customer has already been given, and none of that may drift under them.
#: `notes` is free text with no accounting weight, which is what makes it the
#: one thing worth reopening rather than requiring a cancel-and-reissue for a
#: typo.
INVOICE_ISSUED_EDITABLE_FIELDS = frozenset({"notes"})


@transaction.atomic
def update_invoice(*, actor, invoice, **changes):
    actor = _lock_document_writer(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    unknown = set(changes) - INVOICE_HEADER_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})

    if locked.status == Invoice.Status.ISSUED:
        # Narrower than `_require_editable`, and deliberately not that helper:
        # a draft may change anything in `INVOICE_HEADER_FIELDS`, but an issued
        # invoice may change only `notes`. Widening `_require_editable` itself
        # would also loosen Quotation and Order, which is not what was asked.
        blocked = set(changes) - INVOICE_ISSUED_EDITABLE_FIELDS
        if blocked:
            raise BusinessConflictError({
                field: "Only notes can be changed on an issued invoice." for field in sorted(blocked)
            })
    else:
        _require_editable(locked)

    if "notes" in changes:
        changes["notes"] = _clean_text(changes["notes"], field="notes", limit=FREE_TEXT_MAX_LENGTH)
    if "warehouse" in changes:
        locked.warehouse = _resolve_warehouse(changes["warehouse"])
    for field in ("due_at", "notes", "document_date"):
        if field in changes:
            setattr(locked, field, changes[field])
    if locked.status == Invoice.Status.ISSUED:
        # Nothing here can change subtotal, discount or tax — `notes` is the
        # only field this branch reaches — so the totals stay exactly the
        # snapshot `issue_invoice` fixed. Recomputing would be a needless
        # touch of frozen money fields for a change that is not about money.
        locked.save(update_fields=["notes", "updated_at"])
    else:
        header_discount = changes.get("discount_amount", locked.discount_amount)
        tax_rate = changes.get("tax_rate", locked.tax_rate)
        _recompute_from_stored_lines(
            locked, InvoiceItem, "invoice", header_discount=header_discount, tax_rate=tax_rate
        )
        locked.save()
    log_activity(
        actor=actor,
        operation="invoice.updated",
        instance=locked,
        changes={"number": locked.number, "total_amount": str(locked.total_amount)},
    )
    return locked


@transaction.atomic
def replace_invoice_items(*, actor, invoice, items):
    actor = _lock_document_writer(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    document = _replace_items(
        actor=actor, document=locked, item_model=InvoiceItem, items=items, relation="invoice"
    )
    log_activity(
        actor=actor,
        operation="invoice.items_replaced",
        instance=document,
        changes={"number": document.number, "item_count": len(items), "total_amount": str(document.total_amount)},
    )
    return document


def invoice_affects_stock():
    return bool(getattr(settings, "BILLING_INVOICE_AFFECTS_STOCK", True))


@transaction.atomic
def official_invoice_identity_errors(invoice):
    """What an official invoice is still missing, as {field: message}.

    Checked at issue rather than at draft, so an operator can build the document
    first and complete the identities before making it final — the same shape as
    the "needs at least one line" rule beside it.

    Three identifiers, and which ones apply depends on who the buyer is. Iran
    gives a natural person a کد ملی and an organisation a شناسه ملی plus a
    separate شماره اقتصادی, so a legal-entity buyer needs both columns filled
    and a natural person needs one. `Customer.kind` already records which it is.

    This is a completeness check on fields, and deliberately nothing more. It
    does not validate a check digit, does not compute tax, and does not touch
    numbering — D.3 through D.7 remain open and are not guessed at here.
    """
    errors = {}

    if not settings.SELLER_LEGAL_NAME:
        errors["seller_legal_name"] = (
            "This deployment has no seller name configured, so it cannot issue an "
            "official invoice. Set KARIZ_SELLER_LEGAL_NAME."
        )
    if not settings.SELLER_NATIONAL_ID:
        errors["seller_national_id"] = (
            "This deployment has no seller national id configured. Set "
            "KARIZ_SELLER_NATIONAL_ID."
        )
    if not settings.SELLER_ECONOMIC_CODE:
        errors["seller_economic_code"] = (
            "This deployment has no seller economic code configured. Set "
            "KARIZ_SELLER_ECONOMIC_CODE."
        )

    customer = invoice.customer
    if not (customer.national_id or "").strip():
        errors["customer_national_id"] = (
            "An official invoice needs the buyer's national id."
        )
    if customer.kind == Customer.Kind.LEGAL and not (customer.economic_code or "").strip():
        errors["customer_economic_code"] = (
            "A legal-entity buyer needs an economic code on an official invoice."
        )
    return errors


#: The columns `_snapshot_parties` writes. Named once so the `save()` beside it
#: cannot fall out of step with the assignments above it.
PARTY_SNAPSHOT_FIELDS = (
    "buyer_name", "buyer_national_id", "buyer_economic_code", "buyer_address",
    "buyer_postal_code", "buyer_city", "buyer_phone",
    "seller_name", "seller_registration_number", "seller_national_id",
    "seller_economic_code", "seller_address", "seller_postal_code",
    "seller_city", "seller_phone",
)


def _snapshot_parties(invoice):
    """Copy both parties onto the invoice, in place. Caller saves.

    Every value comes from the `Customer` row or from deployment settings.
    Nothing here reads operator input, and that is the point: the product
    owner's rule is that an address on an invoice is **selected from the
    customer's file and never typed by hand**, so the only way to change what
    an invoice will say is to correct the customer first and then issue.

    Taken for every invoice, not only official ones. An unofficial invoice is
    printed and handed over too, and there is no reason for its copy to drift
    afterwards while the official one holds still.
    """
    customer = invoice.customer
    # The primary active number, matching what the customer screen shows as the
    # main line. `.first()` on the model's own ordering puts primary first.
    phone = customer.phones.filter(is_active=True).order_by("-is_primary", "id").first()

    invoice.buyer_name = (customer.full_name or "").strip()[:255]
    invoice.buyer_national_id = (customer.national_id or "").strip()[:32]
    invoice.buyer_economic_code = (customer.economic_code or "").strip()[:32]
    invoice.buyer_address = (customer.address or "").strip()[:500]
    invoice.buyer_postal_code = (customer.postal_code or "").strip()[:32]
    invoice.buyer_city = (customer.city or "").strip()[:100]
    invoice.buyer_phone = (phone.raw_phone if phone else "").strip()[:40]

    invoice.seller_name = settings.SELLER_LEGAL_NAME[:255]
    invoice.seller_registration_number = settings.SELLER_REGISTRATION_NUMBER[:32]
    invoice.seller_national_id = settings.SELLER_NATIONAL_ID[:32]
    invoice.seller_economic_code = settings.SELLER_ECONOMIC_CODE[:32]
    invoice.seller_address = settings.SELLER_ADDRESS[:500]
    invoice.seller_postal_code = settings.SELLER_POSTAL_CODE[:32]
    invoice.seller_city = settings.SELLER_CITY[:100]
    invoice.seller_phone = settings.SELLER_PHONE[:40]


@transaction.atomic
def reissue_invoice(*, actor, invoice, reason=""):
    """Cancel an invoice and raise a fresh draft with the same lines. (بند ۸.۲)

    The product owner's answer to "how is an issued invoice corrected" was
    neither editing it nor a credit note: **cancel it and issue a new one**,
    with the reason recorded in the notes.

    So this is exactly those two steps in one transaction, and deliberately
    nothing more:

    * The old document is cancelled through `cancel_invoice`, which reverses its
      stock and its ledger entry and writes the reason into its notes. Every
      rule there still applies — in particular, an invoice with money allocated
      to it is refused until those allocations are released.
    * A **draft** is created with the same lines and header. A draft, not an
      issued invoice: the replacement usually differs from the original in the
      way that caused the reissue, and the operator has to be able to correct it
      before it becomes a document. Issuing it is the ordinary separate step,
      and that is also what takes the next official number.

    The new invoice carries no allocation, no payment and no number from the
    old one. It points back to it in its notes, which is the only link that
    survives printing.
    """
    actor = _lock_billing_manager(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != Invoice.Status.ISSUED:
        raise BusinessConflictError({
            "status": "Only an issued invoice can be reissued."
        })

    items = list(locked.items.select_related("product").order_by("line_number"))
    original_number = locked.number
    header_notes = locked.notes
    replacement_items = [
        {
            "product": item.product,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "discount_amount": item.discount_amount,
            "description": item.description,
        }
        for item in items
    ]

    cancel_invoice(actor=actor, invoice=locked, reason=reason)

    trail = f"[صادرشده به‌جای {original_number}]"
    replacement = create_invoice(
        actor=actor,
        customer=locked.customer,
        warehouse=locked.warehouse,
        items=replacement_items,
        discount_amount=locked.discount_amount,
        tax_rate=locked.tax_rate,
        due_at=locked.due_at,
        invoice_type=locked.invoice_type,
        notes=f"{header_notes}\n{trail}".strip() if header_notes else trail,
    )

    log_activity(
        actor=actor,
        operation="invoice.reissued",
        instance=replacement,
        changes={
            "replaces": locked.pk,
            "replaces_number": original_number,
            "reason_provided": bool(reason),
        },
    )
    return replacement


@transaction.atomic
def issue_invoice(*, actor, invoice):
    """Make an invoice final: snapshot cost, deduct stock, post to the ledger.

    All three effects share this transaction with the status change, so an
    invoice can never be issued without its ledger entry, and a stock shortfall
    aborts the issue rather than producing a document the warehouse cannot back.
    """
    actor = _lock_billing_manager(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    _check_transition(locked, Invoice.Status.ISSUED)
    items = list(locked.items.select_related("product").order_by("line_number"))
    if not items:
        raise BusinessConflictError({"items": "An invoice needs at least one line before it is issued."})

    # An official invoice is a tax document, so it is refused rather than issued
    # incomplete. An unofficial one is unaffected and none of this runs for it.
    if locked.invoice_type == Invoice.InvoiceType.OFFICIAL:
        missing = official_invoice_identity_errors(locked)
        if missing:
            raise BusinessRuleError(missing)
        # The official number is taken here and nowhere else: this is the moment
        # the document becomes a tax document, and a series that must be gapless
        # cannot afford a number spent on a draft that is never issued.
        #
        # Guarded so a re-issue could never take a second one, even though the
        # status graph does not currently allow issuing twice.
        if not locked.official_number:
            locked.official_number = next_document_number("official_invoice")

    # Both parties are frozen here, in the same transaction as the status
    # change, so an issued invoice can never exist without its snapshot.
    _snapshot_parties(locked)

    issued_at = timezone.now()
    # An invoice that never had a stated document date gets the day it was
    # issued, so the column reading this is never blank for an issued document.
    # A date the operator did state is left exactly as they wrote it.
    if locked.document_date is None:
        locked.document_date = timezone.localdate(issued_at)
    # The cost snapshot and the stock movement are two separate things.
    #
    # The snapshot is a *read* of what the units cost, and gross profit is
    # measured against it, so it is taken whenever the invoice names a warehouse
    # — including in Client-1, where the invoice moves no goods at all because
    # the order already did. Without this, turning off the stock effect would
    # silently empty the profit report.
    if locked.warehouse_id is not None:
        for item in items:
            stock = StockItem.objects.filter(
                warehouse_id=locked.warehouse_id, product_id=item.product_id
            ).first()
            item.unit_cost_snapshot = stock.average_cost if stock is not None else Decimal("0.00")
            item.save(update_fields=["unit_cost_snapshot", "updated_at"])

    if locked.warehouse_id is not None and invoice_affects_stock():
        for item in items:
            record_stock_movement(
                actor=actor,
                warehouse=locked.warehouse,
                product=item.product,
                movement_type=StockMovement.MovementType.SALE,
                quantity=item.quantity,
                occurred_at=issued_at,
                reference_kind=StockMovement.ReferenceKind.INVOICE,
                reference_id=locked.pk,
                reference_number=locked.number,
                idempotency_key=f"invoice:{locked.pk}:issue:{item.pk}",
                require_manager=False,
            )
        locked.stock_applied = True

    locked.status = Invoice.Status.ISSUED
    locked.issued_at = issued_at
    # `official_number` is in the same write as the status, so an invoice can
    # never be issued without its number, nor hold a number without being issued.
    locked.save(update_fields=[
        "status", "issued_at", "document_date", "stock_applied", "official_number",
        "updated_at",
        *PARTY_SNAPSHOT_FIELDS,
    ])

    append_ledger_entry(
        actor=actor,
        customer=locked.customer,
        entry_type=CustomerLedgerEntry.EntryType.INVOICE_ISSUED,
        debit=locked.total_amount,
        occurred_at=issued_at,
        reference_kind=CustomerLedgerEntry.ReferenceKind.INVOICE,
        reference_id=locked.pk,
        reference_number=locked.number,
    )
    log_activity(
        actor=actor,
        operation="invoice.issued",
        instance=locked,
        changes={
            "number": locked.number,
            "total_amount": str(locked.total_amount),
            "status_from": Invoice.Status.DRAFT,
            "status_to": Invoice.Status.ISSUED,
        },
    )
    return locked


@transaction.atomic
def cancel_invoice(*, actor, invoice, reason=""):
    """Cancel an invoice, reversing its stock and ledger effects.

    An issued invoice with money already applied is refused: releasing an
    allocation is a separate, explicit decision, and cancelling underneath it
    would leave a payment pointing at a document that no longer owes anything.
    """
    actor = _lock_billing_manager(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    _check_transition(locked, Invoice.Status.CANCELLED)
    if locked.paid_amount > 0:
        raise BusinessConflictError({
            "paid_amount": "Release the payments allocated to this invoice before cancelling it."
        })
    cancelled_at = timezone.now()
    was_issued = locked.status == Invoice.Status.ISSUED

    if locked.stock_applied:
        for item in locked.items.select_related("product").order_by("line_number"):
            record_stock_movement(
                actor=actor,
                warehouse=locked.warehouse,
                product=item.product,
                movement_type=StockMovement.MovementType.RETURN_IN,
                quantity=item.quantity,
                unit_cost=item.unit_cost_snapshot,
                occurred_at=cancelled_at,
                reference_kind=StockMovement.ReferenceKind.INVOICE,
                reference_id=locked.pk,
                reference_number=locked.number,
                idempotency_key=f"invoice:{locked.pk}:cancel:{item.pk}",
                require_manager=False,
            )
        locked.stock_applied = False

    locked.status = Invoice.Status.CANCELLED
    locked.cancelled_at = cancelled_at
    # بند ۸.۲ — «دلیل ابطال هم در توضیحات فاکتور نوشته بشه».
    #
    # Appended rather than assigned: whatever the operator wrote when raising
    # the invoice is still true and is not overwritten by the reason it was
    # later cancelled for. The audit log records the same reason, but the audit
    # log is not what gets printed and handed to anyone — the notes are.
    if reason:
        stamp = f"[ابطال] {reason}"
        locked.notes = f"{locked.notes}\n{stamp}".strip() if locked.notes else stamp
        locked.notes = locked.notes[:FREE_TEXT_MAX_LENGTH]
    locked.save(
        update_fields=["status", "cancelled_at", "stock_applied", "notes", "updated_at"]
    )

    if was_issued:
        append_ledger_entry(
            actor=actor,
            customer=locked.customer,
            entry_type=CustomerLedgerEntry.EntryType.INVOICE_CANCELLED,
            credit=locked.total_amount,
            occurred_at=cancelled_at,
            reference_kind=CustomerLedgerEntry.ReferenceKind.INVOICE,
            reference_id=locked.pk,
            reference_number=locked.number,
        )
    log_activity(
        actor=actor,
        operation="invoice.cancelled",
        instance=locked,
        changes={
            "number": locked.number,
            "total_amount": str(locked.total_amount),
            "status_to": Invoice.Status.CANCELLED,
            "reason_provided": bool(reason),
        },
    )
    return locked


@transaction.atomic
def convert_order_to_invoice(*, actor, order, warehouse=None):
    """Copy a confirmed order into a new draft invoice."""
    actor = _lock_document_writer(actor)
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.status not in {Order.Status.CONFIRMED, Order.Status.FULFILLED}:
        raise BusinessConflictError({"status": "Only a confirmed order can become an invoice."})
    if locked.invoices.exclude(status=Invoice.Status.CANCELLED).exists():
        raise BusinessConflictError({"order": "This order already has an invoice."})
    items = _copy_lines(locked.items.select_related("product").all())
    return create_invoice(
        actor=actor,
        customer=locked.customer,
        items=items,
        order=locked,
        quotation=locked.quotation,
        discount_amount=locked.discount_amount,
        tax_rate=locked.tax_rate,
        notes=locked.notes,
        warehouse=warehouse,
    )


def invoice_profit(invoice):
    """Gross profit of one issued invoice, or None when cost is unknown.

    Returns None rather than zero when any line lacks a cost snapshot: a
    missing cost is not a zero cost, and reporting it as one would overstate
    profit. The report shows such invoices as unmeasured instead.
    """
    revenue = Decimal("0.00")
    cost = Decimal("0.00")
    for item in invoice.items.all():
        if item.unit_cost_snapshot is None:
            return None
        revenue += item.line_total
        cost += item.unit_cost_snapshot * item.quantity
    return quantize_money(revenue) - quantize_money(cost)

@transaction.atomic
def record_manual_paid_entry(*, actor, invoice, amount):
    """Record the operator's typed "پرداخت شده" figure for one invoice.

    This is deliberately **not** an accounting operation. It writes no Payment,
    no PaymentAllocation and no ledger entry, and it never touches
    `paid_amount`, the customer balance, receivables reporting or stock. Those
    records keep meaning exactly what they meant before, which is what lets the
    ledger stay true while the invoice screen shows what Client-1 asked for.

    One rule gives the typed number any effect: when it matches the amount the
    payment records still show outstanding, the invoice is marked settled. That
    mark is one-way. Retyping a smaller number afterwards updates what is shown
    in the box and leaves the settlement alone — an invoice that has been
    declared paid does not become unpaid because somebody edited a field.

    A real receipt feature will replace this; until then the whole override
    lives in three columns on Invoice and can be dropped without unwinding
    anything else.
    """
    actor = _lock_billing_manager(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if not invoices_for(actor).filter(pk=locked.pk).exists():
        raise BusinessPermissionDenied("Invoice is outside your scope.")
    entry = clean_money(amount, field="manual_paid_entry")
    if entry > locked.total_amount:
        raise BusinessRuleError(
            {"manual_paid_entry": "Paid amount cannot exceed the invoice total."}
        )

    outstanding_before = locked.canonical_balance_due
    already_settled = locked.is_manually_settled
    fields = ["manual_paid_entry", "updated_at"]
    locked.manual_paid_entry = entry

    # The transition fires only on an exact match, and only once. `> 0` keeps a
    # fully-allocated invoice from being "settled again" by typing zero.
    settles_now = not already_settled and outstanding_before > 0 and entry == outstanding_before
    if settles_now:
        locked.manual_settled_at = timezone.now()
        locked.manual_settled_by = actor
        fields.extend(["manual_settled_at", "manual_settled_by"])

    locked.save(update_fields=fields)
    log_activity(
        actor=actor,
        operation="invoice.manual_paid_entry",
        instance=locked,
        changes={
            "entry": str(entry),
            "outstanding_before": str(outstanding_before),
            "settled_now": settles_now,
            "already_settled": already_settled,
        },
    )
    return locked


@transaction.atomic
def link_invoice_to_order(*, actor, invoice, order):
    """Attach an existing invoice to an existing order, or detach it.

    Client-1 raises the invoice first and the order afterwards, so the two
    documents normally exist before anyone knows they belong together. This is
    the operation that says so, and it takes a real foreign key rather than
    matching document numbers as text — numbers are display strings, and two
    deployments could reuse one.

    Passing `order=None` detaches. Both documents must be in the caller's scope
    and belong to the same customer; nothing about either document's money,
    status or stock changes here.
    """
    actor = _lock_document_writer(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    if not invoices_for(actor).filter(pk=locked.pk).exists():
        raise BusinessPermissionDenied("Invoice is outside your scope.")

    locked_order = None
    if order is not None:
        if not orders_for(actor).filter(pk=order.pk).exists():
            raise BusinessPermissionDenied("Order is outside your scope.")
        locked_order = Order.objects.select_for_update().get(pk=order.pk)
        if locked_order.customer_id != locked.customer_id:
            raise BusinessRuleError(
                {"order": "Order and invoice must belong to the same customer."}
            )

    previous = locked.order_id
    if previous == (locked_order.pk if locked_order else None):
        return locked
    locked.order = locked_order
    locked.save(update_fields=["order", "updated_at"])
    log_activity(
        actor=actor,
        operation="invoice.order_linked",
        instance=locked,
        changes={
            "number": locked.number,
            "order_from": previous,
            "order_to": locked_order.pk if locked_order else None,
        },
    )
    return locked
