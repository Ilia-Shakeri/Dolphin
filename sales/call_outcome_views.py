"""`/api/v1/call-outcomes/` and `/api/v1/do-not-contact/` (2.40.58, BIZ-003).

Settings → «نتیجهٔ تماس»: the outcome list, the company's own outcomes, matching
older calls, and the do-not-contact list. Everything here is a manager-side
correction under `customization.manage`; adding a company outcome needs the
`customization` feature as well (`sales.call_outcomes` checks both again).
Recording a call is not here — it is the call's own API.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from common.openapi import ACCESS_DENIED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, HasCapabilityForMethod, IsActiveAuthenticated
from common.serializers import RejectServerFieldsMixin
from common.throttles import SensitiveRateThrottle
from sales import call_outcomes
from sales.models import CallOutcome, DoNotContact


class OutcomeWriteSerializer(RejectServerFieldsMixin, serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True)
    standard_key = serializers.CharField(required=False, max_length=40)
    is_active = serializers.BooleanField(required=False)


class LegacyMapSerializer(RejectServerFieldsMixin, serializers.Serializer):
    text = serializers.CharField(max_length=80, allow_blank=True, trim_whitespace=False)
    result = serializers.CharField(max_length=40)


class LiftSerializer(RejectServerFieldsMixin, serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=True)


class OutcomeAccessMixin(FeatureGatedAPIMixin):
    required_feature = "leads"
    required_capabilities = (call_outcomes.CAPABILITY,)
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            throttles.append(SensitiveRateThrottle())
        return throttles


def _listing(user):
    payload = call_outcomes.outcomes_payload()
    payload["can_add"] = call_outcomes.can_configure(user)
    return payload


class CallOutcomeListView(OutcomeAccessMixin, APIView):
    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE},
                   description="Every outcome, standard and the company's own, with what each counts as.")
    def get(self, request):
        return Response(_listing(request.user))

    @extend_schema(request=OutcomeWriteSerializer,
                   responses={201: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE},
                   description="Adds a company outcome, counted in reports as the standard one it names.")
    def post(self, request):
        body = OutcomeWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        call_outcomes.create_outcome(
            actor=request.user, label=body.validated_data.get("label", ""),
            standard_key=body.validated_data.get("standard_key", ""),
        )
        return Response(_listing(request.user), status=201)


class CallOutcomeDetailView(OutcomeAccessMixin, APIView):
    @extend_schema(request=OutcomeWriteSerializer,
                   responses={200: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE})
    def patch(self, request, pk):
        outcome = CallOutcome.objects.filter(pk=pk).first()
        if outcome is None:
            raise NotFound()
        body = OutcomeWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        changes = dict(body.validated_data)
        if "standard_key" in changes:
            raise serializers.ValidationError({"standard_key": "نتیجهٔ استانداردی که یک نتیجه با آن شمرده می‌شود عوض نمی‌شود."})
        call_outcomes.update_outcome(actor=request.user, outcome=outcome, **changes)
        return Response(_listing(request.user))


class LegacyOutcomeView(OutcomeAccessMixin, APIView):
    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE},
                   description="The words older calls carry that are not matched to the list yet, with counts.")
    def get(self, request):
        return Response({"texts": call_outcomes.legacy_texts()})

    @extend_schema(request=LegacyMapSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request):
        body = LegacyMapSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        count = call_outcomes.map_legacy(actor=request.user, **body.validated_data)
        return Response({"mapped": count, "texts": call_outcomes.legacy_texts()})


def _serialize_block(row):
    user = row.created_by
    return {
        "id": row.pk, "phone": row.normalized_phone, "note": row.note, "interaction": row.interaction_id,
        "created_by_display": user.get_full_name() or user.username, "created_at": row.created_at.isoformat(),
    }


class DoNotContactListView(OutcomeAccessMixin, APIView):
    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE},
                   description="Numbers not to be called for marketing, newest first (at most 500).")
    def get(self, request):
        rows = DoNotContact.objects.filter(lifted_at__isnull=True).select_related("created_by")[:500]
        return Response({"results": [_serialize_block(row) for row in rows]})


class DoNotContactLiftView(OutcomeAccessMixin, APIView):
    @extend_schema(request=LiftSerializer, responses={200: dict, 400: VALIDATION_ERROR_RESPONSE})
    def post(self, request, pk):
        row = DoNotContact.objects.filter(pk=pk).first()
        if row is None:
            raise NotFound()
        body = LiftSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        call_outcomes.lift_block(actor=request.user, row=row, reason=body.validated_data["reason"])
        return Response({"lifted": True})
