from rest_framework.viewsets import ReadOnlyModelViewSet

from auditlog.models import ActivityLog
from auditlog.permissions import IsAuditReader
from auditlog.selectors import activity_logs_for
from auditlog.serializers import ActivityLogSerializer
from common.throttles import SensitiveRateThrottle
from common.viewsets import StrictQueryParametersMixin, filter_by_date_window


class ActivityLogViewSet(StrictQueryParametersMixin, ReadOnlyModelViewSet):
    required_feature = "audit_log"
    queryset = ActivityLog.objects.none()
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuditReader]
    throttle_classes = [SensitiveRateThrottle]
    search_fields = ["operation", "object_type", "object_id", "request_id"]
    ordering_fields = ["created_at", "operation", "object_type"]
    #: A recorded-at window, both bounds optional and inclusive of the whole
    #: day they name (product-owner request 2026-09-20). This page is read
    #: when something went wrong at a known time, and without a window the
    #: only way to reach a day was to page back through everything since.
    list_query_parameters = {"created_from", "created_to"}

    def get_queryset(self):
        queryset = activity_logs_for(self.request.user).select_related("actor")
        # Narrowing only: `activity_logs_for` has already decided what this
        # reader may see at all, and a date bound cannot widen it.
        return filter_by_date_window(queryset, self.request.query_params)
