"""The trend chart behind one seller's profile page.

`user_id` defaults to the caller's own row, so a marketer opening their own
profile needs no query parameter at all. An elevated role may pass any
`user_id` `reports.selectors.users_for_performance_report` would also let the
user-performance report itself return, and `build_sales_growth_report` refuses
anything past that same boundary — this endpoint adds no permission of its
own beyond `reports.own`/`reports.company`, the pair every other report here
already requires.
"""

from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import has_any_capability
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle
from reports.sales_insights import (
    InvalidReportPeriod,
    InvalidReportUser,
    build_sales_growth_report,
)
from reports.serializers import SalesGrowthQuerySerializer, SalesGrowthReportSerializer


class SalesGrowthReportView(FeatureGatedAPIMixin, APIView):
    required_feature = "reports"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]

    @extend_schema(
        parameters=[SalesGrowthQuerySerializer],
        responses={
            200: SalesGrowthReportSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Confirmed sales for one seller, bucketed by week or month, defaulting to "
            "the caller's own row and the last 365 days. Powers the trend chart on the "
            "seller profile page."
        ),
    )
    def get(self, request):
        if not has_any_capability(request.user, "reports.own", "reports.company"):
            raise PermissionDenied("دسترسی به گزارش‌ها مجاز نیست.")
        serializer = SalesGrowthQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        user_id = values.pop("user_id", None) or request.user.pk
        try:
            report = build_sales_growth_report(actor=request.user, user_id=user_id, **values)
        except InvalidReportUser as exc:
            raise ValidationError({"user_id": "کاربر نامعتبر است."}) from exc
        except InvalidReportPeriod as exc:
            raise ValidationError({"period_end": str(exc)}) from exc
        response = Response(SalesGrowthReportSerializer(report).data)
        response["Cache-Control"] = "private, no-store"
        return response
