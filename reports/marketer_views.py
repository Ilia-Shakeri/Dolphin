"""`GET reports/marketers/` — the marketer ranking (2.40.34, `reports.marketers`).

Feature `reports`, capability `reports.company` (company-wide figures; a
marketer's own figures are on their profile), sensitive-read throttle.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from reports.marketers import RANKINGS, build_marketer_ranking
from reports.services import InvalidReportPeriod, ReportAccessDenied


class MarketerRankingQuerySerializer(serializers.Serializer):
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    ordering = serializers.ChoiceField(choices=list(RANKINGS), required=False, default="sales_amount")


class MarketerRowSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    rank = serializers.IntegerField()
    previous_rank = serializers.IntegerField(allow_null=True)
    sales_count = serializers.IntegerField()
    sales_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    collected_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    average_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    customers_count = serializers.IntegerField()
    calls_count = serializers.IntegerField()
    leads_assigned = serializers.IntegerField()
    leads_completed = serializers.IntegerField()
    conversion_rate = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    share = serializers.DecimalField(max_digits=6, decimal_places=1)


class MarketerTotalsSerializer(serializers.Serializer):
    marketers = serializers.IntegerField()
    sales_count = serializers.IntegerField()
    sales_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    collected_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    customers_count = serializers.IntegerField()
    calls_count = serializers.IntegerField()


class OrderingSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class MarketerRankingSerializer(serializers.Serializer):
    period_start = serializers.CharField()
    period_end = serializers.CharField()
    ordering = serializers.CharField()
    orderings = OrderingSerializer(many=True)
    totals = MarketerTotalsSerializer()
    results = MarketerRowSerializer(many=True)


class MarketerRankingView(FeatureGatedAPIMixin, APIView):
    required_feature = "reports"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        parameters=[MarketerRankingQuerySerializer],
        responses={200: MarketerRankingSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "Every active marketer (Sales Agent, sales workstream) for a window: issued invoices they "
            "made (count, amount, collected, average), customers added, calls logged, leads assigned "
            "and completed. Ranked by `ordering` (competition ranking), with the rank each held over "
            "the window of equal length before. `reports.company` only."
        ),
    )
    def get(self, request):
        query = MarketerRankingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            report = build_marketer_ranking(actor=request.user, **query.validated_data)
        except ReportAccessDenied as exc:
            raise PermissionDenied("دسترسی به رتبه‌بندی بازاریاب‌ها مجاز نیست.") from exc
        except InvalidReportPeriod as exc:
            raise ValidationError({"period_end": "پایان بازه باید بعد از آغاز آن باشد."}) from exc
        return Response(MarketerRankingSerializer(report).data)
