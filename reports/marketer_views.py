"""`GET reports/marketers/` — the marketer ranking (2.40.34, `reports.marketers`).

Feature `reports`, capability `reports.company` (company-wide figures; a
marketer's own figures are on their profile), sensitive-read throttle.

`GET exports/marketers.xlsx` (2.40.41) is the same view's report as a
workbook: it subclasses the JSON view, so the gate, the capability, the query
and the builder are literally the same code.
"""

from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from reports.financial_views import FinancialExportMixin
from reports.marketers import RANKINGS, build_marketer_ranking, marketers_queryset
from reports.services import InvalidReportPeriod, ReportAccessDenied
from reports.targets import build_monthly_targets, current_month
from reports.xlsx import XLSX_CONTENT_TYPE, build_marketer_ranking_workbook
from sales.targets import set_monthly_targets


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
    successful_calls = serializers.IntegerField()
    qualified_calls = serializers.IntegerField()
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
    successful_calls = serializers.IntegerField()
    qualified_calls = serializers.IntegerField()


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
        return Response(MarketerRankingSerializer(self.build(request)).data)

    def build(self, request):
        query = MarketerRankingQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            return build_marketer_ranking(actor=request.user, **query.validated_data)
        except ReportAccessDenied as exc:
            raise PermissionDenied("دسترسی به رتبه‌بندی بازاریاب‌ها مجاز نیست.") from exc
        except InvalidReportPeriod as exc:
            raise ValidationError({"period_end": "پایان بازه باید بعد از آغاز آن باشد."}) from exc


class MarketerRankingExportView(FinancialExportMixin, MarketerRankingView):
    workbook_builder = staticmethod(build_marketer_ranking_workbook)
    filename = "dolphin-marketers.xlsx"

    @extend_schema(
        parameters=[MarketerRankingQuerySerializer],
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="The marketer ranking for the same window and ordering, as a workbook.",
            ),
            (400, "application/json"): VALIDATION_ERROR_RESPONSE,
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description="Exports the same ranked rows and totals as the JSON marketer ranking.",
    )
    def get(self, request):
        return self.export(request)


class MonthQuerySerializer(serializers.Serializer):
    year = serializers.IntegerField(required=False, min_value=1200, max_value=1700)
    month = serializers.IntegerField(required=False, min_value=1, max_value=12)

    def validate(self, attrs):
        if ("year" in attrs) != ("month" in attrs):
            raise serializers.ValidationError({"month": "سال و ماه را با هم بفرستید."})
        return attrs


class TargetEntrySerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=0, required=False, allow_null=True)


class TargetsWriteSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=1200, max_value=1700)
    month = serializers.IntegerField(min_value=1, max_value=12)
    targets = TargetEntrySerializer(many=True, allow_empty=False, max_length=500)


class TargetRowSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    target = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    achieved = serializers.DecimalField(max_digits=20, decimal_places=2)
    percent = serializers.DecimalField(max_digits=8, decimal_places=1, allow_null=True)


class TargetTotalsSerializer(serializers.Serializer):
    target = serializers.DecimalField(max_digits=22, decimal_places=2)
    achieved = serializers.DecimalField(max_digits=22, decimal_places=2)
    percent = serializers.DecimalField(max_digits=8, decimal_places=1, allow_null=True)
    with_target = serializers.IntegerField()


class MonthlyTargetsSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    label = serializers.CharField()
    period_start = serializers.CharField()
    period_end = serializers.CharField()
    can_manage = serializers.BooleanField()
    totals = TargetTotalsSerializer()
    results = TargetRowSerializer(many=True)


class MarketerTargetsView(FeatureGatedAPIMixin, APIView):
    """`GET/PUT reports/marketers/targets/` — monthly sales targets (2.40.41).

    GET: every marketer's target and what they sold in a Jalali month (this
    month when none is given). PUT: set the month's targets in one go — an
    empty or zero amount clears one. Feature `reports`; reading needs
    `reports.company`, writing `sales_targets.manage`.
    """

    required_feature = "reports"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def _report(self, request, year, month):
        try:
            return build_monthly_targets(actor=request.user, year=year, month=month)
        except ReportAccessDenied as exc:
            raise PermissionDenied("دسترسی به هدف‌های فروش مجاز نیست.") from exc

    @extend_schema(
        parameters=[MonthQuerySerializer],
        responses={200: MonthlyTargetsSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
    )
    def get(self, request):
        query = MonthQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        year, month = (query.validated_data["year"], query.validated_data["month"]) if query.validated_data else current_month(timezone.now())
        return Response(MonthlyTargetsSerializer(self._report(request, year, month)).data)

    @extend_schema(
        request=TargetsWriteSerializer,
        responses={200: MonthlyTargetsSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
    )
    def put(self, request):
        body = TargetsWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        set_monthly_targets(
            actor=request.user, year=data["year"], month=data["month"],
            targets=[dict(entry) for entry in data["targets"]], marketers=marketers_queryset(),
        )
        return Response(MonthlyTargetsSerializer(self._report(request, data["year"], data["month"])).data)
