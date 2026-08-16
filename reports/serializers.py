from datetime import UTC

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers

from common.serializers import RejectServerFieldsMixin


class OffsetAwareDateTimeField(serializers.DateTimeField):
    def to_internal_value(self, value):
        parsed = parse_datetime(value) if isinstance(value, str) else None
        if parsed is None or timezone.is_naive(parsed):
            raise serializers.ValidationError(
                "Use an ISO 8601 timestamp with a timezone offset.",
                code="invalid",
            )
        return parsed.astimezone(UTC)


class UserPerformanceQuerySerializer(RejectServerFieldsMixin, serializers.Serializer):
    period_start = OffsetAwareDateTimeField(
        help_text="Inclusive ISO 8601 timestamp with a timezone offset.",
    )
    period_end = OffsetAwareDateTimeField(
        help_text="Exclusive ISO 8601 timestamp with a timezone offset.",
    )
    user_id = serializers.IntegerField(
        min_value=1,
        required=False,
        help_text="Optional user row. Sales Agents may select only themselves.",
    )
    sales_product_id = serializers.IntegerField(
        min_value=1,
        required=False,
        help_text="Optional exact Product ID applied only to Sale metrics.",
    )

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
            raise serializers.ValidationError(
                {"period_end": "Must be later than period_start."}
            )
        return attrs


class UserPerformanceDetailQuerySerializer(UserPerformanceQuerySerializer):
    metric = serializers.ChoiceField(
        choices=(
            "customers_created_count",
            "sales_count",
            "sales_amount",
            "average_sale_amount",
        ),
        required=True,
    )
    page = serializers.IntegerField(min_value=1, required=False, default=1)


class UserPerformanceDetailRowSerializer(serializers.Serializer):
    record_type = serializers.ChoiceField(choices=("customer", "sale"))
    id = serializers.IntegerField(min_value=1)
    title = serializers.CharField()
    owner = serializers.CharField()
    occurred_at = serializers.DateTimeField()
    amount = serializers.DecimalField(max_digits=38, decimal_places=2, allow_null=True, coerce_to_string=True)
    product_name = serializers.CharField(allow_blank=True)
    detail_url = serializers.CharField()


class UserPerformanceRowSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    customers_created_count = serializers.IntegerField(min_value=0)
    sales_count = serializers.IntegerField(min_value=0)
    sales_amount = serializers.DecimalField(
        max_digits=38,
        decimal_places=2,
        coerce_to_string=True,
    )
    average_sale_amount = serializers.DecimalField(
        max_digits=38,
        decimal_places=2,
        coerce_to_string=True,
    )


class UserPerformanceSummarySerializer(serializers.Serializer):
    customers_created_count = serializers.IntegerField(min_value=0)
    sales_count = serializers.IntegerField(min_value=0)
    sales_amount = serializers.DecimalField(max_digits=38, decimal_places=2, coerce_to_string=True)
    average_sale_amount = serializers.DecimalField(max_digits=38, decimal_places=2, coerce_to_string=True)


class UserPerformanceReportSerializer(serializers.Serializer):
    period_start = serializers.CharField()
    period_end = serializers.CharField()
    user_id = serializers.IntegerField(allow_null=True)
    sales_product_id = serializers.IntegerField(allow_null=True)
    summary = UserPerformanceSummarySerializer()
    results = UserPerformanceRowSerializer(many=True)


class SalesDocumentReportQuerySerializer(RejectServerFieldsMixin, serializers.Serializer):
    period_start = OffsetAwareDateTimeField(help_text="Inclusive registration timestamp.")
    period_end = OffsetAwareDateTimeField(help_text="Exclusive registration timestamp.")
    province = serializers.CharField(max_length=100, required=False)
    city = serializers.CharField(max_length=100, required=False)
    postal_status = serializers.CharField(max_length=80, required=False)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)

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
        return attrs


class SalesDocumentGeographyRowSerializer(serializers.Serializer):
    province = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    count = serializers.IntegerField(min_value=0)


class SalesDocumentPostalStatusRowSerializer(serializers.Serializer):
    postal_status = serializers.CharField()
    count = serializers.IntegerField(min_value=0)


class SalesDocumentReportSerializer(serializers.Serializer):
    period_start = serializers.CharField()
    period_end = serializers.CharField()
    filters = serializers.DictField()
    total = serializers.IntegerField(min_value=0)
    by_geography = SalesDocumentGeographyRowSerializer(many=True)
    by_postal_status = SalesDocumentPostalStatusRowSerializer(many=True)


# --- Financial reports -------------------------------------------------------
# These read stored invoice, allocation, and stock rows only. Amounts are
# serialised as strings so no client rounds a currency value through a float.

MONEY = {"max_digits": 38, "decimal_places": 2, "coerce_to_string": True}


class ReceivablesQuerySerializer(RejectServerFieldsMixin, serializers.Serializer):
    customer_id = serializers.IntegerField(
        min_value=1, required=False, help_text="Optional exact Customer ID inside actor scope."
    )


class ReceivablesRowSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField(min_value=1)
    customer_name = serializers.CharField()
    invoice_count = serializers.IntegerField(min_value=0)
    total_outstanding = serializers.DecimalField(**MONEY)
    not_due = serializers.DecimalField(**MONEY)
    days_1_30 = serializers.DecimalField(**MONEY)
    days_31_60 = serializers.DecimalField(**MONEY)
    days_61_90 = serializers.DecimalField(**MONEY)
    days_over_90 = serializers.DecimalField(**MONEY)


class ReceivablesBucketSerializer(serializers.Serializer):
    not_due = serializers.DecimalField(**MONEY)
    days_1_30 = serializers.DecimalField(**MONEY)
    days_31_60 = serializers.DecimalField(**MONEY)
    days_61_90 = serializers.DecimalField(**MONEY)
    days_over_90 = serializers.DecimalField(**MONEY)


class ReceivablesReportSerializer(serializers.Serializer):
    as_of = serializers.CharField()
    total_outstanding = serializers.DecimalField(**MONEY)
    buckets = ReceivablesBucketSerializer()
    results = ReceivablesRowSerializer(many=True)


class ProfitQuerySerializer(RejectServerFieldsMixin, serializers.Serializer):
    period_start = OffsetAwareDateTimeField(help_text="Inclusive invoice issue timestamp.")
    period_end = OffsetAwareDateTimeField(help_text="Exclusive invoice issue timestamp.")
    customer_id = serializers.IntegerField(
        min_value=1, required=False, help_text="Optional exact Customer ID inside actor scope."
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["period_end"] <= attrs["period_start"]:
            raise serializers.ValidationError({"period_end": "Must be later than period_start."})
        return attrs


class ProfitRowSerializer(serializers.Serializer):
    invoice_id = serializers.IntegerField(min_value=1)
    number = serializers.CharField()
    customer_id = serializers.IntegerField(min_value=1)
    customer_name = serializers.CharField()
    issued_at = serializers.CharField()
    revenue = serializers.DecimalField(**MONEY)
    cost = serializers.DecimalField(**MONEY)
    profit = serializers.DecimalField(**MONEY)
    margin_percent = serializers.DecimalField(max_digits=8, decimal_places=2, coerce_to_string=True)


class ProfitReportSerializer(serializers.Serializer):
    period_start = serializers.CharField()
    period_end = serializers.CharField()
    revenue = serializers.DecimalField(**MONEY)
    cost = serializers.DecimalField(**MONEY)
    profit = serializers.DecimalField(**MONEY)
    margin_percent = serializers.DecimalField(max_digits=8, decimal_places=2, coerce_to_string=True)
    measured_invoice_count = serializers.IntegerField(min_value=0)
    # Invoices issued with no cost snapshot. Reported separately rather than
    # folded in at zero cost, which would overstate profit.
    unmeasured_invoice_count = serializers.IntegerField(min_value=0)
    results = ProfitRowSerializer(many=True)


class InventoryValuationQuerySerializer(RejectServerFieldsMixin, serializers.Serializer):
    warehouse_id = serializers.IntegerField(
        min_value=1, required=False, help_text="Optional exact Warehouse ID."
    )


class ValuationRowSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField(min_value=1)
    warehouse_name = serializers.CharField()
    product_id = serializers.IntegerField(min_value=1)
    product_sku = serializers.CharField()
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()
    average_cost = serializers.DecimalField(**MONEY)
    stock_value = serializers.DecimalField(**MONEY)


class InventoryValuationReportSerializer(serializers.Serializer):
    as_of = serializers.CharField()
    total_quantity = serializers.IntegerField()
    total_value = serializers.DecimalField(**MONEY)
    results = ValuationRowSerializer(many=True)
