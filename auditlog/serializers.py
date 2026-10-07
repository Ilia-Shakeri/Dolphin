from rest_framework import serializers

from auditlog.labels import object_type_label, operation_label
from auditlog.models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    #: The Persian name of the operation, beside the stored value rather than in
    #: place of it: the panel reads this, and anything filtering or scripting
    #: against the log keeps the stable `noun.verb` form.
    operation_display = serializers.SerializerMethodField()

    #: The same for the record kind (2.40.36): «سند فروش», not `sales.salesdocument`.
    object_type_display = serializers.SerializerMethodField()

    def get_operation_display(self, instance) -> str:
        return operation_label(instance.operation)

    def get_object_type_display(self, instance) -> str:
        return object_type_label(instance.object_type)

    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "actor",
            "actor_role_snapshot",
            "operation",
            "operation_display",
            "object_type",
            "object_type_display",
            "object_id",
            "object_role_snapshot",
            "safe_changes",
            "request_id",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields
