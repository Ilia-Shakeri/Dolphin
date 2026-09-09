"""`/api/v1/dashboard-layout/` — the settings page for `common.dashboard`'s
own home-page widgets: which show, and in what order.

Same shape as `common/branding_views.py`'s `BrandSettingsView`: Platform
Admin only, feature-gated (`dashboard_insights` — the same feature that
gates the dashboard itself; customising a panel with no dashboard is
meaningless), 404-not-403 when the feature is off so a deployment that never
turned this on sees no evidence the settings page exists.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common import dashboard_layout
from common.deployment.profile import feature_enabled
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import IsPlatformAdmin
from common.serializers import DashboardSettingsSerializer, DashboardSettingsUpdateSerializer
from common.throttles import SensitiveRateThrottle


class DashboardLayoutView(APIView):
    """GET returns the current hidden/order plus the full widget catalog
    (key, label, gating module) so the settings page never hardcodes that
    list a second time. POST updates hidden/order.
    """

    required_feature = "dashboard_insights"
    permission_classes = [IsPlatformAdmin]
    throttle_classes = [SensitiveRateThrottle]

    def initial(self, request, *args, **kwargs):
        if not feature_enabled(self.required_feature):
            from rest_framework.exceptions import NotFound
            raise NotFound()
        super().initial(request, *args, **kwargs)

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "The current dashboard layout (hidden widget keys and preferred order) plus the full widget "
            "catalog — key, Persian label, and the module that gates each widget."
        ),
    )
    def get(self, request):
        settings_row = dashboard_layout.get_dashboard_settings()
        data = DashboardSettingsSerializer(settings_row).data
        data["catalog"] = [
            {"key": key, "label": label, "feature": feature}
            for key, label, feature in dashboard_layout.WIDGET_CATALOG
        ]
        response = Response(data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=DashboardSettingsUpdateSerializer,
        responses={
            200: DashboardSettingsSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Updates which widgets are hidden and/or their order. Both fields are independent and optional.",
    )
    def post(self, request):
        serializer = DashboardSettingsUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = dashboard_layout.update_dashboard_settings(
            actor=request.user,
            hidden_widgets=data.get("hidden_widgets"),
            widget_order=data.get("widget_order"),
        )
        response = Response(DashboardSettingsSerializer(row).data)
        response["Cache-Control"] = "private, no-store"
        return response
