from datetime import timedelta

from rest_framework import serializers

from common.serializers import RejectServerFieldsMixin
from communications.models import InboundSMS
from reports.serializers import OffsetAwareDateTimeField


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
                    {name: "Query parameter must appear once." for name in repeated}
                )
        if attrs["period_end"] <= attrs["period_start"]:
            raise serializers.ValidationError({"period_end": "Must be later than period_start."})
        if attrs["period_end"] - attrs["period_start"] > timedelta(days=366):
            raise serializers.ValidationError({"period_end": "Report period may not exceed 366 days."})
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
