"""`/api/v1/after-sales-settings/` (2.40.60, BIZ-008): case types, stage
lists, deadlines, the working week and holidays.

Feature `after_sales`; `customization.manage`, checked again by
`aftersales.workflow`. Every answer is the whole settings payload, so the
tab redraws from what the server now holds.
"""

from django.utils.dateparse import parse_date
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from aftersales import workflow
from aftersales.models import CaseStage, CaseType, Holiday
from common.exceptions import BusinessRuleError
from common.openapi import ACCESS_DENIED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, HasCapabilityForMethod, IsActiveAuthenticated
from common.serializers import RejectServerFieldsMixin
from common.throttles import SensitiveRateThrottle


class TypeSerializer(RejectServerFieldsMixin, serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    default_priority = serializers.CharField(required=False, max_length=10)
    is_active = serializers.BooleanField(required=False)


class StageSerializer(RejectServerFieldsMixin, serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    case_type = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)


class CaseStageMoveSerializer(RejectServerFieldsMixin, serializers.Serializer):
    #: «up» or «down», checked by `aftersales.workflow`.
    direction = serializers.CharField(max_length=4)


class LimitSerializer(serializers.Serializer):
    value = serializers.IntegerField(required=False, allow_null=True)
    unit = serializers.CharField(max_length=4, required=False)


class PolicySerializer(RejectServerFieldsMixin, serializers.Serializer):
    priority = serializers.CharField(max_length=10)
    case_type = serializers.IntegerField(required=False, allow_null=True)
    response = LimitSerializer(required=False)
    plan = LimitSerializer(required=False)
    resolution = LimitSerializer(required=False)
    clear = serializers.BooleanField(required=False, default=False)


class CalendarSerializer(RejectServerFieldsMixin, serializers.Serializer):
    hours = serializers.DictField(required=False)
    skip_holidays = serializers.BooleanField(required=False)


class HolidaySerializer(RejectServerFieldsMixin, serializers.Serializer):
    day = serializers.CharField(max_length=10)
    title = serializers.CharField(max_length=120, allow_blank=True)


class AlertsSerializer(RejectServerFieldsMixin, serializers.Serializer):
    sms_alerts = serializers.BooleanField(required=False)
    escalate_overdue = serializers.BooleanField(required=False)
    survey_sms = serializers.BooleanField(required=False)
    survey_text = serializers.CharField(required=False, allow_blank=True, max_length=600)


class FixedHolidaysSerializer(RejectServerFieldsMixin, serializers.Serializer):
    jalali_year = serializers.IntegerField()


class SettingsAccessMixin(FeatureGatedAPIMixin):
    required_feature = "after_sales"
    required_capabilities = (workflow.CONFIGURE_CAPABILITY,)
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            throttles.append(SensitiveRateThrottle())
        return throttles

    @staticmethod
    def _one(model, pk):
        item = model.objects.filter(pk=pk).first()
        if item is None:
            raise NotFound()
        return item

    @staticmethod
    def _type(pk):
        if pk in (None, ""):
            return None
        item = CaseType.objects.filter(pk=pk).first()
        if item is None:
            raise BusinessRuleError({"case_type": "این نوع پرونده پیدا نشد."})
        return item


class AfterSalesSettingsView(SettingsAccessMixin, APIView):
    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        return Response(workflow.settings_payload())


class CaseTypeListView(SettingsAccessMixin, APIView):
    @extend_schema(request=TypeSerializer, responses={201: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request):
        body = TypeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        workflow.create_type(
            actor=request.user, label=body.validated_data.get("label", ""),
            default_priority=body.validated_data.get("default_priority", "normal"),
        )
        return Response(workflow.settings_payload(), status=201)


class CaseTypeDetailView(SettingsAccessMixin, APIView):
    @extend_schema(request=TypeSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def patch(self, request, pk):
        body = TypeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        workflow.update_type(actor=request.user, case_type=self._one(CaseType, pk), **body.validated_data)
        return Response(workflow.settings_payload())


class CaseTypeStagesView(SettingsAccessMixin, APIView):
    @extend_schema(request=None, responses={200: dict, 409: dict})
    def post(self, request, pk):
        workflow.give_type_own_stages(actor=request.user, case_type=self._one(CaseType, pk))
        return Response(workflow.settings_payload())


class CaseStageListView(SettingsAccessMixin, APIView):
    @extend_schema(request=StageSerializer, responses={201: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request):
        body = StageSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        workflow.create_stage(
            actor=request.user, label=body.validated_data.get("label", ""),
            case_type=self._type(body.validated_data.get("case_type")),
        )
        return Response(workflow.settings_payload(), status=201)


class CaseStageDetailView(SettingsAccessMixin, APIView):
    @extend_schema(request=StageSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def patch(self, request, pk):
        body = StageSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        changes = dict(body.validated_data)
        changes.pop("case_type", None)
        workflow.update_stage(actor=request.user, stage=self._one(CaseStage, pk), **changes)
        return Response(workflow.settings_payload())


class CaseStageMoveView(SettingsAccessMixin, APIView):
    @extend_schema(request=CaseStageMoveSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request, pk):
        body = CaseStageMoveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        workflow.move_stage(actor=request.user, stage=self._one(CaseStage, pk), **body.validated_data)
        return Response(workflow.settings_payload())


class SlaPolicyView(SettingsAccessMixin, APIView):
    @extend_schema(request=PolicySerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def put(self, request):
        body = PolicySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = dict(body.validated_data)
        workflow.set_policy(
            actor=request.user, priority=data["priority"], case_type=self._type(data.get("case_type")),
            response=data.get("response"), plan=data.get("plan"), resolution=data.get("resolution"),
            clear=data.get("clear", False),
        )
        return Response(workflow.settings_payload())


class CalendarView(SettingsAccessMixin, APIView):
    @extend_schema(request=CalendarSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def patch(self, request):
        body = CalendarSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        workflow.update_calendar(actor=request.user, **body.validated_data)
        return Response(workflow.settings_payload())


class HolidayListView(SettingsAccessMixin, APIView):
    @extend_schema(request=HolidaySerializer, responses={201: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request):
        body = HolidaySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        day = parse_date(body.validated_data["day"])
        if day is None:
            raise BusinessRuleError({"day": "روز را درست انتخاب کنید."})
        workflow.add_holiday(actor=request.user, day=day, title=body.validated_data["title"])
        return Response(workflow.settings_payload(), status=201)


class HolidayDetailView(SettingsAccessMixin, APIView):
    @extend_schema(request=None, responses={200: dict})
    def delete(self, request, pk):
        workflow.remove_holiday(actor=request.user, holiday=self._one(Holiday, pk))
        return Response(workflow.settings_payload())


class AlertsView(SettingsAccessMixin, APIView):
    """Deadline texts, escalation and the satisfaction survey (2.40.61)."""

    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        from aftersales.alerts import serialize_settings

        return Response(serialize_settings())

    @extend_schema(request=AlertsSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def patch(self, request):
        from aftersales.alerts import update_settings

        body = AlertsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        return Response(update_settings(actor=request.user, **body.validated_data))


class FixedHolidaysView(SettingsAccessMixin, APIView):
    @extend_schema(request=FixedHolidaysSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request):
        body = FixedHolidaysSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        added = workflow.add_fixed_holidays(actor=request.user, **body.validated_data)
        payload = workflow.settings_payload()
        payload["added"] = added
        return Response(payload)
