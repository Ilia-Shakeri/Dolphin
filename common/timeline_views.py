"""`/api/v1/customers/<id>/timeline/` — one customer's history in order.

Sits in `common/` rather than on the customer ViewSet because it reads
across nine modules (sales, billing, after-sales, attachments,
communications); putting it in `sales` would make that app import four
others to serve one page. Not throttled, for the reason given in
`common/reminders_views.py`.
"""

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from common import customer_timeline
from common.openapi import ACCESS_DENIED_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated


class CustomerTimelineView(FeatureGatedAPIMixin, APIView):
    """Every event about one customer that the caller may see, newest first."""

    required_feature = "customer_timeline"
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None},
        description=(
            "Calls, leads, orders, invoices, payments, sales documents, after-sales cases, attachments and "
            "SMS for one customer, merged and sorted by when each thing happened. Only the sources this "
            "deployment's features and the caller's own scope allow are present. A customer outside the "
            "caller's scope is a 404, not a 403."
        ),
    )
    def get(self, request, customer_id):
        customer = customer_timeline.visible_customer(request.user, customer_id)
        if customer is None:
            # Not 403: a customer outside someone's own book must not be
            # confirmed to exist, the same as every other direct read here.
            raise Http404()
        response = Response(customer_timeline.timeline_for(request.user, customer))
        response["Cache-Control"] = "private, no-store"
        return response
