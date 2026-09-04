"""`/api/v1/dashboard/` — the home page's own panel, assembled per role.

Not throttled, for the reason given in `common/reminders_views.py`: this is
one authenticated read of rows the caller can already open by hand, and the
`sensitive` bucket is a shared 30/min budget that a page-load request must
not spend.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common import dashboard
from common.openapi import ACCESS_DENIED_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated


class DashboardView(FeatureGatedAPIMixin, APIView):
    """KPIs, a sales trend, and a breakdown — whichever of them this role has."""

    required_feature = "dashboard_insights"
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE},
        description=(
            "The home page's role-specific panel: KPI figures with a period-over-period comparison, a "
            "twelve-week sales trend, and a status breakdown (leads for the sales side, after-sales cases "
            "for the after-sales side). Every part is optional — a reader who may not see a source simply "
            "has no KPI, no trend or no breakdown from it, and the page renders without that section."
        ),
    )
    def get(self, request):
        response = Response(dashboard.dashboard_for(request.user))
        response["Cache-Control"] = "private, no-store"
        return response
