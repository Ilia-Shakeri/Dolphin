from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import has_any_capability
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from communications.reports import build_inbound_sms_report, inbound_sms_drilldown
from communications.selectors import inbound_sms_for
from communications.serializers import (
    InboundSMSDetailSerializer,
    InboundSMSDrilldownQuerySerializer,
    InboundSMSReportQuerySerializer,
    InboundSMSReportSerializer,
)


class InboundSMSReportAccessMixin(FeatureGatedAPIMixin):
    required_feature = "inbound_sms"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def check_sms_access(self, request):
        if not has_any_capability(request.user, "sms.company"):
            raise PermissionDenied("Inbound SMS report access is not allowed.")


class InboundSMSReportView(InboundSMSReportAccessMixin, APIView):
    @extend_schema(
        parameters=[InboundSMSReportQuerySerializer],
        responses={
            200: InboundSMSReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Counts stored provider-neutral inbound SMS records by Asia/Tehran local date and hour. "
            "No public provider ingestion endpoint is exposed."
        ),
    )
    def get(self, request):
        self.check_sms_access(request)
        serializer = InboundSMSReportQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        report = build_inbound_sms_report(actor=request.user, **serializer.validated_data)
        response = Response(InboundSMSReportSerializer(report).data)
        response["Cache-Control"] = "private, no-store"
        return response


class InboundSMSDrilldownView(InboundSMSReportAccessMixin, APIView):
    @extend_schema(
        parameters=[InboundSMSDrilldownQuerySerializer],
        responses={
            200: InboundSMSDetailSerializer(many=True),
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Returns paginated records behind one authorized Asia/Tehran date/hour aggregate.",
    )
    def get(self, request):
        self.check_sms_access(request)
        serializer = InboundSMSDrilldownQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        values.pop("page", None)
        queryset = inbound_sms_drilldown(actor=request.user, **values)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(InboundSMSDetailSerializer(page, many=True).data)
        response["Cache-Control"] = "private, no-store"
        return response


class InboundSMSMessageDetailView(InboundSMSReportAccessMixin, APIView):
    @extend_schema(
        responses={
            200: InboundSMSDetailSerializer,
            403: ACCESS_DENIED_RESPONSE,
            404: None,
            429: THROTTLED_RESPONSE,
        },
        description="Returns one stored inbound SMS row inside the same authorized company scope.",
    )
    def get(self, request, message_id):
        self.check_sms_access(request)
        message = get_object_or_404(inbound_sms_for(request.user), pk=message_id)
        response = Response(InboundSMSDetailSerializer(message).data)
        response["Cache-Control"] = "private, no-store"
        return response

