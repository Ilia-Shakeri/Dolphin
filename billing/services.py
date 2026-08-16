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
from sales.selectors import customers_for, leads_for


ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
DOCUMENT_WRITERS = {User.Role.SALES_AGENT, *ELEVATED_OPERATORS}
QUOTATION_HEADER_FIELDS = {"discount_amount", "tax_rate", "valid_until", "notes"}
ORDER_HEADER_FIELDS = {"discount_amount", "tax_rate", "expected_delivery_at", "notes"}
INVOICE_HEADER_FIELDS = {"discount_amount", "tax_rate", "due_at", "notes", "warehouse"}


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
    actor = _lock_document_writer(actor)
    locked = Order.objects.select_for_update().get(pk=order.pk)
    document = _replace_items(
        actor=actor, document=locked, item_model=OrderItem, items=items, relation="order"
    )
    log_activity(
        actor=actor,
        operation="order.items_replaced",
        instance=document,
        changes={"number": document.number, "item_count": len(items), "total_amount": str(document.total_amount)},
    )
    return document


@transaction.atomic
def transition_order(*, actor, order, to_status, reason=""):
    actor = _lock_document_writer(actor)
    locked = Order.objects.select_for_update().get(pk=order.pk)
    _check_transition(locked, to_status)
    if to_status == Order.Status.CONFIRMED and not locked.items.exists():
        raise BusinessConflictError({"items": "An order needs at least one line before it is confirmed."})
    previous = locked.status
    locked.status = to_status
    update_fields = ["status", "updated_at"]
    if to_status == Order.Status.CONFIRMED and locked.confirmed_at is None:
        locked.confirmed_at = timezone.now()
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
        },
    )
    return locked


def _copy_lines(source_items):
    return [
        {
            "product": item.product,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "discount_amount": item.discount_amount,
            "description": item.description,
        }
        for item in source_items
    ]


@transaction.atomic
def convert_quotation_to_order(*, actor, quotation):
    """Copy an accepted quotation into a new draft order.

    A copy, not a conversion: the quotation keeps its own number, status, and
    line snapshot. Nothing about the accepted document is rewritten, so what the
    customer accepted stays readable exactly as accepted.
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
            "order": locked_order,
            "quotation": locked_quotation,
            "sale": sale,
            "warehouse": _resolve_warehouse(header.get("warehouse")),
            "due_at": due_at,
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


@transaction.atomic
def update_invoice(*, actor, invoice, **changes):
    actor = _lock_document_writer(actor)
    locked = Invoice.objects.select_for_update().get(pk=invoice.pk)
    _require_editable(locked)
    unknown = set(changes) - INVOICE_HEADER_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    if "notes" in changes:
        changes["notes"] = _clean_text(changes["notes"], field="notes", limit=FREE_TEXT_MAX_LENGTH)
    if "warehouse" in changes:
        locked.warehouse = _resolve_warehouse(changes["warehouse"])
    header_discount = changes.get("discount_amount", locked.discount_amount)
    tax_rate = changes.get("tax_rate", locked.tax_rate)
    for field in ("due_at", "notes"):
        if field in changes:
            setattr(locked, field, changes[field])
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

    issued_at = timezone.now()
    if locked.warehouse_id is not None and invoice_affects_stock():
        for item in items:
            # Snapshot the cost *before* the issue moves the average, so profit
            # is measured against what the sold units actually cost.
            stock = StockItem.objects.filter(
                warehouse_id=locked.warehouse_id, product_id=item.product_id
            ).first()
            item.unit_cost_snapshot = stock.average_cost if stock is not None else Decimal("0.00")
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
            item.save(update_fields=["unit_cost_snapshot", "updated_at"])
        locked.stock_applied = True

    locked.status = Invoice.Status.ISSUED
    locked.issued_at = issued_at
    locked.save(update_fields=["status", "issued_at", "stock_applied", "updated_at"])

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
    locked.save(update_fields=["status", "cancelled_at", "stock_applied", "updated_at"])

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
