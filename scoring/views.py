"""`/api/v1/scoring-settings/` — the factor weights, Platform Admin only (2.20.0)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsPlatformAdmin
from common.serializers import RejectServerFieldsMixin
from common.throttles import SensitiveRateThrottle
from scoring.services import strategy_for, update_weights, weights_for


def catalog():
    """Every factor of both person types, with its default and current weight."""
    result = {}
    for person_type in ("customer", "user"):
        weights = weights_for(person_type)
        result[person_type] = [
            {"key": factor.key, "label": factor.label, "default": factor.default_weight, "weight": weights[factor.key]}
            for factor in strategy_for(person_type).factors
        ]
    return result


class ScoringWeightsSerializer(RejectServerFieldsMixin, serializers.Serializer):
    person_type = serializers.ChoiceField(choices=("customer", "user"))
    weights = serializers.DictField(child=serializers.IntegerField(min_value=0, max_value=100))


class ScoringSettingsView(FeatureGatedAPIMixin, APIView):
    required_feature = "person_scoring"
    permission_classes = [IsPlatformAdmin]

    def get_throttles(self):
        return [SensitiveRateThrottle()] if self.request.method == "PUT" else super().get_throttles()

    @extend_schema(responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        return Response(catalog())

    @extend_schema(
        request=ScoringWeightsSerializer,
        responses={200: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Replaces one person type's factor weights (each 0–100). A factor left out goes back to its default.",
    )
    def put(self, request):
        serializer = ScoringWeightsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        update_weights(actor=request.user, **serializer.validated_data)
        return Response(catalog())
