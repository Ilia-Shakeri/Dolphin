from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.access import crm_identities
from accounts.models import User
from accounts.permissions import IsUserReader
from accounts.sessions import active_sessions_for, record_session_device, revoke_sessions
from accounts.serializers import (
    LoginSerializer,
    MeSerializer,
    RoleChangeSerializer,
    SessionListSerializer,
    SessionRevokeResultSerializer,
    SessionRevokeSerializer,
    UserSerializer,
)
from common.openapi import (
    ACCESS_DENIED_RESPONSE,
    CONFLICT_RESPONSE,
    CSRF_OR_ACCESS_DENIED_RESPONSE,
    NOT_FOUND_RESPONSE,
    THROTTLED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from common.permissions import IsActiveAuthenticated
from common.throttles import SensitiveActionThrottleMixin, SensitiveRateThrottle
from common.viewsets import NoDestroyModelViewSet


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: MeSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: CSRF_OR_ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        examples=[
            OpenApiExample(
                "Login request",
                value={"username": "sales.agent", "password": "<password>"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        login(request, serializer.validated_data["user"])
        record_session_device(request)
        return Response(MeSerializer(serializer.validated_data["user"]).data)


class LogoutView(APIView):
    permission_classes = [IsActiveAuthenticated]
    serializer_class = MeSerializer

    @extend_schema(
        request=None,
        responses={204: None, 403: CSRF_OR_ACCESS_DENIED_RESPONSE},
    )
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    permission_classes = [IsActiveAuthenticated]
    serializer_class = MeSerializer

    @extend_schema(responses={200: MeSerializer})
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(
        request=MeSerializer,
        responses={
            200: MeSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: CSRF_OR_ACCESS_DENIED_RESPONSE,
        },
    )
    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class MySessionsView(APIView):
    """The caller's own active sessions, and the controls to end them.

    Separate from the Platform-Admin endpoints on `UserViewSet` on purpose:
    seeing where *you* are signed in, and signing yourself out elsewhere, is not
    user administration and needs no administrative capability. The service
    layer allows self-service and admin access and refuses everything else.
    """

    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]
    serializer_class = SessionListSerializer

    @extend_schema(
        responses={200: SessionListSerializer, 403: ACCESS_DENIED_RESPONSE},
        description="Active sessions of the signed-in user. Session keys are never returned.",
    )
    def get(self, request):
        rows = active_sessions_for(
            actor=request.user,
            target=request.user,
            current_session_key=request.session.session_key or "",
        )
        response = Response(SessionListSerializer({"count": len(rows), "results": rows}).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=SessionRevokeSerializer,
        responses={
            200: SessionRevokeResultSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: CSRF_OR_ACCESS_DENIED_RESPONSE,
        },
        description=(
            "Ends one of the caller's sessions by reference, or every other session when no "
            "reference is given. The caller's own session is always kept, so this never signs "
            "them out of the page they are using."
        ),
    )
    def post(self, request):
        serializer = SessionRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ended = revoke_sessions(
            actor=request.user,
            target=request.user,
            reference=serializer.validated_data.get("reference") or None,
            keep_session_key=request.session.session_key or "",
        )
        return Response(SessionRevokeResultSerializer({"ended": ended}).data)


class UserViewSet(SensitiveActionThrottleMixin, NoDestroyModelViewSet):
    queryset = User.objects.none()
    serializer_class = UserSerializer
    permission_classes = [IsUserReader]
    sensitive_actions = frozenset({"create", "update", "partial_update", "change_role"})
    search_fields = ["username", "first_name", "last_name", "email", "phone"]
    ordering_fields = ["username", "role", "workstream", "is_active", "created_at"]

    def get_queryset(self):
        queryset = crm_identities(User.objects.all()).order_by("username")
        if self.request.user.role == User.Role.SALES_MANAGER:
            queryset = queryset.filter(role=User.Role.SALES_AGENT)
        elif self.request.user.role == User.Role.COMPANY_IT:
            queryset = queryset.exclude(role=User.Role.PLATFORM_ADMIN)
        return queryset

    def _require_admin(self):
        if self.request.user.role != User.Role.PLATFORM_ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("User administration is not allowed.")

    def perform_create(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_admin()
        if self.request.user.role == User.Role.SALES_MANAGER and serializer.instance.role != User.Role.SALES_AGENT:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Sales Manager may manage Sales Agent accounts only.")
        if self.request.user.role == User.Role.COMPANY_IT and serializer.instance.role == User.Role.PLATFORM_ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Company IT cannot manage Platform Admin access.")
        serializer.save()

    @extend_schema(
        request=RoleChangeSerializer,
        responses={
            200: UserSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            409: CONFLICT_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        examples=[OpenApiExample("Role change", value={"role": User.Role.SALES_MANAGER}, request_only=True)],
        description="Sales Manager cannot change roles. Company IT may grant roles through company_it. Platform Admin may grant any fixed CRM role.",
    )
    @action(detail=True, methods=["post"], url_path="change-role")
    def change_role(self, request, pk=None):
        target = self.get_object()
        serializer = RoleChangeSerializer(data=request.data, context={"request": request, "target": target})
        serializer.is_valid(raise_exception=True)
        target = serializer.save()
        return Response(UserSerializer(target).data)

    @extend_schema(
        responses={200: SessionListSerializer},
        description="Active sessions of one user. Platform Admin only.",
    )
    @action(detail=True, methods=["get"], url_path="sessions")
    def sessions(self, request, pk=None):
        target = self.get_object()
        # `reference` identifies a session; the session key itself never leaves
        # the server, because holding one is enough to *be* that user.
        rows = active_sessions_for(
            actor=request.user, target=target, current_session_key=request.session.session_key or ""
        )
        return Response(SessionListSerializer({"count": len(rows), "results": rows}).data)

    @extend_schema(
        request=SessionRevokeSerializer,
        responses={200: SessionRevokeResultSerializer, 400: VALIDATION_ERROR_RESPONSE},
        description="End one session, or every session, of one user. Platform Admin only.",
    )
    @action(detail=True, methods=["post"], url_path="revoke-sessions")
    def revoke_sessions_action(self, request, pk=None):
        target = self.get_object()
        serializer = SessionRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ended = revoke_sessions(
            actor=request.user,
            target=target,
            reference=serializer.validated_data.get("reference") or None,
        )
        return Response(SessionRevokeResultSerializer({"ended": ended}).data)
