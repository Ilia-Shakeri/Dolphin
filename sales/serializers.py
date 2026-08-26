from django.db import IntegrityError
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.access import crm_identities
from accounts.models import User
from common.phones import normalize_customer_phone
from common.serializers import RejectServerFieldsMixin
from sales.models import Customer, CustomerPhone, Interaction, Lead, LeadAssignmentHistory, PostalStatusHistory, Product, ProductCategory, Sale, SalesDocument, TargetAudienceMember
from sales.selectors import customers_for, leads_for, product_categories_for, products_for, sales_for, target_audience_for
from sales.services import add_target_audience_member, update_target_audience_member, create_customer_phone, create_customer_with_phone, create_lead, create_product, create_product_category, mark_sale, record_interaction, register_sales_document, update_customer, update_customer_phone, update_lead, update_product, update_product_category


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
    server_fields = {"created_by", "created_by_display", "is_active", "primary_phone", "kind_display", "created_at", "updated_at"}
    phone = CustomerPhoneInlineSerializer(write_only=True, required=False)
    kind = serializers.ChoiceField(choices=Customer.Kind.choices, required=False)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    #: Only an organisation has one, and only an official invoice requires it.
    #: Optional here so ordinary customer entry is not obstructed by a number
    #: most customers will never need.
    economic_code = serializers.CharField(required=False, allow_blank=True, max_length=32)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    primary_phone = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = ["id", "full_name", "kind", "kind_display", "national_id", "economic_code", "email", "province", "city", "postal_code", "category", "address", "notes", "created_by", "created_by_display", "is_active", "primary_phone", "phone", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_by_display", "is_active", "primary_phone", "kind_display", "created_at", "updated_at"]

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


class ProductCategorySerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"normalized_name", "is_active", "created_by", "created_by_display", "updated_by", "updated_by_display", "created_at", "updated_at"}
    code = serializers.CharField(max_length=64, validators=[])
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    created_by_display = serializers.SerializerMethodField()
    updated_by_display = serializers.SerializerMethodField()

    class Meta:
        model = ProductCategory
        fields = [
            "id", "code", "name", "description", "display_order", "is_active",
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
        return create_product_category(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        return update_product_category(
            actor=self.context["request"].user,
            category=instance,
            **validated_data,
        )


class ProductSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"category_name", "unit_display", "is_active", "created_by", "created_by_display", "updated_by", "updated_by_display", "created_at", "updated_at"}
    barcode = serializers.CharField(max_length=64, required=False, allow_blank=True, validators=[])
    #: The five units the panel offers, plus blank for products that predate the
    #: field. `unit_display` carries the Persian label so a reader never has to
    #: map the stored code themselves.
    unit = serializers.ChoiceField(
        choices=Product.Unit.choices, required=False, allow_blank=True
    )
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    updated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    created_by_display = serializers.SerializerMethodField()
    updated_by_display = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "sku", "name", "category", "category_name", "brand", "barcode", "unit", "unit_display", "current_price", "description", "is_active", "created_by", "created_by_display", "updated_by", "updated_by_display", "created_at", "updated_at"]
        read_only_fields = ["id", "category_name", "unit_display", "is_active", "created_by", "created_by_display", "updated_by", "updated_by_display", "created_at", "updated_at"]

    @staticmethod
    def _display(user) -> str:
        return user.get_full_name() or user.username

    def get_created_by_display(self, instance) -> str:
        return self._display(instance.created_by)

    def get_updated_by_display(self, instance) -> str:
        return self._display(instance.updated_by)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(
                self.fields["category"],
                product_categories_for(request.user).filter(is_active=True),
            )
        else:
            _scope_relation(self.fields["category"], ProductCategory.objects.none())

    def create(self, validated_data):
        return create_product(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        return update_product(actor=self.context["request"].user, product=instance, **validated_data)


class LeadSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer_name", "assigned_to", "assigned_to_display", "assigned_by", "assigned_at", "closed_at", "created_by", "source_payload", "created_at", "updated_at"}
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_to = serializers.PrimaryKeyRelatedField(read_only=True)
    assigned_by = serializers.PrimaryKeyRelatedField(read_only=True)
    # A campaign may name no customer, so this reads blank rather than failing.
    customer_name = serializers.CharField(
        source="customer.full_name", read_only=True, default=""
    )
    assigned_to_display = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = ["id", "customer", "customer_name", "source", "campaign_or_batch", "interested_product", "status", "assigned_to", "assigned_to_display", "assigned_by", "assigned_at", "next_follow_up_at", "closed_at", "created_by", "notes", "source_payload", "created_at", "updated_at"]
        read_only_fields = ["id", "customer_name", "assigned_to", "assigned_to_display", "assigned_by", "assigned_at", "closed_at", "created_by", "source_payload", "created_at", "updated_at"]

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


class TargetAudienceMemberSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    """One identity in a campaign's target audience.

    `status` accepts only the two values a person may set by hand. The other
    two are conclusions the system draws from real activity — a call logged, a
    customer record appearing — so offering them for write would let the list
    claim work that never happened. They are still returned on read.
    """

    server_fields = {"status", "normalized_phone", "customer", "created_by", "created_at", "updated_at"}
    # Read-only: an identity enters as a lead and moves on only when something
    # real happens to it — a call logged, a customer record appearing.
    status = serializers.CharField(read_only=True)
    normalized_phone = serializers.CharField(read_only=True)
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = TargetAudienceMember
        fields = [
            "id", "lead", "full_name", "raw_phone", "normalized_phone",
            "status", "status_display", "customer", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "normalized_phone", "status_display", "customer", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = leads_for(request.user) if request and request.user.is_authenticated else Lead.objects.none()
        _scope_relation(self.fields["lead"], queryset)

    def create(self, validated_data):
        return add_target_audience_member(actor=self.context["request"].user, **validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("lead", None)
        return update_target_audience_member(
            actor=self.context["request"].user, member=instance, **validated_data
        )


class CustomerImportResultSerializer(serializers.Serializer):
    """What one customer spreadsheet upload did, counted by outcome."""

    created = serializers.IntegerField(read_only=True)
    duplicates = serializers.IntegerField(read_only=True)
    invalid = serializers.IntegerField(read_only=True)
    errors = serializers.ListField(child=serializers.DictField(), read_only=True)


class ProductImportRowErrorSerializer(serializers.Serializer):
    row = serializers.IntegerField(read_only=True)
    detail = serializers.CharField(read_only=True)


class ProductImportResultSerializer(serializers.Serializer):
    """What one spreadsheet upload did, counted by outcome.

    The three counts are separate because they mean different things: `created`
    is work done, `duplicates` is work deliberately not done, and `invalid` is
    work that could not be done and needs the operator to look.
    """

    created = serializers.IntegerField(read_only=True)
    duplicates = serializers.IntegerField(read_only=True)
    invalid = serializers.IntegerField(read_only=True)
    errors = ProductImportRowErrorSerializer(many=True, read_only=True)


class ProductActivationSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """The one field the product activation endpoint accepts."""

    is_active = serializers.BooleanField()


class CustomerActivationSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """The one field the activation endpoint accepts."""

    is_active = serializers.BooleanField()


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
    # The call is logged against whoever was actually spoken to. Early in a
    # campaign that is a target-audience identity with no customer record, so
    # the displayed name falls back to the identity's own name.
    customer_name = serializers.SerializerMethodField()
    agent_display = serializers.SerializerMethodField()

    class Meta:
        model = Interaction
        fields = ["id", "lead", "customer", "customer_name", "target_member", "agent", "agent_display", "phone", "direction", "outcome", "occurred_at", "next_follow_up_at", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "customer", "customer_name", "agent", "agent_display", "created_at", "updated_at"]

    def get_customer_name(self, instance) -> str:
        if instance.customer_id:
            return instance.customer.full_name
        return instance.target_member.full_name if instance.target_member_id else ""

    def get_agent_display(self, instance) -> str:
        return instance.agent.get_full_name() or instance.agent.username

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        queryset = leads_for(request.user) if request and request.user.is_authenticated else Lead.objects.none()
        if request and request.user.is_authenticated and request.user.role == User.Role.SALES_AGENT:
            queryset = queryset.filter(assigned_to=request.user)
        _scope_relation(self.fields["lead"], queryset)
        # The identity picker offers only the audience of campaigns this user
        # may work, so a marketer searches within their own assignments.
        members = (
            target_audience_for(request.user)
            if request and request.user.is_authenticated
            else TargetAudienceMember.objects.none()
        )
        _scope_relation(self.fields["target_member"], members)

    def create(self, validated_data):
        return record_interaction(actor=self.context["request"].user, **validated_data)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and "lead" in attrs and attrs["lead"] != self.instance.lead:
            raise serializers.ValidationError({"lead": "Interaction lead cannot change."})
        return attrs


class SaleSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"customer", "customer_name", "campaign_name", "sold_by", "sold_by_display", "product_name", "unit_price_snapshot", "status", "created_at", "updated_at"}
    customer = serializers.PrimaryKeyRelatedField(read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    #: A "sale" is a campaign outcome in Client-1's language, so the list leads
    #: with the campaign rather than the customer.
    campaign_name = serializers.SerializerMethodField()
    sold_by = serializers.PrimaryKeyRelatedField(read_only=True)
    sold_by_display = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_price_snapshot = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)
    sold_at = serializers.DateTimeField(required=False, default=timezone.now)

    class Meta:
        model = Sale
        fields = ["id", "lead", "customer", "customer_name", "campaign_name", "sold_by", "sold_by_display", "product", "product_name", "quantity", "unit_price_snapshot", "total_amount", "status", "sold_at", "notes", "created_at", "updated_at"]
        read_only_fields = ["id", "customer", "customer_name", "campaign_name", "sold_by", "sold_by_display", "product_name", "unit_price_snapshot", "status", "created_at", "updated_at"]
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

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_campaign_name(self, obj):
        """The campaign this result came from.

        Falls back through the lead's own labels so the column is never blank
        for a record that does belong to a campaign.
        """
        lead = obj.lead
        if lead is None:
            return ""
        return lead.campaign_or_batch or lead.source or f"#{lead.pk}"

    def get_sold_by_display(self, instance) -> str:
        return instance.sold_by.get_full_name() or instance.sold_by.username


class CancelSaleSerializer(RejectServerFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class SalesDocumentSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {
        "customer_name", "province_snapshot", "city_snapshot", "postal_code_snapshot",
        "address_snapshot", "registered_at", "registered_by", "registered_by_display",
        "is_active", "created_at", "updated_at",
    }
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    document_number = serializers.CharField(max_length=64, validators=[])
    registered_by = serializers.PrimaryKeyRelatedField(read_only=True)
    registered_by_display = serializers.SerializerMethodField()

    class Meta:
        model = SalesDocument
        fields = [
            "id", "customer", "customer_name", "sale", "document_number",
            "province_snapshot", "city_snapshot", "postal_code_snapshot", "address_snapshot",
            "postal_status", "registered_at", "registered_by", "registered_by_display",
            "is_active", "notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "customer_name", "province_snapshot", "city_snapshot", "postal_code_snapshot",
            "address_snapshot", "registered_at", "registered_by", "registered_by_display",
            "is_active", "created_at", "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(self.fields["customer"], customers_for(request.user))
            _scope_relation(self.fields["sale"], sales_for(request.user))
        else:
            _scope_relation(self.fields["customer"], Customer.objects.none())
            _scope_relation(self.fields["sale"], Sale.objects.none())

    def get_registered_by_display(self, instance) -> str:
        return instance.registered_by.get_full_name() or instance.registered_by.username

    def create(self, validated_data):
        return register_sales_document(actor=self.context["request"].user, **validated_data)


class PostalStatusTransitionSerializer(RejectServerFieldsMixin, serializers.Serializer):
    to_status = serializers.CharField(max_length=80, trim_whitespace=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PostalStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_display = serializers.SerializerMethodField()

    class Meta:
        model = PostalStatusHistory
        fields = ["id", "document", "from_status", "to_status", "changed_by", "changed_by_display", "reason", "changed_at"]
        read_only_fields = fields

    def get_changed_by_display(self, instance) -> str:
        return instance.changed_by.get_full_name() or instance.changed_by.username
