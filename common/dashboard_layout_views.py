"""`/api/v1/dashboard-layout/` — the reader's own dashboard arrangement.

Until 2.8.0 this was a Platform-Admin-only endpoint behind a separate
settings page, writing one row shared by the whole deployment. The product
owner asked for that page to go and for the dashboard itself to be
arranged in place, by whoever is looking at it, so this now reads and writes
`common.models.UserDashboardLayout` — the actor's own row, never anybody
else's, which is enforced at the service signature
(`common.dashboard_layout.update_user_dashboard_layout` takes no `user`).

The deployment-wide row is untouched and still applies underneath; see
`common/dashboard_layout.py` for how the two layers combine, and why a
widget the deployment hid cannot be unhidden from here.

Still feature-gated on `dashboard_insights` — the same feature that gates
the dashboard itself, since arranging a panel with no dashboard is
meaningless — and still 404-not-403 when it is off, so a deployment that
never turned it on sees no evidence the endpoint exists.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common import dashboard_layout
from common.deployment.profile import feature_enabled
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.serializers import UserDashboardLayoutSerializer, UserDashboardLayoutUpdateSerializer
from common.throttles import SensitiveRateThrottle


class DashboardLayoutView(APIView):
    """GET returns this reader's effective layout plus the widget catalog
    (key, label, gating module, available sizes) so the editor never
    hardcodes those lists a second time. POST saves their arrangement;
    DELETE drops it so they follow the deployment default again.
    """

    required_feature = "dashboard_insights"
    permission_classes = [IsAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def initial(self, request, *args, **kwargs):
        if not feature_enabled(self.required_feature):
            raise NotFound()
        super().initial(request, *args, **kwargs)

    def _payload(self, request):
        effective = dashboard_layout.effective_layout(request.user)
        return {
            "hidden_widgets": sorted(effective["hidden"]),
            "widget_order": effective["order"],
            "widget_sizes": effective["sizes"],
            "locked_hidden": sorted(effective["deployment_hidden"]),
            "is_customised": effective["is_customised"],
            "catalog": [
                {"key": key, "label": label, "feature": feature}
                for key, label, feature in dashboard_layout.WIDGET_CATALOG
            ],
            "sizes": [
                {"value": token, "label": label, "classes": classes}
                for token, (label, classes) in dashboard_layout.WIDGET_SIZES.items()
            ],
        }

    def _respond(self, request):
        response = Response(self._payload(request))
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description=(
            "The signed-in user's effective dashboard layout — hidden widget keys, preferred order and "
            "per-widget size — plus the full widget catalog and the available sizes."
        ),
    )
    def get(self, request):
        return self._respond(request)

    @extend_schema(
        request=UserDashboardLayoutUpdateSerializer,
        responses={
            200: UserDashboardLayoutSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Saves the signed-in user's own arrangement. All three fields are independent and optional. "
            "A widget hidden by this deployment's default layout stays hidden regardless of what is sent."
        ),
    )
    def post(self, request):
        serializer = UserDashboardLayoutUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dashboard_layout.update_user_dashboard_layout(
            actor=request.user,
            hidden_widgets=data.get("hidden_widgets"),
            widget_order=data.get("widget_order"),
            widget_sizes=data.get("widget_sizes"),
        )
        return self._respond(request)

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Drops the signed-in user's own arrangement so they follow this deployment's default again.",
    )
    def delete(self, request):
        dashboard_layout.reset_user_dashboard_layout(actor=request.user)
        return self._respond(request)
