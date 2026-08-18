from rest_framework import serializers

from common.serializers import RejectServerFieldsMixin
from inventory.models import StockItem, StockMovement, Warehouse
from inventory.selectors import warehouses_for
from inventory.services import create_warehouse, record_stock_movement, update_warehouse
from sales.models import Product
from sales.selectors import products_for


def _scope_relation(field, queryset):
    field.queryset = queryset
    field.error_messages["does_not_exist"] = "Invalid object."


class WarehouseSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {
        "normalized_name", "is_active", "created_by", "created_by_display",
        "updated_by", "updated_by_display", "created_at", "updated_at",
    }
    code = serializers.CharField(max_length=64, validators=[])
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    updated_by_display = serializers.SerializerMethodField()

    class Meta:
        model = Warehouse
        fields = [
            "id", "code", "name", "address", "is_default", "is_active",
            "created_by", "created_by_display", "updated_by", "updated_by_display",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "is_active", "created_by", "created_by_display", "updated_by",
            "updated_by_display", "created_at", "updated_at",
        ]

    @staticmethod
    def _display(user) -> str:
        return user.get_full_name() or user.username

    def get_created_by_display(self, instance) -> str:
        return self._display(instance.created_by)

    def get_updated_by_display(self, instance) -> str:
        return self._display(instance.updated_by)

    def create(self, validated_data):
        return create_warehouse(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("code", None)
        return update_warehouse(
            actor=self.context["request"].user, warehouse=instance, **validated_data
        )


class StockItemSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    stock_value = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)

    class Meta:
        model = StockItem
        fields = [
            "id", "warehouse", "warehouse_name", "product", "product_name", "product_sku",
            "quantity", "average_cost", "stock_value", "last_movement_at",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class StockMovementSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    """A movement recorded by a person through the movement form.

    `movement_type` is narrowed to the three kinds an operator records directly:
    opening stock, a customer return, and stock sent to a customer. The other
    kinds are produced by an operation that explains them — a transfer between
    warehouses, an order being issued — and are written by those services rather
    than typed in here.

    This is a narrowing of the write contract, not a hidden option: the endpoint
    refuses a kind outside the list even when the request is hand-made.
    """

    movement_type = serializers.ChoiceField(
        choices=[
            (value, label)
            for value, label in StockMovement.MovementType.choices
            if value in StockMovement.MANUALLY_RECORDABLE
        ]
    )
    server_fields = {
        "resulting_quantity", "resulting_average_cost", "created_by", "created_by_display",
        "reference_kind", "reference_id", "reference_number", "warehouse_name",
        "product_name", "created_at", "updated_at",
    }
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    resulting_quantity = serializers.IntegerField(read_only=True)
    resulting_average_cost = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    unit_cost = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True
    )
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_blank=True)

    class Meta:
        model = StockMovement
        fields = [
            "id", "warehouse", "warehouse_name", "product", "product_name", "movement_type",
            "quantity", "unit_cost", "resulting_quantity", "resulting_average_cost",
            "reference_kind", "reference_id", "reference_number", "idempotency_key",
            "occurred_at", "created_by", "created_by_display", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "warehouse_name", "product_name", "resulting_quantity",
            "resulting_average_cost", "reference_kind", "reference_id", "reference_number",
            "created_by", "created_by_display", "created_at", "updated_at",
        ]

    def get_created_by_display(self, instance) -> str:
        return instance.created_by.get_full_name() or instance.created_by.username

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(self.fields["warehouse"], warehouses_for(request.user).filter(is_active=True))
            _scope_relation(self.fields["product"], products_for(request.user))
        else:
            _scope_relation(self.fields["warehouse"], Warehouse.objects.none())
            _scope_relation(self.fields["product"], Product.objects.none())

    def create(self, validated_data):
        if validated_data.get("occurred_at") is None:
            validated_data.pop("occurred_at", None)
        return record_stock_movement(actor=self.context["request"].user, **validated_data)


class StockTransferSerializer(RejectServerFieldsMixin, serializers.Serializer):
    from_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())
    to_warehouse = serializers.PrimaryKeyRelatedField(queryset=Warehouse.objects.none())
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none())
    quantity = serializers.IntegerField(min_value=1)
    occurred_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            warehouses = warehouses_for(request.user).filter(is_active=True)
            _scope_relation(self.fields["from_warehouse"], warehouses)
            _scope_relation(self.fields["to_warehouse"], warehouses)
            _scope_relation(self.fields["product"], products_for(request.user))
