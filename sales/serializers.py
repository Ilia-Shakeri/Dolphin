from django.db import IntegrityError
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.access import crm_identities
from accounts.models import User
from common.phones import normalize_customer_phone
from common.serializers import RejectServerFieldsMixin
from sales.models import Customer, CustomerPhone, Interaction, Lead, LeadAssignmentHistory, Product, Sale
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


class CustomerPrimaryPhoneSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    raw_phone = serializers.CharField(read_only=True)
    normalized_phone = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)


class CustomerSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"created_by", "created_by_display", "is_active", "primary_phone", "created_at", "updated_at"}
    phone = CustomerPhoneInlineSerializer(write_only=True, required=False)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    primary_phone = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ["id", "full_name", "national_id", "email", "province", "city", "postal_code", "category", "address", "notes", "created_by", "created_by_display", "is_active", "primary_phone", "phone", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_by_display", "is_active", "primary_phone", "created_at", "updated_at"]

    def get_created_by_display(self, instance) -> str:
        return instance.created_by.get_full_name() or instance.created_by.username

    @extend_schema_field(CustomerPrimaryPhoneSerializer(allow_null=True))
    def get_primary_phone(self, instance):
        phone = next(
            (
                candidate
                for candidate in instance.phones.all()
                if candidate.is_active and candidate.is_primary
            ),
            None,
        )
        if phone is None:
            return None
        return {
            "id": phone.pk,
            "raw_phone": phone.raw_phone,
            "normalized_phone": phone.normalized_phone,
            "label": phone.label,
        }

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
    server_fields = {"normalized_phone", "is_active", "created_at", "updated_at"}
    normalized_phone = serializers.CharField(read_only=True)

    class Meta:
        model = CustomerPhone
        fields = ["id", "customer", "raw_phone", "normalized_phone", "label", "is_primary", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "normalized_phone", "is_active", "created_at", "updated_at"]

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
    server_fields = {"is_active", "created_by", "created_by_display", "updated_by", "updated_by_display", "created_at", "updated_at"}
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    updated_by_display = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "sku", "name", "current_price", "description", "is_active", "created_by", "created_by_display", "updated_by", "updated_by_display", "created_at", "updated_at"]
        read_only_fields = ["id", "is_active", "created_by", "created_by_display", "updated_by", "updated_by_display", "created_at", "updated_at"]

    @staticmethod
    def _display(user) -> str:
        return user.get_full_name() or user.username

    def get_created_by_display(self, instance) -> str:
        return self._display(instance.created_by)

    def get_updated_by_display(self, instance) -> str:
        return self._display(instance.updated_by)

    def create(self, validated_data):
        return create_product(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        return update_product(actor=self.context["request"].user, product=instance, **validated_data)


class LeadSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer_name", "status", "assigned_to", "assigned_to_display", "assigned_by", "assigned_at", "closed_at", "created_by", "source_payload", "created_at", "updated_at"}
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_to = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_by = serializers.PrimaryKeyRelatedField(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    assigned_to_display = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = ["id", "customer", "customer_name", "source", "campaign_or_batch", "interested_product", "status", "assigned_to", "assigned_to_display", "assigned_by", "assigned_at", "next_follow_up_at", "closed_at", "created_by", "notes", "source_payload", "created_at", "updated_at"]
        read_only_fields = ["id", "customer_name", "status", "assigned_to", "assigned_to_display", "assigned_by", "assigned_at", "closed_at", "created_by", "source_payload", "created_at", "updated_at"]

    def get_assigned_to_display(self, instance) -> str:
        if instance.assigned_to is None:
            return ""
        return instance.assigned_to.get_full_name() or instance.assigned_to.username

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


class LeadAssigneeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name"]
        read_only_fields = fields


class LeadAssignmentHistorySerializer(serializers.ModelSerializer):
    from_user_display = serializers.SerializerMethodField()
    to_user_display = serializers.SerializerMethodField()
    changed_by_display = serializers.SerializerMethodField()

    class Meta:
        model = LeadAssignmentHistory
        fields = [
            "id",
            "lead",
            "from_user",
            "from_user_display",
            "to_user",
            "to_user_display",
            "changed_by",
            "changed_by_display",
            "reason",
            "changed_at",
        ]
        read_only_fields = fields

    @staticmethod
    def _display(user) -> str:
        if user is None:
            return ""
        return user.get_full_name() or user.username

    def get_from_user_display(self, instance) -> str:
        return self._display(instance.from_user)

    def get_to_user_display(self, instance) -> str:
        return self._display(instance.to_user)

    def get_changed_by_display(self, instance) -> str:
        return self._display(instance.changed_by)


class InteractionSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer", "customer_name", "agent", "agent_display", "created_at", "updated_at"}
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    agent = serializers.PrimaryKeyRelatedField(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    agent_display = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = ["id", "lead", "customer", "customer_name", "agent", "agent_display", "phone", "direction", "outcome", "occurred_at", "next_follow_up_at", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "customer", "customer_name", "agent", "agent_display", "created_at", "updated_at"]

    def get_agent_display(self, instance) -> str:
        return instance.agent.get_full_name() or instance.agent.username

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = leads_for(request.user) if request and request.user.is_authenticated else Lead.objects.none()
        if request and request.user.is_authenticated and request.user.role == User.Role.SALES_AGENT:
            queryset = queryset.filter(assigned_to=request.user)
        _scope_relation(self.fields["lead"], queryset)

    def create(self, validated_data):
        return record_interaction(actor=self.context["request"].user, **validated_data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and "lead" in attrs and attrs["lead"] != self.instance.lead:
            raise serializers.ValidationError({"lead": "Interaction lead cannot change."})
        return attrs


class SaleSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer", "customer_name", "sold_by", "sold_by_display", "product_name", "unit_price_snapshot", "status", "created_at", "updated_at"}
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    sold_by = serializers.PrimaryKeyRelatedField(read_only=True)
    sold_by_display = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_price_snapshot = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)
    sold_at = serializers.DateTimeField(required=False, default=timezone.now)

    class Meta:
        model = Sale
        fields = ["id", "lead", "customer", "customer_name", "sold_by", "sold_by_display", "product", "product_name", "quantity", "unit_price_snapshot", "total_amount", "status", "sold_at", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "customer", "customer_name", "sold_by", "sold_by_display", "product_name", "unit_price_snapshot", "status", "created_at", "updated_at"]
        extra_kwargs = {"total_amount": {"required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            leads = leads_for(request.user)
            if request.user.role == User.Role.SALES_AGENT:
                leads = leads.filter(assigned_to=request.user)
            _scope_relation(self.fields["lead"], leads)
            _scope_relation(self.fields["product"], products_for(request.user))
        else:
            _scope_relation(self.fields["lead"], Lead.objects.none())
            _scope_relation(self.fields["product"], Product.objects.none())

    def create(self, validated_data):
        return mark_sale(actor=self.context["request"].user, **validated_data)

    def get_sold_by_display(self, instance) -> str:
        return instance.sold_by.get_full_name() or instance.sold_by.username


class CancelSaleSerializer(RejectServerFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
