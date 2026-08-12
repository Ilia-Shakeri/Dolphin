from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from reports.serializers import (
    SalesDocumentReportQuerySerializer,
    SalesDocumentReportSerializer,
    UserPerformanceQuerySerializer,
    UserPerformanceReportSerializer,
)
from reports.services import (
    InvalidReportPeriod,
    InvalidReportUser,
    ReportAccessDenied,
    build_sales_document_report,
    build_user_performance_report,
)
from reports.xlsx import XLSX_CONTENT_TYPE, build_user_performance_workbook


class XLSXNegotiationRenderer(JSONRenderer):
    media_type = XLSX_CONTENT_TYPE
    format = "xlsx"


class UserPerformanceReportMixin:
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def get_report(self, request):
        serializer = UserPerformanceQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            return build_user_performance_report(
                actor=request.user,
                **serializer.validated_data,
            )
        except InvalidReportUser as exc:
            raise ValidationError({"user_id": "Invalid user."}) from exc
        except InvalidReportPeriod as exc:
            raise ValidationError({"period_end": "Invalid report period."}) from exc
        except ReportAccessDenied as exc:
            raise PermissionDenied("Report access is not allowed.") from exc


class UserPerformanceReportView(UserPerformanceReportMixin, APIView):
    @extend_schema(
        parameters=[UserPerformanceQuerySerializer],
        responses={
            200: UserPerformanceReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Returns exact per-user Customer creation and confirmed Sale metrics. "
            "period_start is inclusive, period_end is exclusive, and sales_product_id "
            "changes only Sale metrics."
        ),
    )
    def get(self, request):
        report = self.get_report(request)
        response = Response(UserPerformanceReportSerializer(report).data)
        response["Cache-Control"] = "private, no-store"
        return response


class SalesDocumentReportView(APIView):
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        parameters=[SalesDocumentReportQuerySerializer],
        responses={
            200: SalesDocumentReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Counts scoped internal sales documents by snapshotted geography "
            "and current postal status. Registration start is inclusive and end is exclusive."
        ),
    )
    def get(self, request):
        serializer = SalesDocumentReportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            report = build_sales_document_report(actor=request.user, **serializer.validated_data)
        except InvalidReportPeriod as exc:
            raise ValidationError({"period_end": "Invalid report period."}) from exc
        except ReportAccessDenied as exc:
            raise PermissionDenied("Report access is not allowed.") from exc
        response = Response(SalesDocumentReportSerializer(report).data)
        response["Cache-Control"] = "private, no-store"
        return response


class UserPerformanceExportView(UserPerformanceReportMixin, APIView):
    renderer_classes = [XLSXNegotiationRenderer]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if isinstance(response, Response) and response.status_code >= 400:
            renderer = JSONRenderer()
            response.accepted_renderer = renderer
            response.accepted_media_type = renderer.media_type
            response.content_type = renderer.media_type
        return response

    @extend_schema(
        parameters=[UserPerformanceQuerySerializer],
        responses={
            (200, XLSX_CONTENT_TYPE): OpenApiResponse(
                response=OpenApiTypes.BINARY,
                description="Filtered user-performance XLSX workbook.",
            ),
            (400, "application/json"): VALIDATION_ERROR_RESPONSE,
            (403, "application/json"): ACCESS_DENIED_RESPONSE,
            (429, "application/json"): THROTTLED_RESPONSE,
        },
        description="Exports the same scoped result and filters as the JSON report.",
    )
    def get(self, request):
        report = self.get_report(request)
        response = HttpResponse(
            build_user_performance_workbook(report),
            content_type=XLSX_CONTENT_TYPE,
        )
        response["Content-Disposition"] = 'attachment; filename="kariz-user-performance.xlsx"'
        response["Cache-Control"] = "private, no-store"
        return response
