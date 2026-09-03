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


#: Image types a logo upload accepts, and the ceiling on its size. A logo is
#: a small, low-resolution UI mark, not a document — 2 MB is generous for
#: that and small next to `attachments.DEFAULT_MAX_ATTACHMENT_BYTES` (10 MB),
#: a limit sized for scanned receipts and photos instead. Module-level, not a
#: class attribute, for the same reason `attachments.models.ALLOWED_CONTENT_
#: TYPES` is: a nested `class Meta` cannot see its enclosing class's own
#: attributes by plain name.
ALLOWED_LOGO_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")
MAX_LOGO_BYTES = 2 * 1024 * 1024


class BrandSettings(TimeStampedModel):
    """One deployment's own choice to show its name/logo instead of Dolphin's.

    Gated by the `custom_branding` feature (`common/deployment/registry.py`)
    and read through `common/branding.py`'s `effective_brand`, never directly
    by a template or view — that function is what decides "does this
    deployment's own choice actually apply right now", folding the feature
    gate in so nothing here needs to duplicate that check.

    Singleton, same pattern and same reasoning as `DeploymentProfileCache`
    above: one deployment, one brand. The logo lives in a `bytea` column, not
    a file — this codebase already made that call for `attachments.Attachment`
    (see that model's docstring): the `web` container's filesystem is
    read-only end to end and there has never been a `MEDIA_ROOT`, so storing
    bytes in Postgres needs no new persistent volume, no new backup path, and
    no nginx change — the data rides along with the volume and backup
    mechanism that already exist.
    """

    SINGLETON = 1

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON)
    #: Blank means "no custom name chosen yet" — `effective_brand` falls back
    #: to Dolphin/دلفین for that, exactly as it does when the feature itself
    #: is off. A customer who enables the feature but never visits the
    #: settings page keeps seeing the platform's own brand, not a blank one.
    display_name = models.CharField(max_length=80, blank=True)
    logo_content = models.BinaryField(null=True, blank=True)
    logo_content_type = models.CharField(max_length=32, blank=True)
    logo_size_bytes = models.PositiveIntegerField(null=True, blank=True)
    logo_original_filename = models.CharField(max_length=255, blank=True)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton=1),
                name="common_brandsettings_is_singleton",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(logo_content__isnull=True, logo_content_type="", logo_size_bytes__isnull=True)
                    | models.Q(
                        logo_content__isnull=False,
                        logo_content_type__in=ALLOWED_LOGO_CONTENT_TYPES,
                        logo_size_bytes__isnull=False,
                    )
                ),
                name="common_brandsettings_logo_all_or_nothing",
            ),
        ]

    @property
    def has_logo(self):
        return self.logo_content is not None

    def __str__(self):
        return self.display_name or "(پیش‌فرض دلفین)"

