"""Warehouses, per-warehouse stock, and the append-only stock movement ledger.

Bounded semantics recorded here because no external contract fixed them
(`docs/backend/INVENTORY_SEMANTICS.md` holds the full statement):

* **Quantities are whole units.** `sales.Sale.quantity` is already a positive
  integer, so a fractional unit could never be sold through the existing path.
  A future deployment that needs fractions changes the column, not the meaning.
* **Cost is a moving weighted average**, recomputed on every incoming movement
  and snapshotted on the movement row. Outgoing movements consume the average
  in force at that moment and never change it.
* **Negative stock is refused** unless `INVENTORY_ALLOW_NEGATIVE_STOCK` is on.
* **A movement is never edited or deleted.** A mistake is corrected by a
  compensating movement, so the ledger always reconstructs the current level.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


WAREHOUSE_CODE_MAX_LENGTH = 64
WAREHOUSE_NAME_MAX_LENGTH = 120
WAREHOUSE_ADDRESS_MAX_LENGTH = 2000
MOVEMENT_NOTES_MAX_LENGTH = 2000
MOVEMENT_REFERENCE_MAX_LENGTH = 64
IDEMPOTENCY_KEY_MAX_LENGTH = 64
MAX_MONEY = Decimal("9999999999999999.99")
MAX_QUANTITY = 1_000_000_000


class Warehouse(TimeStampedModel):
    code = models.CharField(max_length=WAREHOUSE_CODE_MAX_LENGTH, unique=True)
    name = models.CharField(max_length=WAREHOUSE_NAME_MAX_LENGTH)
    normalized_name = models.CharField(
        max_length=WAREHOUSE_NAME_MAX_LENGTH, unique=True, editable=False
    )
    address = models.CharField(max_length=WAREHOUSE_ADDRESS_MAX_LENGTH, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_warehouses"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_warehouses"
    )

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(code__regex=r"\A[a-z0-9][a-z0-9_-]{0,63}\Z"),
                name="warehouse_code_shape",
            ),
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="warehouse_name_nonblank"),
            models.CheckConstraint(
                condition=Q(normalized_name__regex=r"\S"),
                name="warehouse_normalized_name_nonblank",
            ),
            # At most one default warehouse, and only an active one may hold the
            # flag, so "the default" is never a deactivated row.
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="uniq_single_default_warehouse",
            ),
            models.CheckConstraint(
                condition=Q(is_default=False) | Q(is_active=True),
                name="warehouse_default_is_active",
            ),
        ]

    def __str__(self):
        return self.name


class StockItem(TimeStampedModel):
    """The current level and average cost of one product in one warehouse.

    Derived state: every field here is reproducible from `StockMovement`. It
    exists so a stock read is one indexed row rather than an aggregate over the
    whole ledger, and it is only ever written inside the movement service under
    `select_for_update`.
    """

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="stock_items")
    product = models.ForeignKey(
        "sales.Product", on_delete=models.PROTECT, related_name="stock_items"
    )
    quantity = models.IntegerField(default=0)
    average_cost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    last_movement_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["warehouse_id", "product_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["warehouse", "product"], name="uniq_stock_item_warehouse_product"
            ),
            models.CheckConstraint(
                condition=Q(average_cost__gte=0), name="stock_item_average_cost_non_negative"
            ),
        ]
        indexes = [
            models.Index(fields=["product", "warehouse"]),
            models.Index(fields=["warehouse", "quantity"]),
        ]

    @property
    def stock_value(self):
        return (self.average_cost * self.quantity).quantize(Decimal("0.01"))


class StockMovement(TimeStampedModel):
    """One append-only entry in the stock ledger.

    `quantity` is always positive; the direction comes from `movement_type`.
    `resulting_quantity` and `resulting_average_cost` snapshot the stock item
    immediately after this movement was applied, so a historical level never
    depends on replaying arithmetic.

    The link back to a billing document is a soft reference
    (`reference_kind` + `reference_id`) rather than a foreign key. Inventory
    must stay usable in a deployment whose manifest does not enable billing at
    all, and a hard FK would make the two features inseparable.
    """

    class MovementType(models.TextChoices):
        OPENING = "opening", "Opening stock"
        PURCHASE = "purchase", "Purchase receipt"
        SALE = "sale", "Sale issue"
        RETURN_IN = "return_in", "Customer return"
        RETURN_OUT = "return_out", "Return to supplier"
        ADJUSTMENT_IN = "adjustment_in", "Adjustment increase"
        ADJUSTMENT_OUT = "adjustment_out", "Adjustment decrease"
        TRANSFER_IN = "transfer_in", "Transfer in"
        TRANSFER_OUT = "transfer_out", "Transfer out"

    class ReferenceKind(models.TextChoices):
        MANUAL = "manual", "Manual entry"
        INVOICE = "invoice", "Invoice"
        ORDER = "order", "Order"
        TRANSFER = "transfer", "Warehouse transfer"

    INCOMING = frozenset({
        MovementType.OPENING,
        MovementType.PURCHASE,
        MovementType.RETURN_IN,
        MovementType.ADJUSTMENT_IN,
        MovementType.TRANSFER_IN,
    })
    OUTGOING = frozenset({
        MovementType.SALE,
        MovementType.RETURN_OUT,
        MovementType.ADJUSTMENT_OUT,
        MovementType.TRANSFER_OUT,
    })
    #: The kinds a person may record by hand. Every other kind exists because
    #: some other operation produces it — a transfer moves stock between
    #: warehouses, an order issues it — and letting an operator type one of
    #: those directly would create inventory history that no document explains.
    #: "sale" is the outward one: stock sent to a customer, deducted from the
    #: level like any other issue and recorded in the same ledger.
    MANUALLY_RECORDABLE = frozenset({
        MovementType.OPENING,
        MovementType.RETURN_IN,
        MovementType.SALE,
    })

    # An incoming movement must carry the cost it arrives at, otherwise the
    # moving average silently drifts toward zero.
    COST_REQUIRED = frozenset({
        MovementType.OPENING,
        MovementType.PURCHASE,
        MovementType.ADJUSTMENT_IN,
        MovementType.TRANSFER_IN,
    })

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    product = models.ForeignKey(
        "sales.Product", on_delete=models.PROTECT, related_name="stock_movements"
    )
    movement_type = models.CharField(max_length=20, choices=MovementType.choices, db_index=True)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    resulting_quantity = models.IntegerField()
    resulting_average_cost = models.DecimalField(max_digits=18, decimal_places=2)
    reference_kind = models.CharField(
        max_length=20, choices=ReferenceKind.choices, default=ReferenceKind.MANUAL
    )
    reference_id = models.PositiveBigIntegerField(null=True, blank=True)
    reference_number = models.CharField(max_length=MOVEMENT_REFERENCE_MAX_LENGTH, blank=True)
    idempotency_key = models.CharField(max_length=IDEMPOTENCY_KEY_MAX_LENGTH, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements"
    )
    notes = models.CharField(max_length=MOVEMENT_NOTES_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="stock_movement_quantity_positive"),
            models.CheckConstraint(
                condition=Q(unit_cost__isnull=True) | Q(unit_cost__gte=0),
                name="stock_movement_unit_cost_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(resulting_average_cost__gte=0),
                name="stock_movement_resulting_cost_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(
                    movement_type__in=[
                        "opening", "purchase", "sale", "return_in", "return_out",
                        "adjustment_in", "adjustment_out", "transfer_in", "transfer_out",
                    ]
                ),
                name="stock_movement_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(reference_kind__in=["manual", "invoice", "order", "transfer"]),
                name="stock_movement_reference_kind_valid",
            ),
            # A reference id without a kind, or a kind without an id, would make
            # the soft link unresolvable in both directions.
            models.CheckConstraint(
                condition=(
                    Q(reference_kind="manual", reference_id__isnull=True)
                    | (~Q(reference_kind="manual") & Q(reference_id__isnull=False))
                ),
                name="stock_movement_reference_pair",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_stock_movement_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["warehouse", "product", "-occurred_at"]),
            models.Index(fields=["product", "-occurred_at"]),
            models.Index(fields=["reference_kind", "reference_id"]),
        ]

    @property
    def is_incoming(self):
        return self.movement_type in self.INCOMING

    @property
    def signed_quantity(self):
        return self.quantity if self.is_incoming else -self.quantity
