"""Endpoints behind the two charts on the customers page.

Both go through the same three controls every other read in this codebase does,
and none of them is re-implemented here:

* **feature** — `FeatureGatedAPIMixin` with `required_feature = "customers"`, so
  a deployment without the customers module has no such endpoint at all;
* **role** — `customers.scoped` or `customers.company`, exactly the capabilities
  the customer list endpoint itself requires;
* **object scope** — `customers_for` inside `reports.customer_insights`, so a
  marketer's chart counts their own customers and no others.

A chart that aggregated beyond its viewer's scope would leak the shape of data
they cannot list, which is why the aggregation is built on the selector rather
than on the model.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import has_any_capability
from common.openapi import (
    ACCESS_DENIED_RESPONSE,
    NOT_FOUND_RESPONSE,
    THROTTLED_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
)
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from reports.list_charts import LIST_CHARTS, totals_for
from reports.customer_insights import (
    InvalidReportPeriod,
    build_customer_city_report,
    build_customer_growth_report,
)
from reports.serializers import (
    CustomerCityReportSerializer,
    CustomerGrowthQuerySerializer,
    CustomerGrowthReportSerializer,
    ListChartSerializer,
)


class CustomerInsightMixin(FeatureGatedAPIMixin):
    required_feature = "customers"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def require_customer_access(self, request):
        # The same pair the customer list requires. Answering 403 rather than an
        # empty chart matches how every other module here treats a caller with
        # no capability: they are not asking for nothing, they are asking for
        # something they may not have.
        if not has_any_capability(request.user, "customers.scoped", "customers.company"):
            raise PermissionDenied("Customer access is not allowed.")


class CustomerCityReportView(CustomerInsightMixin, APIView):
    @extend_schema(
        responses={
            200: CustomerCityReportSerializer,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "How the caller's customers are distributed by city, largest first, with "
            "percentages taken against that same scoped total. Customers with no city "
            "fall back to their province, and those with neither are reported as an "
            "explicit 'not recorded' row rather than dropped, so the percentages add up."
        ),
    )
    def get(self, request):
        self.require_customer_access(request)
        report = build_customer_city_report(actor=request.user)
        response = Response(CustomerCityReportSerializer(report).data)
        response["Cache-Control"] = "private, no-store"
        return response


class CustomerGrowthReportView(CustomerInsightMixin, APIView):
    @extend_schema(
        parameters=[CustomerGrowthQuerySerializer],
        responses={
            200: CustomerGrowthReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Customers registered per week or per month, with the running total beside "
            "it. Empty buckets are returned as zero rather than omitted, so the line "
            "between two points always spans the same amount of time. Defaults to the "
            "last year by month."
        ),
    )
    def get(self, request):
        self.require_customer_access(request)
        query = CustomerGrowthQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            report = build_customer_growth_report(actor=request.user, **query.validated_data)
        except InvalidReportPeriod as exc:
            raise ValidationError({"period_end": str(exc)}) from exc
        response = Response(CustomerGrowthReportSerializer(report).data)
        response["Cache-Control"] = "private, no-store"
        return response


class ListChartView(FeatureGatedAPIMixin, APIView):
    """The chart under one list page, chosen by `key`.

    One view rather than eleven, but the three controls stay per-chart and
    explicit: `LIST_CHARTS` names the feature and the capabilities for each, and
    every builder starts from its own module's selector. A single view is only
    safe because none of that is shared — what is shared is the plumbing.

    `required_feature` is resolved per request rather than declared on the
    class, so a deployment without a module answers 404 for its chart exactly as
    it does for its pages.
    """

    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    def initial(self, request, *args, **kwargs):
        key = kwargs.get("key")
        entry = LIST_CHARTS.get(key)
        if entry is None:
            raise NotFound("Unknown chart.")
        self.required_feature = entry[0]
        # Runs the feature gate with the value just resolved.
        super().initial(request, *args, **kwargs)

    @extend_schema(
        responses={
            200: ListChartSerializer,
            403: ACCESS_DENIED_RESPONSE,
            404: NOT_FOUND_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "The single chart shown beneath one list page. Each key carries its own "
            "feature and capability requirements, and its rows are aggregated through "
            "that module's selector, so a chart never counts a row its viewer could "
            "not list."
        ),
    )
    def get(self, request, key):
        feature, capabilities, builder, title = LIST_CHARTS[key]
        if not has_any_capability(request.user, *capabilities):
            raise PermissionDenied("Access to this chart is not allowed.")
        results = builder(request.user)
        payload = {"key": key, "title": title, "results": results, **totals_for(results)}
        response = Response(ListChartSerializer(payload).data)
        response["Cache-Control"] = "private, no-store"
        return response
