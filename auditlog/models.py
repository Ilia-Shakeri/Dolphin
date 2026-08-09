from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="activity_logs")
    actor_role_snapshot = models.CharField(max_length=32, blank=True, db_index=True)
    operation = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    object_role_snapshot = models.CharField(max_length=32, blank=True, db_index=True)
    safe_changes = models.JSONField(default=dict)
    request_id = models.CharField(max_length=100, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["object_type", "object_id", "-created_at"])]
