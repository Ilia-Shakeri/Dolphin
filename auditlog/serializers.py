from rest_framework import serializers

from auditlog.models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "actor",
            "actor_role_snapshot",
            "operation",
            "object_type",
            "object_id",
            "object_role_snapshot",
            "safe_changes",
            "request_id",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields
