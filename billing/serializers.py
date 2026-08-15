from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

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
from billing.selectors import invoices_for, orders_for, payments_for, quotations_for
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(self.fields["product"], products_for(request.user).filter(is_active=True))


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


class CommercialDocumentSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
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
            "id", "number", "customer", "customer_name", "lead", "quotation", "status",
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


class InvoiceSerializer(CommercialDocumentSerializer):
    server_fields = {
        "number", "status", "customer_name", "subtotal_amount", "tax_amount", "total_amount",
        "issued_at", "cancelled_at", "paid_amount", "balance_due", "settlement_status",
        "stock_applied", "created_by", "created_by_display", "line_items", "created_at", "updated_at",
    }
    line_items = InvoiceItemSerializer(source="items", many=True, read_only=True)
    paid_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    settlement_status = serializers.CharField(read_only=True)
    stock_applied = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "number", "customer", "customer_name", "order", "quotation", "sale",
            "warehouse", "status", "subtotal_amount", "discount_amount", "tax_rate", "tax_amount",
            "total_amount", "paid_amount", "balance_due", "settlement_status", "issued_at",
            "due_at", "cancelled_at", "stock_applied", "notes", "created_by", "created_by_display",
            "items", "line_items", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number", "customer_name", "status", "subtotal_amount", "tax_amount",
            "total_amount", "paid_amount", "balance_due", "settlement_status", "issued_at",
            "cancelled_at", "stock_applied", "created_by", "created_by_display", "line_items",
            "created_at", "updated_at",
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


class DocumentItemsSerializer(RejectServerFieldsMixin, serializers.Serializer):
    items = DocumentLineInputSerializer(many=True)


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
    branch_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    serial_number = serializers.CharField(max_length=64)
    account_holder = serializers.CharField(max_length=255, required=False, allow_blank=True)
    due_date = serializers.DateField()
    notes = serializers.CharField(max_length=4000, required=False, allow_blank=True)


class ChequeSerializer(serializers.ModelSerializer):
    payment_number = serializers.CharField(source="payment.number", read_only=True)
    customer = serializers.IntegerField(source="payment.customer_id", read_only=True)
    customer_name = serializers.CharField(source="payment.customer.full_name", read_only=True)

    class Meta:
        model = Cheque
        fields = [
            "id", "payment", "payment_number", "customer", "customer_name", "bank_name",
            "branch_name", "serial_number", "account_holder", "due_date", "amount", "status",
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
        "created_at", "updated_at",
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

    class Meta:
        model = Payment
        fields = [
            "id", "number", "customer", "customer_name", "method", "status", "amount",
            "allocated_amount", "unallocated_amount", "received_at", "received_by",
            "received_by_display", "reference", "idempotency_key", "cancelled_at", "notes",
            "cheque", "cheque_detail", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "number", "customer_name", "status", "allocated_amount", "unallocated_amount",
            "received_by", "received_by_display", "cancelled_at", "cheque_detail",
            "created_at", "updated_at",
        ]

    def get_received_by_display(self, instance) -> str:
        return _display(instance.received_by)

    @extend_schema_field(ChequeSerializer(allow_null=True))
    def get_cheque_detail(self, instance):
        cheque = Cheque.objects.filter(payment=instance).first()
        return ChequeSerializer(cheque).data if cheque is not None else None

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


class AllocatePaymentSerializer(RejectServerFieldsMixin, serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.none())
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, min_value=0
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(
                self.fields["invoice"], invoices_for(request.user).filter(status=Invoice.Status.ISSUED)
            )


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
