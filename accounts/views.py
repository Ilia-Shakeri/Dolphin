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

from accounts.models import User
from accounts.permissions import IsUserReader
from accounts.serializers import LoginSerializer, MeSerializer, RoleChangeSerializer, UserSerializer
from common.permissions import IsActiveAuthenticated
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
            400: OpenApiResponse(description="Invalid credentials or request fields."),
            403: OpenApiResponse(description="CSRF check failed."),
            429: OpenApiResponse(description="Login attempt rate exceeded."),
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
        return Response(MeSerializer(serializer.validated_data["user"]).data)


class LogoutView(APIView):
    permission_classes = [IsActiveAuthenticated]
    serializer_class = MeSerializer

    @extend_schema(
        request=None,
        responses={204: None, 403: OpenApiResponse(description="Authentication or CSRF check failed.")},
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
        responses={200: MeSerializer, 400: OpenApiResponse(description="Unknown, invalid, or server-controlled field."), 403: OpenApiResponse(description="Authentication or CSRF check failed.")},
    )
    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserViewSet(NoDestroyModelViewSet):
    queryset = User.objects.none()
    serializer_class = UserSerializer
    permission_classes = [IsUserReader]
    search_fields = ["username", "first_name", "last_name", "email", "phone"]
    ordering_fields = ["username", "role", "is_active", "created_at"]

    def get_queryset(self):
        queryset = User.objects.all().order_by("username")
        if self.request.user.role == User.Role.COMPANY_IT:
            queryset = queryset.exclude(role=User.Role.PLATFORM_ADMIN)
        return queryset

    def _require_admin(self):
        if self.request.user.role not in {User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("User administration is not allowed.")

    def perform_create(self, serializer):
        self._require_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_admin()
        if self.request.user.role == User.Role.COMPANY_IT and serializer.instance.role == User.Role.PLATFORM_ADMIN:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Company IT cannot manage Platform Admin access.")
        serializer.save()

    @action(detail=True, methods=["post"], url_path="change-role")
    @extend_schema(
        request=RoleChangeSerializer,
        responses={
            200: UserSerializer,
            400: OpenApiResponse(description="Unknown role or invalid request."),
            403: OpenApiResponse(description="Role grant is outside actor authority."),
            404: OpenApiResponse(description="User is outside actor scope."),
        },
        examples=[OpenApiExample("Role change", value={"role": User.Role.SALES_MANAGER}, request_only=True)],
        description="Company IT may grant roles through company_it. Platform Admin may grant any fixed CRM role.",
    )
    def change_role(self, request, pk=None):
        target = self.get_object()
        serializer = RoleChangeSerializer(data=request.data, context={"request": request, "target": target})
        serializer.is_valid(raise_exception=True)
        target = serializer.save()
        return Response(UserSerializer(target).data)
