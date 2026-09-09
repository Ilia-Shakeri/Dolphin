from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import has_any_capability
from common.deployment.profile import feature_enabled
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import (
    FeatureGatedAPIMixin,
    HasCapabilityForMethod,
    IsActiveAuthenticated,
    IsPlatformAdmin,
)
from common.throttles import SensitiveRateThrottle
from communications import services, sms
from communications.reports import build_inbound_sms_report, inbound_sms_drilldown
from communications.selectors import inbound_sms_for, outbound_sms_for
from communications.sms_provider_settings import get_sms_provider_settings, update_sms_provider_settings
from communications.serializers import (
    InboundSMSDetailSerializer,
    InboundSMSDrilldownQuerySerializer,
    InboundSMSReportQuerySerializer,
    InboundSMSReportSerializer,
    OutboundSMSDetailSerializer,
    OutboundSMSSendSerializer,
    SmsCampaignCreateSerializer,
    SmsCampaignSerializer,
    SmsProviderSettingsSerializer,
    SmsProviderSettingsUpdateSerializer,
    SmsTemplateCreateSerializer,
    SmsTemplateSerializer,
)
from communications.models import SmsCampaign, SmsTemplate


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
    """Feature, then role, then object scope — the three kept separate.

    `HasCapabilityForMethod` is here for the same reason
    `sales.permissions.HasSalesCapability` exists: without it a caller with
    no `sms.company` capability received `200` and an empty page, because
    `outbound_sms_for` returns an empty queryset for them. Never a leak — the
    boundary held — but inconsistent with the `/sms/` page itself, which
    answers `403` to exactly those callers, and with `users`,
    `activity-logs` and `inbound-sms`, which have always answered `403`.
    Someone without the capability is not asking for an empty log; they are
    asking for something that is not theirs.
    """

    required_feature = "outbound_sms"
    required_capabilities = ("sms.company",)
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]
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


class SmsProviderSettingsAccessMixin:
    """Feature, then role — the same two-gate shape `BrandSettingsView`/
    `DolphinBrandingSettingsView` already use for a Platform-Admin-only
    settings screen: 404 (not 403) when the deployment never turned the
    underlying module on at all, so a lower role or a deployment without the
    module sees no evidence the page exists.
    """

    required_feature = "outbound_sms"
    permission_classes = [IsPlatformAdmin]
    throttle_classes = [SensitiveRateThrottle]

    def initial(self, request, *args, **kwargs):
        if not feature_enabled(self.required_feature):
            raise NotFound()
        super().initial(request, *args, **kwargs)


class SmsProviderSettingsView(SmsProviderSettingsAccessMixin, APIView):
    """`/api/v1/sms-provider-settings/` — the settings page itself."""

    @extend_schema(
        responses={200: SmsProviderSettingsSerializer, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="This deployment's outbound SMS gateway configuration. token_password is never returned.",
    )
    def get(self, request):
        response = Response(SmsProviderSettingsSerializer(get_sms_provider_settings()).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=SmsProviderSettingsUpdateSerializer,
        responses={
            200: SmsProviderSettingsSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Updates any subset of the gateway configuration; every field is independent and optional.",
    )
    def post(self, request):
        serializer = SmsProviderSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        row = update_sms_provider_settings(actor=request.user, **serializer.validated_data)
        response = Response(SmsProviderSettingsSerializer(row).data)
        response["Cache-Control"] = "private, no-store"
        return response


class TestSmsProviderConnectionView(SmsProviderSettingsAccessMixin, APIView):
    """`/api/v1/sms-provider-settings/test/` — the settings page's own "تست
    اتصال" button. Tests the currently *saved* row (an admin saves, then
    tests) — never the request body, so this endpoint carries no risk of
    running a request built from unvalidated input.
    """

    @extend_schema(
        request=None,
        responses={200: dict, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "Calls the saved test_url (a GET) with whichever auth the saved row resolves to. "
            "Takes no request body — it tests the row already saved, not anything sent here. "
            "Returns {success, status_detail} — a failed test is a 200 with success: false, "
            "not an HTTP error, since the test itself succeeded at running."
        ),
    )
    def post(self, request):
        row = get_sms_provider_settings()
        result = sms.test_connectivity(sms.config_from_row(row))
        response = Response({"success": result.success, "status_detail": result.status_detail})
        response["Cache-Control"] = "private, no-store"
        return response


class SmsTemplateListCreateView(OutboundSMSAccessMixin, APIView):
    @extend_schema(
        responses={200: SmsTemplateSerializer(many=True), 403: ACCESS_DENIED_RESPONSE},
        description="Reusable message bodies for this deployment, newest title order.",
    )
    def get(self, request):
        templates = SmsTemplate.objects.all()
        response = Response(SmsTemplateSerializer(templates, many=True).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=SmsTemplateCreateSerializer,
        responses={
            201: SmsTemplateSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
        },
        description="Save one reusable message body. Requires the sms.company capability.",
    )
    def post(self, request):
        serializer = SmsTemplateCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        template = services.create_sms_template(actor=request.user, **serializer.validated_data)
        response = Response(SmsTemplateSerializer(template).data, status=201)
        response["Cache-Control"] = "private, no-store"
        return response


class SmsTemplateDeleteView(OutboundSMSAccessMixin, APIView):
    @extend_schema(
        responses={204: None, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
        description=(
            "Deletes one saved message body. Messages already sent from it keep "
            "their own copy of the text, so nothing already sent changes. POST "
            "rather than DELETE, matching every other mutation in this codebase."
        ),
    )
    def post(self, request, pk):
        services.delete_sms_template(actor=request.user, template_id=pk)
        response = Response(status=204)
        response["Cache-Control"] = "private, no-store"
        return response


class SmsCampaignListCreateView(OutboundSMSAccessMixin, APIView):
    """Group and scheduled sends.

    The listing also performs the small opportunistic flush described in
    `communications/services.py` — a deployment whose operator has not wired
    the `send_scheduled_sms` cron job yet still sends, because the page that
    shows campaigns also nudges a few of them along. Bounded hard
    (`SMS_CAMPAIGN_REQUEST_FLUSH_BATCH`) so opening this page can never turn
    into an unbounded run of provider calls inside one request.
    """

    @extend_schema(
        responses={200: SmsCampaignSerializer(many=True), 403: ACCESS_DENIED_RESPONSE},
        description="Paginated list of group/scheduled sends, newest scheduled time first.",
    )
    def get(self, request):
        services.dispatch_due_sms_campaigns(limit=services.SMS_CAMPAIGN_REQUEST_FLUSH_BATCH)
        queryset = (
            SmsCampaign.objects.all()
            .annotate(
                recipient_count=Count("recipients", distinct=True),
                sent_count=Count(
                    "recipients", filter=Q(recipients__state="sent"), distinct=True
                ),
                failed_count=Count(
                    "recipients", filter=Q(recipients__state="failed"), distinct=True
                ),
                pending_count=Count(
                    "recipients", filter=Q(recipients__state="pending"), distinct=True
                ),
            )
            .select_related("created_by")
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        response = paginator.get_paginated_response(SmsCampaignSerializer(page, many=True).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=SmsCampaignCreateSerializer,
        responses={
            201: SmsCampaignSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Queues one group or scheduled send. Nothing is sent in this "
            "request: recipients are dispatched by the send_scheduled_sms "
            "management command (cron) and by a small flush when the SMS page "
            "is opened. Object scope is enforced in the request serializer; "
            "sending additionally requires the sms.company capability."
        ),
    )
    def post(self, request):
        serializer = SmsCampaignCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        campaign = services.create_sms_campaign(
            actor=request.user,
            body=data["body"],
            scheduled_for=data.get("scheduled_for"),
            customer_ids=[customer.pk for customer in data.get("customers", [])],
            lead_ids=[lead.pk for lead in data.get("leads", [])],
            phones=data.get("phones", []),
        )
        # Send immediately when the caller asked for "now", so a group send is
        # not silently waiting on cron for its first message.
        if data.get("scheduled_for") is None:
            services.dispatch_due_sms_campaigns(limit=services.SMS_CAMPAIGN_REQUEST_FLUSH_BATCH)
        fresh = (
            SmsCampaign.objects.filter(pk=campaign.pk)
            .annotate(
                recipient_count=Count("recipients", distinct=True),
                sent_count=Count("recipients", filter=Q(recipients__state="sent"), distinct=True),
                failed_count=Count("recipients", filter=Q(recipients__state="failed"), distinct=True),
                pending_count=Count("recipients", filter=Q(recipients__state="pending"), distinct=True),
            )
            .select_related("created_by")
            .get()
        )
        response = Response(SmsCampaignSerializer(fresh).data, status=201)
        response["Cache-Control"] = "private, no-store"
        return response


class SmsCampaignCancelView(OutboundSMSAccessMixin, APIView):
    @extend_schema(
        responses={200: SmsCampaignSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
        description=(
            "Cancels the unsent remainder of a campaign. Anything already sent "
            "stays sent — this stops the queue, it does not recall messages."
        ),
    )
    def post(self, request, pk):
        services.cancel_sms_campaign(actor=request.user, campaign_id=pk)
        fresh = (
            SmsCampaign.objects.filter(pk=pk)
            .annotate(
                recipient_count=Count("recipients", distinct=True),
                sent_count=Count("recipients", filter=Q(recipients__state="sent"), distinct=True),
                failed_count=Count("recipients", filter=Q(recipients__state="failed"), distinct=True),
                pending_count=Count("recipients", filter=Q(recipients__state="pending"), distinct=True),
            )
            .select_related("created_by")
            .get()
        )
        response = Response(SmsCampaignSerializer(fresh).data)
        response["Cache-Control"] = "private, no-store"
        return response
