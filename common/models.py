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
    #: Blank means "no custom accent chosen yet" — same fallback shape as
    #: `display_name`. Stored as `#rrggbb`, lower-cased on the way in
    #: (`common.color.normalize_hex_color`) so two admins typing the same
    #: colour in different letter-casing never reads as a change.
    accent_color = models.CharField(max_length=7, blank=True)
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
            models.CheckConstraint(
                condition=models.Q(accent_color="") | models.Q(accent_color__regex=r"\A#[0-9a-f]{6}\Z"),
                name="common_brandsettings_accent_color_shape",
            ),
        ]

    @property
    def has_logo(self):
        return self.logo_content is not None

    def __str__(self):
        return self.display_name or "(پیش‌فرض دلفین)"


class DashboardSettings(TimeStampedModel):
    """One deployment's own choice of which home-page widgets show, and in
    what order — gated by the same `dashboard_insights` feature that already
    gates the dashboard itself (`common/deployment/registry.py`), read
    through `common.dashboard_layout.apply_layout`, never directly.

    Singleton, same pattern as `BrandSettings` above: one deployment, one
    layout — every user of this deployment sees the same arrangement, the
    same way every user already sees the same brand. A per-user layout is a
    different, larger feature (its own table keyed by user, its own "reset
    to the company default" question) that nobody has asked for; this is the
    one an admin can actually reach from a single settings page today.

    `hidden_widgets` and `widget_order` hold widget *keys* — the same `key`
    each `_kpi(...)` call in `common/dashboard.py` already carries, plus the
    two pseudo-keys `"trend"` and `"breakdown"` for those sections — never a
    label, so a later Persian-wording change to a KPI never breaks a saved
    layout. Both are validated against `common.dashboard_layout.WIDGET_KEYS`
    before saving, never trusted as free-form.
    """

    SINGLETON = 1

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON)
    #: Widget keys this deployment's admin turned off. A key that no longer
    #: exists (a KPI removed in a later version) is silently ignored by
    #: `apply_layout` rather than erroring — the same "disabling never
    #: breaks the page" posture every feature flag in this codebase already
    #: takes.
    hidden_widgets = models.JSONField(default=list, blank=True)
    #: The admin's preferred order, as a list of widget keys. A key present
    #: on the dashboard but missing from this list keeps its original
    #: position, appended after every explicitly ordered key — reordering
    #: one widget never requires re-listing all of them.
    widget_order = models.JSONField(default=list, blank=True)
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(singleton=1),
                name="common_dashboardsettings_is_singleton",
            ),
        ]

    def __str__(self):
        return f"چیدمان داشبورد ({len(self.hidden_widgets)} پنهان)"

