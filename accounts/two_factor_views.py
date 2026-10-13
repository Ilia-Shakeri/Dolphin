"""Two-factor sign-in endpoints (2.40.42, feature `two_factor`).

`auth/me/two-factor/…` are the reader's own: status, start, confirm, turn off
and new recovery codes. `auth/login/two-factor/` is the second step of signing
in, after `auth/login/` answered `{"two_factor_required": true}`. The Platform
Admin's reset of someone else's lost phone is `users/{id}/reset-two-factor/`
(`accounts.views.UserViewSet`).
"""

import time

from django.contrib.auth import login
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts import two_factor
from accounts.access import is_crm_identity
from accounts.models import User
from accounts.serializers import MeSerializer
from accounts.sessions import record_session_device
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError
from common.openapi import CONFLICT_RESPONSE, CSRF_OR_ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle

#: The session key that holds a sign-in waiting for its second step.
PENDING_KEY = "dolphin_two_factor_pending"
#: How long the password step stays good for, and how many codes it allows.
PENDING_SECONDS = 300
PENDING_TRIES = 5

UNAVAILABLE = "ورود دومرحله‌ای در این استقرار در دسترس نیست؛ کلید رازها (DOLPHIN_SECRETS_KEY) تنظیم نشده است."


class TwoFactorStatusSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    enabled = serializers.BooleanField()
    enabled_at = serializers.DateTimeField(allow_null=True)
    recovery_codes_left = serializers.IntegerField()


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)


class PasswordAndCodeSerializer(PasswordSerializer, CodeSerializer):
    pass


class EnrolmentSerializer(serializers.Serializer):
    secret = serializers.CharField()
    otpauth_uri = serializers.CharField()
    qr = serializers.CharField(help_text="The address as an SVG QR code, a data: URI.")


class RecoveryCodesSerializer(serializers.Serializer):
    recovery_codes = serializers.ListField(child=serializers.CharField())


class _OwnTwoFactorView(FeatureGatedAPIMixin, APIView):
    required_feature = "two_factor"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def unavailable(self):
        raise BusinessConflictError({"detail": UNAVAILABLE})


class MyTwoFactorView(_OwnTwoFactorView):
    @extend_schema(responses={200: TwoFactorStatusSerializer})
    def get(self, request):
        response = Response(TwoFactorStatusSerializer(two_factor.status_for(request.user)).data)
        response["Cache-Control"] = "private, no-store"
        return response


class MyTwoFactorSetupView(_OwnTwoFactorView):
    @extend_schema(
        request=PasswordSerializer,
        responses={200: EnrolmentSerializer, 400: VALIDATION_ERROR_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE},
        description="A new key for the reader's authenticator app, not in force until confirmed. Asks for the password.",
    )
    def post(self, request):
        body = PasswordSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            enrolment = two_factor.begin_enrolment(user=request.user, **body.validated_data)
        except two_factor.TwoFactorUnavailable:
            self.unavailable()
        response = Response(EnrolmentSerializer(enrolment).data)
        response["Cache-Control"] = "private, no-store"
        return response


class MyTwoFactorConfirmView(_OwnTwoFactorView):
    @extend_schema(
        request=CodeSerializer,
        responses={200: RecoveryCodesSerializer, 400: VALIDATION_ERROR_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Turns two-factor sign-in on once the app's code matches; answers the recovery codes, shown once.",
    )
    def post(self, request):
        body = CodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            codes = two_factor.confirm_enrolment(user=request.user, **body.validated_data)
        except two_factor.TwoFactorUnavailable:
            self.unavailable()
        response = Response(RecoveryCodesSerializer({"recovery_codes": codes}).data)
        response["Cache-Control"] = "private, no-store"
        return response


class MyTwoFactorDisableView(_OwnTwoFactorView):
    @extend_schema(
        request=PasswordAndCodeSerializer,
        responses={200: TwoFactorStatusSerializer, 400: VALIDATION_ERROR_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Turns it off: the password, and a current code or a recovery code.",
    )
    def post(self, request):
        body = PasswordAndCodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            two_factor.disable(user=request.user, **body.validated_data)
        except two_factor.TwoFactorUnavailable:
            self.unavailable()
        return Response(TwoFactorStatusSerializer(two_factor.status_for(request.user)).data)


class MyRecoveryCodesView(_OwnTwoFactorView):
    @extend_schema(
        request=PasswordAndCodeSerializer,
        responses={200: RecoveryCodesSerializer, 400: VALIDATION_ERROR_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Ten new recovery codes, replacing the old ones.",
    )
    def post(self, request):
        body = PasswordAndCodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            codes = two_factor.renew_recovery_codes(user=request.user, **body.validated_data)
        except two_factor.TwoFactorUnavailable:
            self.unavailable()
        response = Response(RecoveryCodesSerializer({"recovery_codes": codes}).data)
        response["Cache-Control"] = "private, no-store"
        return response


# --- sign-in ----------------------------------------------------------------------

def start_pending_sign_in(request, user):
    """Remember a password that was right, for the code that must follow it.

    Nothing is signed in: the session only names the user, the moment and the
    tries left. `auth_hash` ties it to the password as it was, so a password
    changed meanwhile ends it.
    """
    request.session[PENDING_KEY] = {
        "user_id": user.pk,
        "backend": getattr(user, "backend", ""),
        "auth_hash": user.get_session_auth_hash(),
        "at": int(time.time()),
        "tries": 0,
    }


def needs_second_step(user):
    return feature_enabled("two_factor") and two_factor.enabled_for(user)


@method_decorator(csrf_protect, name="dispatch")
class LoginTwoFactorView(FeatureGatedAPIMixin, APIView):
    required_feature = "two_factor"
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=CodeSerializer,
        responses={200: MeSerializer, 400: VALIDATION_ERROR_RESPONSE, 403: CSRF_OR_ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "The second step of signing in: the authenticator's six-digit code, or a recovery code. "
            "Valid for five minutes and five tries after the password step."
        ),
    )
    def post(self, request):
        body = CodeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        pending = request.session.get(PENDING_KEY)
        expired = ValidationError({"code": "مهلت ورود تمام شد؛ دوباره نام کاربری و رمز عبور را وارد کنید."})
        if not pending or time.time() - pending.get("at", 0) > PENDING_SECONDS:
            request.session.pop(PENDING_KEY, None)
            raise expired
        user = User.objects.filter(pk=pending.get("user_id"), is_active=True).first()
        if user is None or not is_crm_identity(user) or user.get_session_auth_hash() != pending.get("auth_hash"):
            request.session.pop(PENDING_KEY, None)
            raise expired
        try:
            accepted = two_factor.verify_sign_in(user=user, code=body.validated_data["code"])
        except two_factor.TwoFactorUnavailable:
            raise ValidationError({"code": UNAVAILABLE})
        if not accepted:
            pending["tries"] = pending.get("tries", 0) + 1
            if pending["tries"] >= PENDING_TRIES:
                request.session.pop(PENDING_KEY, None)
                raise ValidationError({"code": "کد چند بار اشتباه وارد شد؛ دوباره نام کاربری و رمز عبور را وارد کنید."})
            request.session[PENDING_KEY] = pending
            raise ValidationError({"code": "کد درست نیست."})
        request.session.pop(PENDING_KEY, None)
        login(request, user, backend=pending.get("backend") or None)
        record_session_device(request)
        return Response(MeSerializer(user).data)
