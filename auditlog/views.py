from rest_framework.viewsets import ReadOnlyModelViewSet

from auditlog.models import ActivityLog
from auditlog.permissions import IsAuditReader
from auditlog.selectors import activity_logs_for
from auditlog.serializers import ActivityLogSerializer
from common.throttles import SensitiveRateThrottle
from common.viewsets import StrictQueryParametersMixin


class ActivityLogViewSet(StrictQueryParametersMixin, ReadOnlyModelViewSet):
    queryset = ActivityLog.objects.none()
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuditReader]
    throttle_classes = [SensitiveRateThrottle]
    search_fields = ["operation", "object_type", "object_id", "request_id"]
    ordering_fields = ["created_at", "operation", "object_type"]

    def get_queryset(self):
        return activity_logs_for(self.request.user).select_related("actor")
