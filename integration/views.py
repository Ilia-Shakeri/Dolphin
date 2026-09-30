"""PRELIMINARY, UNCOMMITTED — see integration/apps.py."""

from django.contrib.auth import login
from django.http import Http404
from django.shortcuts import redirect
from django.views.generic import View
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common.deployment.profile import paired_accounting_base_url
from common.permissions import IsActiveAuthenticated, IsPlatformAdmin
from integration import services
from integration.serializers import (
    HandoffMintResponseSerializer,
    PairingSettingsSerializer,
    PairingSettingsUpdateSerializer,
)
from integration.tokens import TokenError, mint_handoff_token, verify_handoff_token

AUDIENCE_ACCOUNTING = "dolphin-accounting"
AUDIENCE_CRM = "dolphin-crm"
HANDOFF_TOKEN_TTL_SECONDS = 60


class PairingSettingsView(APIView):
    """`/api/v1/integration/pairing/` — Platform Admin only. No dedicated
    feature flag: gated on the manifest entitlement instead, same as
    Accounting's own equivalent."""

    permission_classes = [IsPlatformAdmin]

    def initial(self, request, *args, **kwargs):
        if not paired_accounting_base_url():
            raise Http404()
        super().initial(request, *args, **kwargs)

    @extend_schema(responses={200: PairingSettingsSerializer})
    def get(self, request):
        row = services.get_pairing_settings()
        return Response(PairingSettingsSerializer({
            "is_enabled": row.is_enabled, "has_shared_secret": bool(row.shared_secret),
        }).data)

    @extend_schema(request=PairingSettingsUpdateSerializer, responses={200: PairingSettingsSerializer})
    def post(self, request):
        row = services.update_pairing_settings(
            actor=request.user,
            is_enabled=request.data.get("is_enabled"),
            shared_secret=request.data.get("shared_secret"),
        )
        return Response(PairingSettingsSerializer({
            "is_enabled": row.is_enabled, "has_shared_secret": bool(row.shared_secret),
        }).data)


class HandoffMintView(APIView):
    """`/api/v1/integration/handoff/mint/` — a signed-in CRM user asks for a
    one-click way into the paired Accounting deployment."""

    permission_classes = [IsActiveAuthenticated]

    @extend_schema(request=None, responses={200: HandoffMintResponseSerializer})
    def post(self, request):
        base_url = paired_accounting_base_url()
        if not base_url:
            raise Http404()
        pairing = services.get_pairing_settings()
        if not pairing.is_enabled or not pairing.shared_secret:
            raise Http404()
        token = mint_handoff_token(
            secret=pairing.shared_secret,
            issuer=AUDIENCE_CRM,
            audience=AUDIENCE_ACCOUNTING,
            claims={"username": request.user.username, "email": request.user.email},
            ttl_seconds=HANDOFF_TOKEN_TTL_SECONDS,
        )
        return Response(HandoffMintResponseSerializer({
            "url": f"{base_url}/integration/handoff/?token={token}",
        }).data)


class HandoffAcceptView(View):
    """`/integration/handoff/` — a user arriving from Dolphin Accounting's
    own mint endpoint. Mirrors that repo's own HandoffAcceptView exactly."""

    def get(self, request):
        base_url = paired_accounting_base_url()
        if not base_url:
            raise Http404()
        pairing = services.get_pairing_settings()
        if not pairing.is_enabled or not pairing.shared_secret:
            raise Http404()
        token = request.GET.get("token", "")
        try:
            claims = verify_handoff_token(
                secret=pairing.shared_secret, token=token, expected_audience=AUDIENCE_CRM
            )
        except TokenError:
            raise Http404()
        user = services.provision_or_get_handoff_user(
            username=claims.get("username", ""), email=claims.get("email", "")
        )
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("common_ui:home")
