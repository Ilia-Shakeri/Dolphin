from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DeploymentProfileCache(TimeStampedModel):
    """A derived, queryable copy of the active deployment profile.

    This table is never the source of truth: the signed manifest is
    (PROFILE-001, Option C). Nothing may authorise a feature from this row, and
    `common/deployment/cache.py` rewrites it from the manifest before any read,
    so restoring an old backup cannot reinstate a withdrawn feature.
    """

    SINGLETON = 1

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON)
    profile_id = models.CharField(max_length=64)
    manifest_fingerprint = models.CharField(max_length=64, blank=True)
    features = models.JSONField(default=list)
    source = models.CharField(max_length=32)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton=1),
                name="common_deploymentprofilecache_is_singleton",
            )
        ]

    def __str__(self):
        return f"{self.profile_id} ({self.source})"

