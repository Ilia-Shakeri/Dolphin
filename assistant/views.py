"""`/api/v1/assistant/` (2.40.55): suggestions from the deployment's own model.

404 without the `ai_assistant` feature (a module a deployment does not run
looks like one never built); then `ai.use`, and the customer's own scope,
both checked again by the service. Throttled like every sensitive action:
each call is a model run on the customer's own hardware.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant import client, services
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, HasCapabilityForMethod, IsActiveAuthenticated
from common.serializers import RejectServerFieldsMixin
from common.throttles import SensitiveRateThrottle


class SuggestSerializer(RejectServerFieldsMixin, serializers.Serializer):
    kind = serializers.ChoiceField(choices=sorted(services.TASKS))
    customer = serializers.IntegerField(min_value=1)
    instruction = serializers.CharField(max_length=services.INSTRUCTION_MAX, required=False, allow_blank=True)


class AssistantSuggestView(FeatureGatedAPIMixin, APIView):
    required_feature = services.FEATURE
    required_capabilities = (services.CAPABILITY,)
    permission_classes = [IsActiveAuthenticated, HasCapabilityForMethod]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        request=SuggestSerializer,
        responses={200: dict, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "A suggestion about one customer: `summary`, `next_action` or `sms_draft`. It changes nothing; "
            "409 when the model cannot answer."
        ),
    )
    def post(self, request):
        serializer = SuggestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.suggest(
            actor=request.user, kind=data["kind"], customer_id=data["customer"], instruction=data.get("instruction", ""),
        )
        response = Response(result)
        response["Cache-Control"] = "private, no-store"
        return response


class AssistantStatusView(FeatureGatedAPIMixin, APIView):
    """Whether the model answers — for the Platform Admin and Company IT."""

    required_feature = services.FEATURE
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(responses={200: dict, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        from rest_framework.exceptions import PermissionDenied

        from accounts.models import User

        if request.user.role not in (User.Role.PLATFORM_ADMIN, User.Role.COMPANY_IT):
            raise PermissionDenied("وضعیت دستیار را فقط مدیر پلتفرم و مدیر فنی می‌بینند.")
        return Response(client.health())
