from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from decimal import Decimal

from billing.models import (
    Cheque,
    ChequeStatusHistory,
    CustomerLedgerEntry,
    Installment,
    InstallmentPlan,
    Invoice,
    InvoiceItem,
    Order,
    OrderItem,
    Payment,
    PaymentAllocation,
    Quotation,
    QuotationItem,
)
from billing.selectors import invoices_for, orders_for, quotations_for
from billing.services import (
    create_invoice,
    create_order,
    create_quotation,
    update_invoice,
    update_order,
    update_quotation,
)
from common.serializers import RejectServerFieldsMixin
from inventory.models import Warehouse
from inventory.selectors import warehouses_for
from sales.models import Customer, Lead, Product, Sale
from sales.selectors import customers_for, leads_for, products_for, sales_for


def _scope_relation(field, queryset):
    field.queryset = queryset
    field.error_messages["does_not_exist"] = "Invalid object."


def _display(user):
    if user is None:
        return ""
    return user.get_full_name() or user.username


class DocumentLineInputSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """One requested document line.

    `unit_price` may be omitted, in which case the service snapshots the
    product's current price. A discount is given either as a percentage or as an
    absolute amount, never both — the service refuses the ambiguous pair.
    """

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none())
    quantity = serializers.IntegerField(min_value=1, max_value=1_000_000)
    unit_price = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True, min_value=0, max_value=100
    )
    discount_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ScopedLineItemsMixin:
    """Scope the nested line serializer's product field to the caller.

    A nested serializer declared as a class attribute is constructed before DRF
    binds it to a parent, so its own `__init__` runs with an empty context and
    cannot see the request. Scoping it from the parent — which does receive the
    context — is what makes an out-of-scope product id resolve to "Invalid
    object" instead of silently accepting every product in the catalogue.
    """

    def scope_line_products(self):
        items = self.fields.get("items")
        if items is None:
            return
        request = self.context.get("request")
        queryset = (
            products_for(request.user).filter(is_active=True)
            if request and request.user.is_authenticated
            else Product.objects.none()
        )
        _scope_relation(items.child.fields["product"], queryset)


class DocumentLineOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    line_number = serializers.IntegerField(read_only=True)
    product = serializers.IntegerField(source="product_id", read_only=True)
    product_name_snapshot = serializers.CharField(read_only=True)
    product_sku_snapshot = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    discount_percent = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    discount_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)


class QuotationItemSerializer(DocumentLineOutputSerializer):
    pass


class OrderItemSerializer(DocumentLineOutputSerializer):
    pass


class InvoiceItemSerializer(DocumentLineOutputSerializer):
    unit_cost_snapshot = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True, allow_null=True
    )


class CommercialDocumentSerializer(ScopedLineItemsMixin, RejectServerFieldsMixin, serializers.ModelSerializer):
    """Shared read/write shape of Quotation, Order, and Invoice."""

    items = DocumentLineInputSerializer(many=True, write_only=True, required=False)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    number = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    subtotal_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    tax_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    def get_created_by_display(self, instance) -> str:
        return _display(instance.created_by)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        authenticated = bool(request and request.user.is_authenticated)
        _scope_relation(
            self.fields["customer"],
            customers_for(request.user) if authenticated else Customer.objects.none(),
        )
        if "lead" in self.fields:
            _scope_relation(
                self.fields["lead"], leads_for(request.user) if authenticated else Lead.objects.none()
            )
        self.scope_line_products()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get("items"):
            raise serializers.ValidationError({"items": "A document needs at least one line."})
        if self.instance is not None and "items" in getattr(self, "initial_data", {}):
            raise serializers.ValidationError({
                "items": "Use the document's items action to replace lines."
            })
        if self.instance is not None and "customer" in attrs and attrs["customer"] != self.instance.customer:
            raise serializers.ValidationError({"customer": "Document customer cannot change."})
        return attrs


class QuotationSerializer(CommercialDocumentSerializer):
    server_fields = {
        "number", "status", "customer_name", "subtotal_amount", "tax_amount", "total_amount",
        "issued_at", "created_by", "created_by_display", "line_items", "created_at", "updated_at",
    }
    line_items = QuotationItemSerializer(source="items", many=True, read_only=True)

    class Meta:
        model = Quotation
        fields = [
            "id", "number", "customer", "customer_name", "lead", "status", "subtotal_amount",
            "discount_amount", "tax_rate", "tax_amount", "total_amount", "valid_until",
            "issued_at", "notes", "created_by", "created_by_display", "items", "line_items",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number", "customer_name", "status", "subtotal_amount", "tax_amount",
            "total_amount", "issued_at", "created_by", "created_by_display", "line_items",
            "created_at", "updated_at",
        ]

    def create(self, validated_data):
        items = validated_data.pop("items")
        return create_quotation(actor=self.context["request"].user, items=items, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("items", None)
        validated_data.pop("customer", None)
        validated_data.pop("lead", None)
        return update_quotation(
            actor=self.context["request"].user, quotation=instance, **validated_data
        )


class OrderSerializer(CommercialDocumentSerializer):
    server_fields = {
        "number", "status", "customer_name", "subtotal_amount", "tax_amount", "total_amount",
        "confirmed_at", "created_by", "created_by_display", "line_items", "created_at", "updated_at",
    }
    line_items = OrderItemSerializer(source="items", many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "number", "customer", "customer_name", "lead", "quotation", "warehouse",
            "shipping_method", "status",
            "subtotal_amount", "discount_amount", "tax_rate", "tax_amount", "total_amount",
            "expected_delivery_at", "confirmed_at", "notes", "created_by", "created_by_display",
            "items", "line_items", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number", "customer_name", "status", "subtotal_amount", "tax_amount",
            "total_amount", "confirmed_at", "created_by", "created_by_display", "line_items",
            "created_at", "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        _scope_relation(
            self.fields["quotation"],
            quotations_for(request.user) if request and request.user.is_authenticated
            else Quotation.objects.none(),
        )

    def create(self, validated_data):
        items = validated_data.pop("items")
        return create_order(actor=self.context["request"].user, items=items, **validated_data)

    def update(self, instance, validated_data):
        for field in ("items", "customer", "lead", "quotation"):
            validated_data.pop(field, None)
        return update_order(actor=self.context["request"].user, order=instance, **validated_data)


class ManualPaidEntrySerializer(RejectServerFieldsMixin, serializers.Serializer):
    """The typed "پرداخت شده" figure.

    Display only: matching the outstanding amount marks the invoice settled and
    writes no accounting record. See `billing.services.record_manual_paid_entry`.
    """

    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("0.00"))


class InvoiceOrderLinkSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """Attach an invoice to an order after both exist, or detach it with null."""

    order = serializers.PrimaryKeyRelatedField(
        queryset=Order.objects.all(), allow_null=True, required=True
    )


class InvoiceSerializer(CommercialDocumentSerializer):
    server_fields = {
        "number", "status", "customer_name", "subtotal_amount", "tax_amount", "total_amount",
        "issued_at", "cancelled_at", "paid_amount", "balance_due", "settlement_status",
        "stock_applied", "created_by", "created_by_display", "line_items", "created_at", "updated_at",
        "manual_paid_entry", "manual_settled_at", "is_manually_settled", "canonical_balance_due",
        "invoice_type_display", "official_number", "customer_kind", "customer_national_id",
        "customer_economic_code",
    }
    line_items = InvoiceItemSerializer(source="items", many=True, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    settlement_status = serializers.CharField(read_only=True)
    stock_applied = serializers.BooleanField(read_only=True)
    #: What the payment records alone say, alongside what the screen shows. Both
    #: are published so a reader can tell a manual settlement from a real one.
    canonical_balance_due = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    manual_paid_entry = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    manual_settled_at = serializers.DateTimeField(read_only=True)
    is_manually_settled = serializers.BooleanField(read_only=True)
    #: Writable while the invoice is a draft, like every other document field:
    #: the identity requirements it brings are checked at issue, not here, so an
    #: operator can set the type first and complete the buyer's details after.
    invoice_type = serializers.ChoiceField(
        choices=Invoice.InvoiceType.choices, required=False
    )
    invoice_type_display = serializers.CharField(
        source="get_invoice_type_display", read_only=True
    )
    #: The buyer's identity, read through rather than duplicated, so the page
    #: can tell the operator what an official invoice is still missing without
    #: fetching the customer separately. Read-only: the customer record owns
    #: these, and editing them from an invoice would be editing the wrong thing.
    customer_kind = serializers.CharField(source="customer.kind", read_only=True)
    customer_national_id = serializers.CharField(source="customer.national_id", read_only=True)
    customer_economic_code = serializers.CharField(source="customer.economic_code", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "customer", "customer_name", "order", "quotation", "sale",
            "warehouse", "status", "invoice_type", "invoice_type_display", "official_number",
            "customer_kind", "customer_national_id", "customer_economic_code",
            "subtotal_amount", "discount_amount", "tax_rate", "tax_amount",
            "total_amount", "paid_amount", "balance_due", "canonical_balance_due",
            "settlement_status", "issued_at", "due_at", "cancelled_at", "stock_applied",
            "manual_paid_entry", "manual_settled_at", "is_manually_settled",
            "notes", "created_by", "created_by_display",
            "items", "line_items", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number", "official_number", "customer_name", "status", "invoice_type_display",
            "customer_kind", "customer_national_id", "customer_economic_code",
            "subtotal_amount", "tax_amount",
            "total_amount", "paid_amount", "balance_due", "canonical_balance_due",
            "settlement_status", "issued_at", "cancelled_at", "stock_applied",
            "manual_paid_entry", "manual_settled_at", "is_manually_settled",
            "created_by", "created_by_display", "line_items", "created_at", "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        authenticated = bool(request and request.user.is_authenticated)
        _scope_relation(
            self.fields["order"],
            orders_for(request.user) if authenticated else Order.objects.none(),
        )
        _scope_relation(
            self.fields["quotation"],
            quotations_for(request.user) if authenticated else Quotation.objects.none(),
        )
        _scope_relation(
            self.fields["sale"], sales_for(request.user) if authenticated else Sale.objects.none()
        )
        _scope_relation(
            self.fields["warehouse"],
            warehouses_for(request.user).filter(is_active=True) if authenticated
            else Warehouse.objects.none(),
        )

    def create(self, validated_data):
        items = validated_data.pop("items")
        return create_invoice(actor=self.context["request"].user, items=items, **validated_data)

    def update(self, instance, validated_data):
        for field in ("items", "customer", "order", "quotation", "sale"):
            validated_data.pop(field, None)
        return update_invoice(actor=self.context["request"].user, invoice=instance, **validated_data)


class DocumentItemsSerializer(ScopedLineItemsMixin, RejectServerFieldsMixin, serializers.Serializer):
    items = DocumentLineInputSerializer(many=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scope_line_products()


class DocumentStatusTransitionSerializer(RejectServerFieldsMixin, serializers.Serializer):
    to_status = serializers.CharField(max_length=20, trim_whitespace=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ReasonSerializer(RejectServerFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ConvertOrderSerializer(RejectServerFieldsMixin, serializers.Serializer):
    warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.none(), required=False, allow_null=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(
                self.fields["warehouse"], warehouses_for(request.user).filter(is_active=True)
            )


class ChequeInputSerializer(RejectServerFieldsMixin, serializers.Serializer):
    bank_name = serializers.CharField(max_length=120)
    #: شماره جاری — the account drawn on, distinct from the serial number.
    bank_account = serializers.CharField(max_length=64, required=False, allow_blank=True)
    branch_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    serial_number = serializers.CharField(max_length=64)
    #: Only meaningful on a disbursement; blank on a cheque received from a
    #: customer, where the question does not arise.
    source = serializers.ChoiceField(
        choices=Cheque.Source.choices, required=False, allow_blank=True
    )
    account_holder = serializers.CharField(max_length=255, required=False, allow_blank=True)
    due_date = serializers.DateField()
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True)


class ChequeSpendSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """Endorsing a received cheque onward. Only the recipient and why."""

    payee = serializers.CharField(max_length=255)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ChequeSerializer(serializers.ModelSerializer):
    payment_number = serializers.CharField(source="payment.number", read_only=True)
    customer = serializers.IntegerField(source="payment.customer_id", read_only=True)
    customer_name = serializers.CharField(source="payment.customer.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Cheque
        fields = [
            "id", "payment", "payment_number", "customer", "customer_name", "bank_name",
            "bank_account", "branch_name", "serial_number", "account_holder", "due_date", "registered_on", "is_registered",
            "amount", "status", "status_display", "source", "paid_to",
            "notes", "created_at", "updated_at",
        ]
        read_only_fields = fields


class ChequeStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_display = serializers.SerializerMethodField()

    class Meta:
        model = ChequeStatusHistory
        fields = [
            "id", "cheque", "from_status", "to_status", "changed_by", "changed_by_display",
            "reason", "changed_at",
        ]
        read_only_fields = fields

    def get_changed_by_display(self, instance) -> str:
        return _display(instance.changed_by)


class PaymentSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {
        "number", "status", "allocated_amount", "unallocated_amount", "customer_name",
        "received_by", "received_by_display", "cancelled_at", "cheque_detail",
        "direction_display", "created_at", "updated_at",
    }
    cheque = ChequeInputSerializer(write_only=True, required=False)
    # A method field rather than a nested serializer: the reverse one-to-one
    # raises rather than returning None for the (usual) non-cheque payment.
    cheque_detail = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    number = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    allocated_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    unallocated_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    received_by = serializers.PrimaryKeyRelatedField(read_only=True)
    received_by_display = serializers.SerializerMethodField()
    received_at = serializers.DateTimeField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)
    direction = serializers.ChoiceField(choices=Payment.Direction.choices, required=False)
    direction_display = serializers.CharField(source="get_direction_display", read_only=True)
    #: Required for a disbursement, refused for a receipt — checked by the
    #: service, which is also where a script or a management command arrives.
    payee = serializers.CharField(max_length=255, required=False, allow_blank=True)

    class Meta:
        model = Payment
        fields = [
            "id", "number", "customer", "customer_name", "method", "status", "amount",
            "allocated_amount", "unallocated_amount", "received_at", "received_by",
            "received_by_display", "direction", "direction_display", "payee",
            "reference", "bank_name", "bank_account",
            "idempotency_key", "cancelled_at", "notes",
            "cheque", "cheque_detail", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number", "customer_name", "status", "direction_display",
            "allocated_amount", "unallocated_amount",
            "received_by", "received_by_display", "cancelled_at", "cheque_detail",
            "created_at", "updated_at",
        ]

    def get_received_by_display(self, instance) -> str:
        return _display(instance.received_by)

    @extend_schema_field(ChequeSerializer(allow_null=True))
    def get_cheque_detail(self, instance):
        # Read the relation the queryset already selected rather than issuing a
        # fresh query: this runs once per row, so a lookup here is a straight
        # N+1 on the payments list.
        try:
            cheque = instance.cheque
        except Cheque.DoesNotExist:
            return None
        return ChequeSerializer(cheque).data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        _scope_relation(
            self.fields["customer"],
            customers_for(request.user) if request and request.user.is_authenticated
            else Customer.objects.none(),
        )

    def create(self, validated_data):
        from billing.payments import register_payment

        if validated_data.get("received_at") is None:
            validated_data.pop("received_at", None)
        return register_payment(actor=self.context["request"].user, **validated_data)


class PaymentAllocationSerializer(serializers.ModelSerializer):
    payment_number = serializers.CharField(source="payment.number", read_only=True)
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    created_by_display = serializers.SerializerMethodField()

    class Meta:
        model = PaymentAllocation
        fields = [
            "id", "payment", "payment_number", "invoice", "invoice_number", "amount",
            "is_reversed", "created_by", "created_by_display", "created_at",
        ]
        read_only_fields = fields

    def get_created_by_display(self, instance) -> str:
        return _display(instance.created_by)


class ScopedIssuedInvoiceField(serializers.PrimaryKeyRelatedField):
    """An issued invoice the requesting user is allowed to see.

    The scope is resolved in `get_queryset`, which DRF calls during validation,
    rather than in a serializer's `__init__`.

    That distinction is the whole point. `__init__` runs when the serializer is
    *constructed*, and a serializer nested as a field — `AllocatePaymentSerializer(many=True)`
    — is constructed once, at class-definition time, when there is no request and
    no context. Scoping there left the nested child holding `Invoice.objects.none()`
    forever, so every id it was given came back as "invalid pk", and the split
    endpoint could not allocate to any invoice at all. `get_queryset` runs per
    request, and `self.context` on a bound field resolves up through its parents,
    so the same field works standalone and nested.

    A caller with no authenticated request gets nothing, which is the safe end of
    the failure: an unscoped queryset here would let a split reach an invoice
    outside the caller's scope.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("queryset", Invoice.objects.none())
        super().__init__(**kwargs)
        self.error_messages["does_not_exist"] = "Invalid object."

    def get_queryset(self):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return Invoice.objects.none()
        return invoices_for(request.user).filter(status=Invoice.Status.ISSUED)


class AllocatePaymentSerializer(RejectServerFieldsMixin, serializers.Serializer):
    invoice = ScopedIssuedInvoiceField()
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, min_value=0
    )


class AllocatePaymentAcrossSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """One receipt, several invoices, one submission. (بند ۳.۱ و ۳.۲)

    Each row reuses `AllocatePaymentSerializer`, so an invoice offered here is
    scoped to what the requesting user may see exactly as it is for a single
    allocation — a split is not a way to reach an invoice outside your scope.
    """

    splits = AllocatePaymentSerializer(many=True)

    def validate_splits(self, value):
        if not value:
            raise serializers.ValidationError("Choose at least one invoice.")
        seen = set()
        for row in value:
            invoice = row["invoice"]
            if invoice.pk in seen:
                raise serializers.ValidationError(
                    "Each invoice may appear only once in a split."
                )
            seen.add(invoice.pk)
        return value


class ChequeTransitionSerializer(RejectServerFieldsMixin, serializers.Serializer):
    to_status = serializers.ChoiceField(choices=Cheque.Status.choices)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class InstallmentSerializer(serializers.ModelSerializer):
    balance_due = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Installment
        fields = [
            "id", "plan", "sequence", "due_date", "amount", "paid_amount", "balance_due",
            "status", "created_at", "updated_at",
        ]
        read_only_fields = fields


class InstallmentPlanSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True)
    customer = serializers.IntegerField(source="invoice.customer_id", read_only=True)
    customer_name = serializers.CharField(source="invoice.customer.full_name", read_only=True)
    installments = InstallmentSerializer(many=True, read_only=True)
    created_by_display = serializers.SerializerMethodField()

    class Meta:
        model = InstallmentPlan
        fields = [
            "id", "invoice", "invoice_number", "customer", "customer_name", "total_amount",
            "installment_count", "interval_days", "start_date", "status", "notes",
            "created_by", "created_by_display", "installments", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_created_by_display(self, instance) -> str:
        return _display(instance.created_by)


class CreateInstallmentPlanSerializer(RejectServerFieldsMixin, serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.none())
    installment_count = serializers.IntegerField(min_value=1, max_value=120)
    start_date = serializers.DateField()
    interval_days = serializers.IntegerField(
        min_value=1, max_value=365, required=False, allow_null=True
    )
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(
                self.fields["invoice"], invoices_for(request.user).filter(status=Invoice.Status.ISSUED)
            )


class CustomerLedgerEntrySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    created_by_display = serializers.SerializerMethodField()

    class Meta:
        model = CustomerLedgerEntry
        fields = [
            "id", "customer", "customer_name", "entry_type", "debit", "credit", "balance_after",
            "reference_kind", "reference_id", "reference_number", "occurred_at", "created_by",
            "created_by_display", "notes", "created_at",
        ]
        read_only_fields = fields

    def get_created_by_display(self, instance) -> str:
        return _display(instance.created_by)


class OpeningBalanceSerializer(RejectServerFieldsMixin, serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.none())
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(self.fields["customer"], customers_for(request.user))
