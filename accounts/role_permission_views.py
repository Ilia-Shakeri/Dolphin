"""`role-permissions/`: the Platform Admin's role-level permission defaults (2.40.48).

`accounts.role_permissions` holds the rule; these views are its HTTP shape.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.role_permissions import (
    reset_role_permissions,
    role_permissions_for,
    role_profiles_for,
    set_role_permission_overrides,
)
from accounts.serializers import PermissionMatrixEntrySerializer, PermissionMatrixUpdateSerializer
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle


class RoleProfileSummarySerializer(serializers.Serializer):
    key = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    has_custom_permissions = serializers.BooleanField(read_only=True)


class RolePermissionsSerializer(serializers.Serializer):
    key = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    workstream = serializers.CharField(read_only=True)
    matrix = serializers.DictField(child=PermissionMatrixEntrySerializer(), read_only=True)
    has_custom_permissions = serializers.BooleanField(read_only=True)


class RoleProfileListView(APIView):
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        operation_id="api_v1_role_permissions_list",
        responses={200: RoleProfileSummarySerializer(many=True), 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="The roles whose permission defaults the Platform Admin may change, and which are changed. Platform Admin only.",
    )
    def get(self, request):
        return Response(RoleProfileSummarySerializer(role_profiles_for(actor=request.user), many=True).data)


class RolePermissionsView(APIView):
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        operation_id="api_v1_role_permissions_retrieve",
        responses={200: RolePermissionsSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="One role's Read/Edit/Delete matrix as configured, marked where it differs from the release's own. Platform Admin only.",
    )
    def get(self, request, key):
        return Response(RolePermissionsSerializer(role_permissions_for(actor=request.user, key=key)).data)

    @extend_schema(
        operation_id="api_v1_role_permissions_update",
        request=PermissionMatrixUpdateSerializer,
        responses={200: RolePermissionsSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "Sets what this role grants for everyone holding it. User administration and the activity "
            "log stay out of reach, except `audit.team` for the store manager. Platform Admin only."
        ),
    )
    def put(self, request, key):
        serializer = PermissionMatrixUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = set_role_permission_overrides(actor=request.user, key=key, matrix=serializer.validated_data["matrix"])
        return Response(RolePermissionsSerializer(result).data)


class RolePermissionsResetView(APIView):
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        operation_id="api_v1_role_permissions_reset",
        request=None,
        responses={200: RolePermissionsSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Back to what the release ships for this role. Platform Admin only.",
    )
    def post(self, request, key):
        return Response(RolePermissionsSerializer(reset_role_permissions(actor=request.user, key=key)).data)
