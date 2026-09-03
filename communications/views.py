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
from communications import services
from communications.reports import build_inbound_sms_report, inbound_sms_drilldown
from communications.selectors import inbound_sms_for, outbound_sms_for
from communications.serializers import (
    InboundSMSDetailSerializer,
    InboundSMSDrilldownQuerySerializer,
    InboundSMSReportQuerySerializer,
    InboundSMSReportSerializer,
    OutboundSMSDetailSerializer,
    OutboundSMSSendSerializer,
)


class InboundSMSReportAccessMixin(FeatureGatedAPIMixin):
    required_feature = "inbound_sms"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def check_sms_access(self, request):
        if not has_any_capability(request.user, "sms.company"):
            raise PermissionDenied("دسترسی به گزارش پیامک‌های ورودی مجاز نیست.")


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


class OutboundSMSAccessMixin(FeatureGatedAPIMixin):
    required_feature = "outbound_sms"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]


class SendOutboundSMSView(OutboundSMSAccessMixin, APIView):
    @extend_schema(
        request=OutboundSMSSendSerializer,
        responses={
            200: OutboundSMSDetailSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Sends one SMS through this deployment's configured provider and "
            "records the outcome — sent or failed — as one OutboundSMS row. "
            "Object scope (which customer/lead a caller may name) is enforced "
            "in the request serializer; sending itself additionally requires "
            "the sms.company capability, checked in the service layer."
        ),
    )
    def post(self, request):
        serializer = OutboundSMSSendSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        message = services.send_outbound_sms(actor=request.user, **serializer.validated_data)
        response = Response(OutboundSMSDetailSerializer(message).data)
        response["Cache-Control"] = "private, no-store"
        return response


class OutboundSMSListView(OutboundSMSAccessMixin, APIView):
    @extend_schema(
        responses={
            200: OutboundSMSDetailSerializer(many=True),
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Paginated log of outbound SMS attempts, newest first, within the caller's sms.company scope.",
    )
    def get(self, request):
        queryset = outbound_sms_for(request.user)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(OutboundSMSDetailSerializer(page, many=True).data)
        response["Cache-Control"] = "private, no-store"
        return response

