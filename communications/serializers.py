from datetime import timedelta

from rest_framework import serializers

from common.serializers import RejectServerFieldsMixin
from communications.models import InboundSMS, OutboundSMS
from reports.serializers import OffsetAwareDateTimeField
from sales.models import Customer, Lead
from sales.selectors import customers_for, leads_for


class InboundSMSReportQuerySerializer(RejectServerFieldsMixin, serializers.Serializer):
    period_start = OffsetAwareDateTimeField(help_text="Inclusive provider-received timestamp.")
    period_end = OffsetAwareDateTimeField(help_text="Exclusive provider-received timestamp.")
    provider_code = serializers.RegexField(r"^[a-z0-9][a-z0-9_-]{0,49}$", required=False)
    recipient_normalized = serializers.RegexField(r"^\+[1-9][0-9]{7,14}$", required=False)
    processing_state = serializers.ChoiceField(choices=InboundSMS.ProcessingState.choices, required=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        getlist = getattr(self.initial_data, "getlist", None)
        if getlist:
            repeated = sorted(name for name in self.initial_data if len(getlist(name)) > 1)
            if repeated:
                raise serializers.ValidationError(
                    {name: "این پارامتر باید فقط یک‌بار وارد شود." for name in repeated}
                )
        if attrs["period_end"] <= attrs["period_start"]:
            raise serializers.ValidationError({"period_end": "باید پس از تاریخ شروع دوره باشد."})
        if attrs["period_end"] - attrs["period_start"] > timedelta(days=366):
            raise serializers.ValidationError({"period_end": "بازه گزارش نمی‌تواند بیش از ۳۶۶ روز باشد."})
        return attrs


class InboundSMSDrilldownQuerySerializer(InboundSMSReportQuerySerializer):
    local_date = serializers.DateField(required=True)
    local_hour = serializers.IntegerField(min_value=0, max_value=23, required=True)
    page = serializers.IntegerField(min_value=1, required=False, default=1)


class InboundSMSAggregateRowSerializer(serializers.Serializer):
    local_date = serializers.DateField()
    local_hour = serializers.IntegerField(min_value=0, max_value=23)
    inbound_sms_count = serializers.IntegerField(min_value=0)


class InboundSMSReportSerializer(serializers.Serializer):
    period_start = serializers.CharField()
    period_end = serializers.CharField()
    timezone = serializers.CharField()
    filters = serializers.DictField()
    total = serializers.IntegerField(min_value=0)
    results = InboundSMSAggregateRowSerializer(many=True)


class InboundSMSDetailSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", allow_null=True, read_only=True)
    lead_label = serializers.SerializerMethodField()

    class Meta:
        model = InboundSMS
        fields = (
            "id",
            "provider_code",
            "external_message_id",
            "sender_normalized",
            "recipient_normalized",
            "provider_received_at",
            "system_received_at",
            "direction",
            "metadata",
            "body_retention_policy",
            "processing_state",
            "customer",
            "customer_name",
            "lead",
            "lead_label",
        )
        read_only_fields = fields

    def get_lead_label(self, instance) -> str | None:
        if not instance.lead:
            return None
        return instance.lead.source or f"سرنخ {instance.lead_id}"


def _scope_relation(field, queryset):
    field.queryset = queryset
    field.error_messages["does_not_exist"] = "Invalid object."


class OutboundSMSSendSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """What a caller supplies to send one SMS.

    Exactly one of `customer`, `lead` or `phone` names the recipient — never
    a bare phone alongside a customer, which would leave it ambiguous which
    number `send_outbound_sms` should actually use. `customer` and `lead` are
    scoped to what the requesting user may already see (`customers_for`/
    `leads_for`, the same object-scope selectors every other write in this
    codebase goes through), so this cannot be used to probe for the
    existence of a row outside that scope.
    """

    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.none(), required=False, allow_null=True)
    lead = serializers.PrimaryKeyRelatedField(queryset=Lead.objects.none(), required=False, allow_null=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    body = serializers.CharField(max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            _scope_relation(self.fields["customer"], customers_for(request.user))
            _scope_relation(self.fields["lead"], leads_for(request.user))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        named = [name for name in ("customer", "lead", "phone") if attrs.get(name)]
        if len(named) > 1:
            raise serializers.ValidationError(
                {"phone": "فقط یکی از مشتری، سرنخ یا شماره را مشخص کنید."}
            )
        if not named:
            raise serializers.ValidationError(
                {"phone": "گیرنده الزامی است: مشتری، سرنخ یا شماره تلفن."}
            )
        return attrs


class OutboundSMSDetailSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", allow_null=True, read_only=True)
    lead_label = serializers.SerializerMethodField()
    sent_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OutboundSMS
        fields = (
            "id",
            "provider_code",
            "recipient_normalized",
            "body_text",
            "status",
            "status_detail",
            "customer",
            "customer_name",
            "lead",
            "lead_label",
            "sent_by_name",
            "sent_at",
        )
        read_only_fields = fields

    def get_lead_label(self, instance) -> str | None:
        if not instance.lead:
            return None
        return instance.lead.source or f"سرنخ {instance.lead_id}"

    def get_sent_by_name(self, instance) -> str:
        if not instance.sent_by:
            return ""
        return instance.sent_by.get_full_name() or instance.sent_by.username
