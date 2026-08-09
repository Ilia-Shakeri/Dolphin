from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers

from accounts.access import crm_identities
from accounts.models import User
from common.phones import normalize_customer_phone
from common.serializers import RejectServerFieldsMixin
from sales.models import Customer, CustomerPhone, Interaction, Lead, Product, Sale
from sales.selectors import customers_for, leads_for, products_for
from sales.services import create_customer_phone, create_customer_with_phone, create_lead, create_product, mark_sale, record_interaction, update_customer, update_customer_phone, update_lead, update_product


def _scope_relation(field, queryset):
    field.queryset = queryset
    field.error_messages["does_not_exist"] = "Invalid object."


class CustomerPhoneInlineSerializer(RejectServerFieldsMixin, serializers.Serializer):
    raw_phone = serializers.CharField(max_length=40)
    label = serializers.CharField(max_length=40, required=False, allow_blank=True)
    is_primary = serializers.BooleanField(default=True)

    def validate_raw_phone(self, value):
        normalize_customer_phone(value)
        return value


class CustomerSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"created_by", "is_active", "created_at", "updated_at"}
    phone = CustomerPhoneInlineSerializer(write_only=True, required=False)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Customer
        fields = ["id", "full_name", "national_id", "email", "province", "city", "address", "notes", "created_by", "is_active", "phone", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "is_active", "created_at", "updated_at"]

    def create(self, validated_data):
        phone = validated_data.pop("phone", None)
        try:
            return create_customer_with_phone(actor=self.context["request"].user, phone=phone, **validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError({"phone": "Active phone conflicts with an existing phone for this customer."}) from exc

    def update(self, instance, validated_data):
        return update_customer(actor=self.context["request"].user, customer=instance, **validated_data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and "phone" in attrs:
            raise serializers.ValidationError({"phone": "Phone can be supplied only when creating a customer."})
        return attrs


class CustomerPhoneSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"normalized_phone", "created_at", "updated_at"}
    normalized_phone = serializers.CharField(read_only=True)

    class Meta:
        model = CustomerPhone
        fields = ["id", "customer", "raw_phone", "normalized_phone", "label", "is_primary", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "normalized_phone", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = customers_for(request.user) if request and request.user.is_authenticated else Customer.objects.none()
        _scope_relation(self.fields["customer"], queryset)

    def create(self, validated_data):
        try:
            return create_customer_phone(actor=self.context["request"].user, **validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError("Active phone or primary-phone constraint failed.") from exc

    def validate_raw_phone(self, value):
        normalize_customer_phone(value)
        return value

    def update(self, instance, validated_data):
        if "customer" in validated_data and validated_data["customer"] != instance.customer:
            raise serializers.ValidationError({"customer": "Phone ownership cannot change."})
        validated_data.pop("customer", None)
        try:
            return update_customer_phone(actor=self.context["request"].user, phone=instance, **validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError("Active phone or primary-phone constraint failed.") from exc


class ProductSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"is_active", "created_by", "updated_by", "created_at", "updated_at"}
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "sku", "name", "current_price", "description", "is_active", "created_by", "updated_by", "created_at", "updated_at"]
        read_only_fields = ["id", "is_active", "created_by", "updated_by", "created_at", "updated_at"]

    def create(self, validated_data):
        return create_product(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        return update_product(actor=self.context["request"].user, product=instance, **validated_data)


class LeadSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"status", "assigned_to", "assigned_by", "assigned_at", "closed_at", "created_by", "source_payload", "created_at", "updated_at"}
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_to = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Lead
        fields = ["id", "customer", "source", "campaign_or_batch", "interested_product", "status", "assigned_to", "assigned_by", "assigned_at", "next_follow_up_at", "closed_at", "created_by", "notes", "source_payload", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "assigned_to", "assigned_by", "assigned_at", "closed_at", "created_by", "source_payload", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(self.fields["customer"], customers_for(request.user))
            _scope_relation(self.fields["interested_product"], products_for(request.user))
        else:
            _scope_relation(self.fields["customer"], Customer.objects.none())
            _scope_relation(self.fields["interested_product"], Product.objects.none())

    def create(self, validated_data):
        return create_lead(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        return update_lead(actor=self.context["request"].user, lead=instance, **validated_data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and "customer" in attrs and attrs["customer"] != self.instance.customer:
            raise serializers.ValidationError({"customer": "Lead customer cannot change."})
        product = attrs.get("interested_product")
        if product and not product.is_active:
            raise serializers.ValidationError({"interested_product": "Product is inactive."})
        return attrs


class ReassignSerializer(RejectServerFieldsMixin, serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(
        queryset=crm_identities(User.objects.filter(role=User.Role.SALES_AGENT, is_active=True)),
    )
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class InteractionSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer", "agent", "created_at", "updated_at"}
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    agent = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Interaction
        fields = ["id", "lead", "customer", "agent", "phone", "direction", "outcome", "occurred_at", "next_follow_up_at", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "customer", "agent", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = leads_for(request.user) if request and request.user.is_authenticated else Lead.objects.none()
        _scope_relation(self.fields["lead"], queryset)

    def create(self, validated_data):
        return record_interaction(actor=self.context["request"].user, **validated_data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and "lead" in attrs and attrs["lead"] != self.instance.lead:
            raise serializers.ValidationError({"lead": "Interaction lead cannot change."})
        return attrs


class SaleSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer", "sold_by", "unit_price_snapshot", "status", "created_at", "updated_at"}
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    sold_by = serializers.PrimaryKeyRelatedField(read_only=True)
    unit_price_snapshot = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)
    sold_at = serializers.DateTimeField(required=False, default=timezone.now)

    class Meta:
        model = Sale
        fields = ["id", "lead", "customer", "sold_by", "product", "quantity", "unit_price_snapshot", "total_amount", "status", "sold_at", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "customer", "sold_by", "unit_price_snapshot", "status", "created_at", "updated_at"]
        extra_kwargs = {"total_amount": {"required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(self.fields["lead"], leads_for(request.user))
            _scope_relation(self.fields["product"], products_for(request.user))
        else:
            _scope_relation(self.fields["lead"], Lead.objects.none())
            _scope_relation(self.fields["product"], Product.objects.none())

    def create(self, validated_data):
        return mark_sale(actor=self.context["request"].user, **validated_data)


class CancelSaleSerializer(RejectServerFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
