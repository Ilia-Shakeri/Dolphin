"""The white-label API: read/update the settings, and serve the logo itself.

Two different trust levels, on purpose:

* `BrandSettingsView` (GET/POST `/api/v1/branding/`) is the settings page's
  own API — Platform Admin only, feature-gated.
* `BrandLogoView` (GET `/api/v1/branding/logo/`) is public, no authentication
  at all: the login page shows the custom logo *before* anyone has signed in,
  exactly like the default static logo it replaces is already public. It is
  still feature-gated — a deployment that turned white-labelling back off
  stops serving a customer's uploaded logo even if the row still holds one.
"""

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common import branding
from common.deployment.profile import feature_enabled
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import IsPlatformAdmin
from common.serializers import BrandSettingsSerializer, BrandSettingsUpdateSerializer
from common.throttles import SensitiveRateThrottle


class BrandSettingsView(APIView):
    """`/api/v1/branding/` — the settings page itself reads and writes here."""

    required_feature = "custom_branding"
    permission_classes = [IsPlatformAdmin]
    parser_classes = [MultiPartParser]
    throttle_classes = [SensitiveRateThrottle]

    def initial(self, request, *args, **kwargs):
        # Same 404-not-403 reasoning as FeatureGatedAPIMixin: a deployment
        # that never turned this on should see no evidence the page exists,
        # not a permission error naming a feature it does not have.
        if not feature_enabled(self.required_feature):
            from rest_framework.exceptions import NotFound
            raise NotFound()
        super().initial(request, *args, **kwargs)

    @extend_schema(
        responses={200: BrandSettingsSerializer, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="The current brand name and whether a logo is set. Never the logo bytes themselves.",
    )
    def get(self, request):
        response = Response(BrandSettingsSerializer(branding.get_brand_settings()).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=BrandSettingsUpdateSerializer,
        responses={
            200: BrandSettingsSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Updates the display name and/or logo. Every field is independent and optional — sending only "
            "display_name leaves the logo untouched, and vice versa."
        ),
    )
    def post(self, request):
        serializer = BrandSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        logo = data.get("logo")
        row = branding.update_brand_settings(
            actor=request.user,
            display_name=data.get("display_name"),
            logo_bytes=logo.read() if logo is not None else None,
            logo_original_filename=logo.name if logo is not None else "",
            remove_logo=data.get("remove_logo", False),
        )
        response = Response(BrandSettingsSerializer(row).data)
        response["Cache-Control"] = "private, no-store"
        return response


class BrandLogoView(APIView):
    """`/api/v1/branding/logo/` — public, streams the uploaded logo.

    No `IsActiveAuthenticated`: unauthenticated pages (the login screen)
    render this too, the same way the default static logo is public.
    """

    permission_classes = []
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        responses={200: bytes, 404: None, 429: THROTTLED_RESPONSE},
        description="Streams the custom logo, or 404 when the feature is off or no logo is set.",
    )
    def get(self, request):
        from django.http import Http404

        if not feature_enabled("custom_branding"):
            raise Http404()
        row = branding.get_brand_settings()
        if not row.has_logo:
            raise Http404()
        response = HttpResponse(bytes(row.logo_content), content_type=row.logo_content_type)
        # Public and rarely changed, but never for longer than the page can
        # still be trusted to want it: a short cache plus revalidation, not a
        # long-lived one keyed only by URL, since this URL never changes even
        # when the logo does — the caller cache-busts with `?v=` instead
        # (see `common.context_processors.brand`).
        response["Cache-Control"] = "public, max-age=300"
        response["X-Content-Type-Options"] = "nosniff"
        return response
