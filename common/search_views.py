"""`/api/v1/search/` — the header box's one endpoint.

Not throttled, for the reason spelled out in `common/reminders_views.py`:
`sensitive` is a single shared 30/min bucket per user, and a box typed into
one debounced keystroke at a time would drain it and make somebody's
unrelated write fail with a 429. What protects this endpoint instead is the
work it is allowed to do — a minimum query length and a hard per-group cap,
both in `common/search.py`.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common import search as search_service
from common.openapi import ACCESS_DENIED_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated


class GlobalSearchView(FeatureGatedAPIMixin, APIView):
    """Everything matching `?q=` that the caller may see, grouped by module."""

    required_feature = "global_search"
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="q",
                description=(
                    "What to look for. Shorter than two characters returns no groups rather than an error — "
                    "the box is typed into one letter at a time. Persian digits are accepted everywhere Latin "
                    "ones are, since the panel prints numbers in Persian."
                ),
                required=False,
                type=str,
            )
        ],
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE},
        description=(
            "Searches customers, leads, products, invoices, orders, payments, sales documents and after-sales "
            "requests in one call. Each group is capped at five rows and carries the `list_url` of the page "
            "that can show the rest; `count` is the true total. Only groups this deployment's features and the "
            "caller's own scope allow are present."
        ),
    )
    def get(self, request):
        response = Response(search_service.search(request.user, request.query_params.get("q", "")))
        # One user's own reachable rows, and stale results are worse than no
        # results in a box someone is typing into.
        response["Cache-Control"] = "private, no-store"
        return response
