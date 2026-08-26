"""Quotation, Order, Invoice, Payment, cheque, installment, and customer ledger.

These are the commercial documents. `sales.Sale` (the operational record a Sales
Agent files when a lead converts) and `sales.SalesDocument` (the internal postal
tracking record) are deliberately left untouched: an Invoice may reference a
Sale, but neither replaces the other and no existing row is rewritten.

Bounded semantics, all configurable and all recorded in
`docs/backend/BILLING_SEMANTICS.md` because no external contract fixed them:

* **Money is `Decimal(18, 2)`, rounded half-up at every step.** One currency per
  deployment; no currency column, because a second currency needs a rate policy
  nobody has approved.
* **Tax is off by default** (`BILLING_DEFAULT_TAX_RATE = "0.00"`). The code
  applies whatever rate the deployment configures to a single taxable base; it
  encodes no jurisdiction's tax law and claims no compliance.
* **Numbering** is a per-kind gap-free counter formatted by
  `BILLING_NUMBER_FORMATS`. Uniqueness is a database constraint, not a hope.
* **A document is editable only while `draft`.** Once issued, the snapshot is
  immutable and a mistake is corrected by cancelling and re-issuing, so a
  printed document can never disagree with the stored row.
* **The ledger is append-only.** A balance is the running sum of its entries,
  and every entry carries the balance it produced.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


DOCUMENT_NUMBER_MAX_LENGTH = 64
FREE_TEXT_MAX_LENGTH = 4000
LINE_DESCRIPTION_MAX_LENGTH = 500
REFERENCE_MAX_LENGTH = 120
IDEMPOTENCY_KEY_MAX_LENGTH = 64
MAX_MONEY = Decimal("9999999999999999.99")
MAX_LINE_QUANTITY = 1_000_000


class DocumentSequence(models.Model):
    """One gap-free counter per document kind.

    A counter row rather than a database sequence, because it must be readable
    and restorable with the rest of the data: after a restore the next number
    continues from the restored state instead of colliding with numbers already
    printed on a customer's paperwork.
    """

    kind = models.CharField(max_length=32, unique=True)
    next_value = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind"]
        constraints = [
            models.CheckConstraint(condition=Q(next_value__gte=1), name="document_sequence_positive"),
        ]

    def __str__(self):
        return f"{self.kind}:{self.next_value}"


class CommercialDocument(TimeStampedModel):
    """Fields shared by Quotation, Order, and Invoice.

    Abstract: each concrete document owns its own table, its own status graph,
    and its own numbering kind. Nothing is shared at the row level.
    """

    number = models.CharField(max_length=DOCUMENT_NUMBER_MAX_LENGTH, unique=True)
    customer = models.ForeignKey(
        "sales.Customer", on_delete=models.PROTECT, related_name="%(class)ss"
    )
    customer_name_snapshot = models.CharField(max_length=255, blank=True)
    subtotal_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_%(class)ss"
    )

    class Meta:
        abstract = True


class DocumentLine(TimeStampedModel):
    """Fields shared by every document line.

    `product` stays a protected foreign key so catalogue history is preserved,
    while `product_name_snapshot` / `product_sku_snapshot` keep the document
    readable exactly as issued even if the catalogue is later renamed.
    """

    line_number = models.PositiveIntegerField()
    product = models.ForeignKey(
        "sales.Product", on_delete=models.PROTECT, related_name="%(class)ss"
    )
    product_name_snapshot = models.CharField(max_length=255)
    product_sku_snapshot = models.CharField(max_length=80)
    description = models.CharField(max_length=LINE_DESCRIPTION_MAX_LENGTH, blank=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        abstract = True


def _line_constraints(prefix):
    return [
        models.CheckConstraint(condition=Q(quantity__gt=0), name=f"{prefix}_quantity_positive"),
        models.CheckConstraint(condition=Q(unit_price__gte=0), name=f"{prefix}_unit_price_non_negative"),
        models.CheckConstraint(
            condition=Q(discount_amount__gte=0), name=f"{prefix}_discount_non_negative"
        ),
        models.CheckConstraint(
            condition=Q(discount_percent__gte=0) & Q(discount_percent__lte=100),
            name=f"{prefix}_discount_percent_bounded",
        ),
        models.CheckConstraint(condition=Q(line_total__gte=0), name=f"{prefix}_line_total_non_negative"),
        models.CheckConstraint(
            condition=Q(line_total=models.F("unit_price") * models.F("quantity") - models.F("discount_amount")),
            name=f"{prefix}_line_total_matches_inputs",
        ),
    ]


def _document_constraints(prefix, statuses):
    return [
        models.CheckConstraint(condition=Q(number__regex=r"\S"), name=f"{prefix}_number_nonblank"),
        models.CheckConstraint(condition=Q(status__in=statuses), name=f"{prefix}_status_valid"),
        models.CheckConstraint(condition=Q(subtotal_amount__gte=0), name=f"{prefix}_subtotal_non_negative"),
        models.CheckConstraint(condition=Q(discount_amount__gte=0), name=f"{prefix}_discount_non_negative"),
        models.CheckConstraint(
            condition=Q(tax_rate__gte=0) & Q(tax_rate__lte=100), name=f"{prefix}_tax_rate_bounded"
        ),
        models.CheckConstraint(condition=Q(tax_amount__gte=0), name=f"{prefix}_tax_non_negative"),
        models.CheckConstraint(condition=Q(total_amount__gte=0), name=f"{prefix}_total_non_negative"),
        # The header discount can never exceed what is being discounted.
        models.CheckConstraint(
            condition=Q(discount_amount__lte=models.F("subtotal_amount")),
            name=f"{prefix}_discount_within_subtotal",
        ),
        models.CheckConstraint(
            condition=Q(
                total_amount=models.F("subtotal_amount")
                - models.F("discount_amount")
                + models.F("tax_amount")
            ),
            name=f"{prefix}_total_matches_parts",
        ),
    ]


class Quotation(CommercialDocument):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    NUMBER_KIND = "quotation"
    EDITABLE_STATUSES = frozenset({Status.DRAFT})
    TRANSITIONS = {
        Status.DRAFT: frozenset({Status.SENT, Status.CANCELLED}),
        Status.SENT: frozenset({Status.ACCEPTED, Status.REJECTED, Status.EXPIRED, Status.CANCELLED}),
        Status.ACCEPTED: frozenset({Status.EXPIRED, Status.CANCELLED}),
        Status.REJECTED: frozenset(),
        Status.EXPIRED: frozenset(),
        Status.CANCELLED: frozenset(),
    }

    lead = models.ForeignKey(
        "sales.Lead", null=True, blank=True, on_delete=models.PROTECT, related_name="quotations"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    valid_until = models.DateTimeField(null=True, blank=True, db_index=True)
    issued_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = _document_constraints(
            "quotation", ["draft", "sent", "accepted", "rejected", "expired", "cancelled"]
        )
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self):
        return self.number


class QuotationItem(DocumentLine):
    quotation = models.ForeignKey(Quotation, on_delete=models.PROTECT, related_name="items")

    class Meta:
        ordering = ["quotation_id", "line_number"]
        constraints = [
            *_line_constraints("quotation_item"),
            models.UniqueConstraint(
                fields=["quotation", "line_number"], name="uniq_quotation_item_line_number"
            ),
        ]


class Order(CommercialDocument):
    class ShippingMethod(models.TextChoices):
        POST = "post", "پست"
        COURIER = "courier", "پیک"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    NUMBER_KIND = "order"
    #: An approved order stays editable: Client-1 adjusts quantities after
    #: approval, and the stock reconciliation below moves only the difference.
    EDITABLE_STATUSES = frozenset({Status.DRAFT, Status.CONFIRMED})
    TRANSITIONS = {
        Status.DRAFT: frozenset({Status.CONFIRMED, Status.CANCELLED}),
        Status.CONFIRMED: frozenset({Status.FULFILLED, Status.CANCELLED}),
        Status.FULFILLED: frozenset(),
        Status.CANCELLED: frozenset(),
    }

    quotation = models.ForeignKey(
        Quotation, null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )
    lead = models.ForeignKey(
        "sales.Lead", null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )
    #: Where the goods leave from when the order is approved. An order without
    #: one has no stock effect at all.
    warehouse = models.ForeignKey(
        "inventory.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    expected_delivery_at = models.DateTimeField(null=True, blank=True)
    #: How the goods travel. Blank until somebody decides, which is why it is a
    #: blank-able choice rather than a default that would claim a decision.
    shipping_method = models.CharField(
        max_length=20, choices=ShippingMethod.choices, blank=True, default=""
    )

    # --- Inventory lifecycle guards ----------------------------------------
    #
    # The order owns the stock movement, not the invoice: goods leave once on
    # approval and come back once on cancellation. `stock_applied` is what makes
    # "once" true under a retry — a repeated approval finds it already set and
    # moves nothing. `stock_revision` counts reconciliations so each one gets a
    # distinct idempotency key; without it a repeated edit would reuse the key
    # of the previous edit and be silently swallowed.
    stock_applied = models.BooleanField(default=False)
    stock_revision = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            *_document_constraints("order", ["draft", "confirmed", "fulfilled", "cancelled"]),
            models.CheckConstraint(
                condition=Q(shipping_method__in=["", "post", "courier"]),
                name="order_shipping_method_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self):
        return self.number


class OrderItem(DocumentLine):
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")

    class Meta:
        ordering = ["order_id", "line_number"]
        constraints = [
            *_line_constraints("order_item"),
            models.UniqueConstraint(fields=["order", "line_number"], name="uniq_order_item_line_number"),
        ]


class Invoice(CommercialDocument):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        CANCELLED = "cancelled", "Cancelled"

    class SettlementStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"

    class InvoiceType(models.TextChoices):
        """Whether this invoice is a tax document or an internal one.

        `OPEN_BUSINESS_DECISIONS.md` D.2 asked which of the two an Invoice is;
        the answer is that this deployment issues both, and the distinction is
        recorded per document rather than per deployment.

        What this field does today is exactly one thing: an official invoice
        must name the identities a tax document names, so those fields become
        required when it is set. It deliberately changes **nothing** about tax
        computation, the order of discount against tax, rounding, or numbering
        — D.3 through D.7 are still open, and inventing an answer to any of them
        here would put a wrong number on a legal document.

        The default is unofficial, because that is what every invoice in the
        system before this field was, and a migration cannot know which of them
        a tax authority ever saw.
        """

        UNOFFICIAL = "unofficial", "غیررسمی"
        OFFICIAL = "official", "رسمی"

    NUMBER_KIND = "invoice"
    EDITABLE_STATUSES = frozenset({Status.DRAFT})
    TRANSITIONS = {
        Status.DRAFT: frozenset({Status.ISSUED, Status.CANCELLED}),
        Status.ISSUED: frozenset({Status.CANCELLED}),
        Status.CANCELLED: frozenset(),
    }

    order = models.ForeignKey(
        Order, null=True, blank=True, on_delete=models.PROTECT, related_name="invoices"
    )
    quotation = models.ForeignKey(
        Quotation, null=True, blank=True, on_delete=models.PROTECT, related_name="invoices"
    )
    sale = models.ForeignKey(
        "sales.Sale", null=True, blank=True, on_delete=models.PROTECT, related_name="invoices"
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    invoice_type = models.CharField(
        max_length=20,
        choices=InvoiceType.choices,
        default=InvoiceType.UNOFFICIAL,
        db_index=True,
    )
    #: The number in the official series, taken at issue and never afterwards.
    #:
    #: Separate from `number`, which every document receives at creation. The
    #: official series must be gapless, and allocating from it at creation would
    #: not be: a draft that is abandoned, or one created official and switched
    #: back before issue, would have consumed a number no tax document ever
    #: carries. Taking it at the moment the document becomes official is the
    #: only point at which the series can stay whole.
    #:
    #: Blank on every unofficial invoice, and on every official one still in
    #: draft. Unique among the invoices that have one — the partial constraint
    #: below excludes the blanks, which would otherwise collide immediately.
    #:
    #: Cancellation does not release it. That is what gapless means: a cancelled
    #: official invoice keeps its number, and the number is not reissued.
    official_number = models.CharField(
        max_length=DOCUMENT_NUMBER_MAX_LENGTH, blank=True, default="", db_index=True
    )
    issued_at = models.DateTimeField(null=True, blank=True, db_index=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    #: The canonical figure, maintained only by PaymentAllocation. Nothing in
    #: the manual-settlement block below ever writes to it.
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    cancelled_at = models.DateTimeField(null=True, blank=True)
    stock_applied = models.BooleanField(default=False)

    # --- Manual settlement -------------------------------------------------
    #
    # Client-1 wants a "پرداخت شده" box an operator can type into, where
    # entering exactly the outstanding amount marks the invoice settled. That
    # is a *display* decision, not an accounting one: it creates no Payment, no
    # PaymentAllocation and no ledger entry, and it never touches `paid_amount`
    # or the customer balance. Payment, allocation and ledger keep meaning
    # exactly what they meant before, so receivables and the ledger stay true.
    #
    # It is deliberately one-way. Once the operator has matched the outstanding
    # amount the invoice is settled for good, and later edits to the typed value
    # cannot pull it back — an invoice that has been declared paid does not
    # become unpaid because somebody retyped a number. A real receipt feature
    # will replace this later; until then the override is isolated to these
    # three columns so nothing else has to be unwound.
    manual_paid_entry = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )
    manual_settled_at = models.DateTimeField(null=True, blank=True)
    manual_settled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="manually_settled_invoices",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            *_document_constraints("invoice", ["draft", "issued", "cancelled"]),
            models.CheckConstraint(condition=Q(paid_amount__gte=0), name="invoice_paid_non_negative"),
            # Unique among the invoices that carry one. A plain unique column
            # would collide on the first two blanks, and blank is the normal
            # state for every unofficial invoice and every unissued draft.
            models.UniqueConstraint(
                fields=["official_number"],
                condition=~Q(official_number=""),
                name="invoice_official_number_unique",
            ),
            # Only an official invoice may hold one. A number in this series on
            # an unofficial document would mean the series had been spent on
            # something that is not a tax document.
            models.CheckConstraint(
                condition=Q(official_number="") | Q(invoice_type="official"),
                name="invoice_official_number_requires_official_type",
            ),
            models.CheckConstraint(
                condition=Q(manual_paid_entry__isnull=True) | Q(manual_paid_entry__gte=0),
                name="invoice_manual_entry_non_negative",
            ),
            # The stamp and its author travel together, so a settled invoice
            # always says who settled it.
            models.CheckConstraint(
                condition=(
                    Q(manual_settled_at__isnull=True, manual_settled_by__isnull=True)
                    | Q(manual_settled_at__isnull=False, manual_settled_by__isnull=False)
                ),
                name="invoice_manual_settlement_fields_consistent",
            ),
            # Allocation may never exceed the invoice; an overpayment stays on
            # the customer account instead of inflating a settled document.
            models.CheckConstraint(
                condition=Q(paid_amount__lte=models.F("total_amount")),
                name="invoice_paid_within_total",
            ),
            models.CheckConstraint(
                condition=Q(status="draft", issued_at__isnull=True) | ~Q(status="draft"),
                name="invoice_draft_has_no_issue_time",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-issued_at"]),
            models.Index(fields=["created_by", "-created_at"]),
            models.Index(fields=["due_at"]),
        ]

    def __str__(self):
        return self.number

    @property
    def is_manually_settled(self):
        """Whether the one-way manual override has fired for this invoice."""
        return self.manual_settled_at is not None

    @property
    def canonical_balance_due(self):
        """What the payment records alone say is outstanding.

        This is the figure receivables reporting and the customer ledger are
        built from, and the manual override never changes it.
        """
        return self.total_amount - self.paid_amount

    @property
    def balance_due(self):
        if self.is_manually_settled:
            return Decimal("0.00")
        return self.canonical_balance_due

    @property
    def settlement_status(self):
        if self.is_manually_settled:
            return self.SettlementStatus.PAID
        if self.status == self.Status.CANCELLED or self.paid_amount <= 0:
            return self.SettlementStatus.UNPAID
        if self.paid_amount >= self.total_amount:
            return self.SettlementStatus.PAID
        return self.SettlementStatus.PARTIALLY_PAID


class InvoiceItem(DocumentLine):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="items")
    # Captured from the warehouse moving average at the moment of issue. It is
    # what makes a profit figure sourced rather than guessed; a draft invoice or
    # an invoice with no warehouse leaves it null and reports no profit.
    unit_cost_snapshot = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["invoice_id", "line_number"]
        constraints = [
            *_line_constraints("invoice_item"),
            models.UniqueConstraint(fields=["invoice", "line_number"], name="uniq_invoice_item_line_number"),
            models.CheckConstraint(
                condition=Q(unit_cost_snapshot__isnull=True) | Q(unit_cost_snapshot__gte=0),
                name="invoice_item_cost_non_negative",
            ),
        ]

    @property
    def cost_total(self):
        if self.unit_cost_snapshot is None:
            return None
        return self.unit_cost_snapshot * self.quantity


class Payment(TimeStampedModel):
    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"
        CHEQUE = "cheque", "Cheque"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    NUMBER_KIND = "payment"

    number = models.CharField(max_length=DOCUMENT_NUMBER_MAX_LENGTH, unique=True)
    customer = models.ForeignKey("sales.Customer", on_delete=models.PROTECT, related_name="payments")
    method = models.CharField(max_length=20, choices=Method.choices, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    received_at = models.DateTimeField(db_index=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_payments"
    )
    #: The tracking / receipt number, whatever the method calls it: a cash
    #: receipt number, a transfer's شماره پیگیری. One column, because it is the
    #: same idea each time and splitting it per method would mean four columns
    #: of which three are always blank.
    reference = models.CharField(max_length=REFERENCE_MAX_LENGTH, blank=True)
    #: Where a bank transfer came from. Blank for every other method, and blank
    #: is also fine on a transfer: an operator recording one from a statement
    #: may genuinely not have the account it left, and refusing the receipt over
    #: that would lose the money rather than record it.
    #:
    #: `Cheque` keeps its own `bank_name`, deliberately. A cheque is a separate
    #: instrument with its own lifecycle and its own bank, and collapsing the
    #: two would tie a cheque's bank to the payment row that happens to carry it.
    bank_name = models.CharField(max_length=120, blank=True)
    #: شماره حساب or شبا. Stored as typed rather than normalised: an IBAN and
    #: a domestic account number have different shapes, and guessing which one
    #: an operator meant is how a wrong account ends up on a record.
    bank_account = models.CharField(max_length=64, blank=True)
    idempotency_key = models.CharField(max_length=IDEMPOTENCY_KEY_MAX_LENGTH, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(number__regex=r"\S"), name="payment_number_nonblank"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
            models.CheckConstraint(
                condition=Q(allocated_amount__gte=0), name="payment_allocated_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(allocated_amount__lte=models.F("amount")),
                name="payment_allocated_within_amount",
            ),
            models.CheckConstraint(
                condition=Q(method__in=["cash", "card", "bank_transfer", "cheque"]),
                name="payment_method_valid",
            ),
            # Bank details belong to a bank transfer and nothing else. A cash
            # receipt carrying an account number would mean the form had written
            # into the wrong record.
            models.CheckConstraint(
                condition=(
                    Q(method="bank_transfer")
                    | (Q(bank_name="") & Q(bank_account=""))
                ),
                name="payment_bank_details_only_on_transfer",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "confirmed", "cancelled"]),
                name="payment_status_valid",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="uniq_payment_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-received_at"]),
            models.Index(fields=["status", "-received_at"]),
        ]

    def __str__(self):
        return self.number

    @property
    def unallocated_amount(self):
        return self.amount - self.allocated_amount


class PaymentAllocation(TimeStampedModel):
    """One confirmed payment applied to one invoice.

    Allocation is a separate row rather than a field on either side because a
    payment may settle several invoices and an invoice may take several
    payments; both directions must stay auditable.
    """

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_payment_allocations"
    )
    is_reversed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_allocation_amount_positive"),
            models.UniqueConstraint(
                fields=["payment", "invoice"],
                condition=Q(is_reversed=False),
                name="uniq_active_payment_invoice_allocation",
            ),
        ]
        indexes = [
            models.Index(fields=["invoice", "-created_at"]),
            models.Index(fields=["payment", "-created_at"]),
        ]


class Cheque(TimeStampedModel):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registered"
        DEPOSITED = "deposited", "Deposited"
        CLEARED = "cleared", "Cleared"
        BOUNCED = "bounced", "Bounced"
        RETURNED = "returned", "Returned to customer"
        CANCELLED = "cancelled", "Cancelled"

    TRANSITIONS = {
        Status.REGISTERED: frozenset({Status.DEPOSITED, Status.RETURNED, Status.CANCELLED}),
        Status.DEPOSITED: frozenset({Status.CLEARED, Status.BOUNCED, Status.RETURNED}),
        Status.CLEARED: frozenset(),
        Status.BOUNCED: frozenset({Status.DEPOSITED, Status.RETURNED}),
        Status.RETURNED: frozenset(),
        Status.CANCELLED: frozenset(),
    }

    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="cheque")
    bank_name = models.CharField(max_length=120)
    branch_name = models.CharField(max_length=120, blank=True)
    serial_number = models.CharField(max_length=64)
    account_holder = models.CharField(max_length=255, blank=True)
    due_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REGISTERED, db_index=True
    )
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["due_date", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="cheque_amount_positive"),
            models.CheckConstraint(condition=Q(bank_name__regex=r"\S"), name="cheque_bank_nonblank"),
            models.CheckConstraint(condition=Q(serial_number__regex=r"\S"), name="cheque_serial_nonblank"),
            models.CheckConstraint(
                condition=Q(
                    status__in=["registered", "deposited", "cleared", "bounced", "returned", "cancelled"]
                ),
                name="cheque_status_valid",
            ),
            # A serial is unique within a bank; the same serial at another bank
            # is a different cheque.
            models.UniqueConstraint(
                fields=["bank_name", "serial_number"],
                condition=~Q(status="cancelled"),
                name="uniq_active_cheque_bank_serial",
            ),
        ]
        indexes = [models.Index(fields=["status", "due_date"])]

    def __str__(self):
        return f"{self.bank_name} {self.serial_number}"


class ChequeStatusHistory(models.Model):
    cheque = models.ForeignKey(Cheque, on_delete=models.PROTECT, related_name="history")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cheque_status_changes"
    )
    reason = models.CharField(max_length=500, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]
        indexes = [models.Index(fields=["cheque", "-changed_at"])]


class InstallmentPlan(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    invoice = models.OneToOneField(Invoice, on_delete=models.PROTECT, related_name="installment_plan")
    total_amount = models.DecimalField(max_digits=18, decimal_places=2)
    installment_count = models.PositiveSmallIntegerField()
    interval_days = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_installment_plans"
    )
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(total_amount__gt=0), name="installment_plan_total_positive"),
            models.CheckConstraint(
                condition=Q(installment_count__gte=1) & Q(installment_count__lte=120),
                name="installment_plan_count_bounded",
            ),
            models.CheckConstraint(
                condition=Q(interval_days__gte=1) & Q(interval_days__lte=365),
                name="installment_plan_interval_bounded",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "completed", "cancelled"]),
                name="installment_plan_status_valid",
            ),
        ]


class Installment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIALLY_PAID = "partially_paid", "Partially paid"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    plan = models.ForeignKey(InstallmentPlan, on_delete=models.PROTECT, related_name="installments")
    sequence = models.PositiveSmallIntegerField()
    due_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    class Meta:
        ordering = ["plan_id", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["plan", "sequence"], name="uniq_installment_plan_sequence"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="installment_amount_positive"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0), name="installment_paid_non_negative"),
            models.CheckConstraint(
                condition=Q(paid_amount__lte=models.F("amount")), name="installment_paid_within_amount"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "partially_paid", "paid", "cancelled"]),
                name="installment_status_valid",
            ),
        ]
        indexes = [models.Index(fields=["status", "due_date"])]

    @property
    def balance_due(self):
        return self.amount - self.paid_amount


class CustomerLedgerEntry(TimeStampedModel):
    """One append-only movement on a customer account.

    Debit increases what the customer owes; credit reduces it. `balance_after`
    is the running balance this entry produced, so a statement never has to
    replay arithmetic and a corrupted middle row is detectable rather than
    silently absorbed.

    Nothing here is ever updated or deleted. A reversal is another entry.
    """

    class EntryType(models.TextChoices):
        OPENING_BALANCE = "opening_balance", "Opening balance"
        INVOICE_ISSUED = "invoice_issued", "Invoice issued"
        INVOICE_CANCELLED = "invoice_cancelled", "Invoice cancelled"
        PAYMENT_RECEIVED = "payment_received", "Payment received"
        PAYMENT_CANCELLED = "payment_cancelled", "Payment cancelled"
        ADJUSTMENT_DEBIT = "adjustment_debit", "Adjustment (debit)"
        ADJUSTMENT_CREDIT = "adjustment_credit", "Adjustment (credit)"

    class ReferenceKind(models.TextChoices):
        NONE = "none", "None"
        INVOICE = "invoice", "Invoice"
        PAYMENT = "payment", "Payment"

    customer = models.ForeignKey(
        "sales.Customer", on_delete=models.PROTECT, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=24, choices=EntryType.choices, db_index=True)
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    balance_after = models.DecimalField(max_digits=20, decimal_places=2)
    reference_kind = models.CharField(
        max_length=20, choices=ReferenceKind.choices, default=ReferenceKind.NONE
    )
    reference_id = models.PositiveBigIntegerField(null=True, blank=True)
    reference_number = models.CharField(max_length=DOCUMENT_NUMBER_MAX_LENGTH, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_ledger_entries"
    )
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(debit__gte=0), name="ledger_debit_non_negative"),
            models.CheckConstraint(condition=Q(credit__gte=0), name="ledger_credit_non_negative"),
            # Exactly one side carries the amount; a row with both or neither
            # has no defined effect on the balance.
            models.CheckConstraint(
                condition=(Q(debit__gt=0) & Q(credit=0)) | (Q(credit__gt=0) & Q(debit=0)),
                name="ledger_exactly_one_side",
            ),
            models.CheckConstraint(
                condition=Q(
                    entry_type__in=[
                        "opening_balance", "invoice_issued", "invoice_cancelled",
                        "payment_received", "payment_cancelled", "adjustment_debit",
                        "adjustment_credit",
                    ]
                ),
                name="ledger_entry_type_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(reference_kind="none", reference_id__isnull=True)
                    | (~Q(reference_kind="none") & Q(reference_id__isnull=False))
                ),
                name="ledger_reference_pair",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-occurred_at", "-id"]),
            models.Index(fields=["reference_kind", "reference_id"]),
        ]
