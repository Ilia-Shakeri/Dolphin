"""API for the receivables, profit, and stock valuation reports.

Each report exposes the same pair the user-performance report already
establishes: a JSON view and an XLSX export that take identical parameters and
produce identical numbers, so an exported file can never disagree with the
screen it was exported from.

Three controls apply, unchanged and separate: the deployment feature gate
(404 when this deployment does not run the module), the `reports.company`
capability (403 for anyone else, including a Sales Agent with `reports.own`),
and the underlying selectors' object scope.
"""

from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import has_any_capability
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from reports.financial import (
    InvalidProfitPeriod,
    build_inventory_valuation_report,
    build_profit_report,
    build_receivables_report,
)
from reports.serializers import (
    InventoryValuationQuerySerializer,
    InventoryValuationReportSerializer,
    ProfitQuerySerializer,
    ProfitReportSerializer,
    ReceivablesQuerySerializer,
    ReceivablesReportSerializer,
)
from reports.services import ReportAccessDenied
from reports.views import XLSXNegotiationRenderer
from reports.xlsx import (
    XLSX_CONTENT_TYPE,
    build_inventory_valuation_workbook,
    build_profit_workbook,
    build_receivables_workbook,
)


class FinancialReportMixin(FeatureGatedAPIMixin):
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]
    query_serializer_class = None
    builder = None

    def build(self, request):
        if not has_any_capability(request.user, "reports.company"):
            raise PermissionDenied("دسترسی به گزارش‌ها مجاز نیست.")
        serializer = self.query_serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            return type(self).builder(actor=request.user, **serializer.validated_data)
        except InvalidProfitPeriod as exc:
            raise ValidationError({"period_end": "بازه گزارش نامعتبر است."}) from exc
        except ReportAccessDenied as exc:
            raise PermissionDenied("دسترسی به گزارش‌ها مجاز نیست.") from exc


class FinancialExportMixin:
    """Serve XLSX on success and JSON on error, like the performance export."""

    renderer_classes = [XLSXNegotiationRenderer]
    workbook_builder = None
    filename = "dolphin-report.xlsx"

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if isinstance(response, Response) and response.status_code >= 400:
            renderer = JSONRenderer()
            response.accepted_renderer = renderer
            response.accepted_media_type = renderer.media_type
            response.content_type = renderer.media_type
        return response

    def export(self, request):
        report = self.build(request)
        response = HttpResponse(
            type(self).workbook_builder(report), content_type=XLSX_CONTENT_TYPE
        )
        response["Content-Disposition"] = f'attachment; filename="{self.filename}"'
        response["Cache-Control"] = "private, no-store"
        return response


def _json(report, serializer_class):
    response = Response(serializer_class(report).data)
    response["Cache-Control"] = "private, no-store"
    return response


class ReceivablesReportView(FinancialReportMixin, APIView):
    required_feature = "invoices"
    query_serializer_class = ReceivablesQuerySerializer
    builder = staticmethod(build_receivables_report)

    @extend_schema(
        parameters=[ReceivablesQuerySerializer],
        responses={
            200: ReceivablesReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Outstanding balance of every issued invoice, grouped by customer and aged into "
            "not-yet-due plus 1-30, 31-60, 61-90 and over-90 days past due."
        ),
    )
    def get(self, request):
        return _json(self.build(request), ReceivablesReportSerializer)


class ReceivablesExportView(FinancialExportMixin, ReceivablesReportView):
    workbook_builder = staticmethod(build_receivables_workbook)
    filename = "dolphin-receivables.xlsx"

    @extend_schema(
        parameters=[ReceivablesQuerySerializer],
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="Receivables aging workbook."
            ),
            (400, "application/json"): VALIDATION_ERROR_RESPONSE,
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description="Exports the same scoped rows and totals as the JSON receivables report.",
    )
    def get(self, request):
        return self.export(request)


class ProfitReportView(FinancialReportMixin, APIView):
    required_feature = "invoices"
    query_serializer_class = ProfitQuerySerializer
    builder = staticmethod(build_profit_report)

    @extend_schema(
        parameters=[ProfitQuerySerializer],
        responses={
            200: ProfitReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Gross profit of invoices issued in the period, measured against the unit cost "
            "snapshotted at issue. Invoices issued without a cost snapshot are counted "
            "separately and excluded from the totals rather than treated as costing nothing."
        ),
    )
    def get(self, request):
        return _json(self.build(request), ProfitReportSerializer)


class ProfitExportView(FinancialExportMixin, ProfitReportView):
    workbook_builder = staticmethod(build_profit_workbook)
    filename = "dolphin-profit.xlsx"

    @extend_schema(
        parameters=[ProfitQuerySerializer],
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="Profit workbook."
            ),
            (400, "application/json"): VALIDATION_ERROR_RESPONSE,
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description="Exports the same scoped rows and totals as the JSON profit report.",
    )
    def get(self, request):
        return self.export(request)


class InventoryValuationReportView(FinancialReportMixin, APIView):
    required_feature = "inventory"
    query_serializer_class = InventoryValuationQuerySerializer
    builder = staticmethod(build_inventory_valuation_report)

    @extend_schema(
        parameters=[InventoryValuationQuerySerializer],
        responses={
            200: InventoryValuationReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Stock on hand valued at the moving average cost the movement ledger produced. "
            "No revaluation policy is applied."
        ),
    )
    def get(self, request):
        return _json(self.build(request), InventoryValuationReportSerializer)


class InventoryValuationExportView(FinancialExportMixin, InventoryValuationReportView):
    workbook_builder = staticmethod(build_inventory_valuation_workbook)
    filename = "dolphin-stock-valuation.xlsx"

    @extend_schema(
        parameters=[InventoryValuationQuerySerializer],
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY, description="Stock valuation workbook."
            ),
            (400, "application/json"): VALIDATION_ERROR_RESPONSE,
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description="Exports the same scoped rows and totals as the JSON valuation report.",
    )
    def get(self, request):
        return self.export(request)
