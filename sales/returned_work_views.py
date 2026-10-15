"""`returned-work/`: work back from a deactivated account, and the manager's decision (2.40.48)."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import BusinessPermissionDenied
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from sales.returned_work import (
    RESOLVE_ACTIONS,
    can_decide_returned_work,
    resolve_returned_work,
    returned_work_summary,
)


class ReturnedWorkSerializer(serializers.Serializer):
    from_user = serializers.IntegerField(read_only=True)
    from_user_display = serializers.CharField(read_only=True)
    lead_count = serializers.IntegerField(read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    returned_at = serializers.DateTimeField(read_only=True)


class ResolveReturnedWorkSerializer(serializers.Serializer):
    from_user = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=RESOLVE_ACTIONS)
    to_user = serializers.IntegerField(min_value=1, required=False)
    fallback_users = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, max_length=50)


class AssignedShareSerializer(serializers.Serializer):
    user = serializers.IntegerField(read_only=True)
    display = serializers.CharField(read_only=True)
    count = serializers.IntegerField(read_only=True)


class ResolvedWorkSerializer(serializers.Serializer):
    assigned_count = serializers.IntegerField(read_only=True)
    by_user = AssignedShareSerializer(many=True, read_only=True)


class ReturnedWorkView(FeatureGatedAPIMixin, APIView):
    required_feature = "leads"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        responses={200: ReturnedWorkSerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Whose work came back to the managers on deactivation and is still waiting for a decision.",
    )
    def get(self, request):
        if not can_decide_returned_work(request.user):
            raise BusinessPermissionDenied("تصمیم دربارهٔ کارهای برگشتی با مدیر است.")
        return Response(ReturnedWorkSerializer(returned_work_summary(request.user), many=True).data)


class ResolveReturnedWorkView(FeatureGatedAPIMixin, APIView):
    required_feature = "leads"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        request=ResolveReturnedWorkSerializer,
        responses={200: ResolvedWorkSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "Decide what happens to the work that came back from one person: `split` it evenly among the "
            "other responsibles of each item's campaign (with `fallback_users` for anything without one), "
            "or `assign` it all to `to_user`."
        ),
    )
    def post(self, request):
        serializer = ResolveReturnedWorkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = resolve_returned_work(
            actor=request.user,
            from_user=data["from_user"],
            action=data["action"],
            to_user=data.get("to_user"),
            fallback_users=data.get("fallback_users") or [],
        )
        return Response(ResolvedWorkSerializer(result).data)
