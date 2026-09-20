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



#: Panel typefaces a user may choose between, as `(value, Persian label, CSS
#: stack)`. Every stack ends in `IRANSansWeb` — the one Persian face this
#: product actually ships (`assets/fonts/`) — so a reader who picks a family
#: their machine does not have still gets Persian glyphs rather than an OS
#: substitute chosen at random. No new font file is downloaded for this: the
#: alternatives are the faces Iranian office machines already carry, which is
#: exactly why they are the ones people ask for by name.
PANEL_FONT_FAMILIES = (
    ("iransans", "ایران‌سنس (پیش‌فرض)", 'IRANSansWeb, Helvetica, sans-serif'),
    ("tahoma", "تاهوما", 'Tahoma, IRANSansWeb, Helvetica, sans-serif'),
    ("nazanin", "بی‌نازنین", '"B Nazanin", "XB Zar", IRANSansWeb, serif'),
    ("mitra", "بی‌میترا", '"B Mitra", "XB Zar", IRANSansWeb, serif'),
    ("system", "قلم سیستم", 'system-ui, -apple-system, "Segoe UI", IRANSansWeb, sans-serif'),
)
PANEL_FONT_FAMILY_STACKS = {value: stack for value, _label, stack in PANEL_FONT_FAMILIES}
DEFAULT_PANEL_FONT_FAMILY = PANEL_FONT_FAMILIES[0][0]

#: Panel scale, as `(value, Persian label, root font-size)`. The theme's whole
#: type ramp (`.fs-1` … `.fs-8`) and most of its spacing are `rem`, so moving
#: the root size moves the panel proportionally rather than only its running
#: text — which is what "اندازهٔ قلم کل پنل" actually asks for.
#:
#: Absolute pixels, stepped off the purchased theme's own base rather than
#: percentages of the browser default. Measured in a real browser, not
#: assumed: `style.bundle.rtl.css` ends with `html, body { font-size: 13px
#: !important }`, so the root is 13px and not the 16px a percentage would be
#: read against — `112.5%` came out as 18px, a 38% jump, where a step up was
#: wanted. `13px` is that base exactly and emits no CSS at all.
PANEL_FONT_SCALES = (
    ("sm", "کوچک", "12px"),
    ("md", "متوسط (پیش‌فرض)", "13px"),
    ("lg", "بزرگ", "14.5px"),
    ("xl", "خیلی بزرگ", "16px"),
)
PANEL_FONT_SCALE_SIZES = {value: size for value, _label, size in PANEL_FONT_SCALES}
DEFAULT_PANEL_FONT_SCALE = "md"


class UserPreference(TimeStampedModel):
    """One user's own panel preferences — typeface, scale, currency unit and
    colour theme.

    Deliberately separate from `BrandSettings`/`DashboardSettings` above, and
    from `accounts.User` itself, because it answers a third question. Those
    two are *this deployment's* choices, set by an admin and seen by everyone;
    `accounts.User` is who somebody is and what they may do. This is what one
    reader wants their own screen to look like, and nothing here may ever
    widen what that reader can see or do — a preference is presentation, never
    permission (CLAUDE.md §5.1).

    A row is created lazily on first write. A user who never opened the
    settings page has no row and gets every default, so adding this table
    changed nothing for anybody already using the product.
    """

    class CurrencyUnit(models.TextChoices):
        RIAL = "rial", "ریال"
        TOMAN = "toman", "تومان"

    class Theme(models.TextChoices):
        SYSTEM = "system", "هماهنگ با سیستم"
        LIGHT = "light", "روشن"
        DARK = "dark", "تیره"

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="panel_preference", primary_key=True,
    )
    font_family = models.CharField(
        max_length=16,
        choices=[(value, label) for value, label, _stack in PANEL_FONT_FAMILIES],
        default=DEFAULT_PANEL_FONT_FAMILY,
    )
    font_scale = models.CharField(
        max_length=2,
        choices=[(value, label) for value, label, _size in PANEL_FONT_SCALES],
        default=DEFAULT_PANEL_FONT_SCALE,
    )
    #: Display only. Every amount in this product is stored in rial and stays
    #: stored in rial; choosing «تومان» divides by ten on the way to the screen
    #: and multiplies by ten on the way back from a form, so the stored value a
    #: rial reader and a toman reader are looking at is the same number.
    currency_unit = models.CharField(
        max_length=8, choices=CurrencyUnit.choices, default=CurrencyUnit.RIAL,
    )
    #: Mirrors what `KTThemeMode` already keeps in `localStorage` under
    #: `data-bs-theme-mode`. Stored server-side as well so the choice follows
    #: the person to another browser, and so the first painted frame is
    #: already right — `base.html` stamps it before any stylesheet loads.
    theme = models.CharField(max_length=8, choices=Theme.choices, default=Theme.SYSTEM)

    def __str__(self):
        return f"تنظیمات نمایش {self.user_id}"


class UserDashboardLayout(TimeStampedModel):
    """One user's own dashboard arrangement — which widgets they hid, the
    order they put them in, and how wide each one is.

    `DashboardSettings` above stays exactly what it was: this deployment's
    default, applied to everyone. This table is an overlay on top of it, and
    the overlay may only ever *narrow* what is shown — a widget the
    deployment hid stays hidden no matter what a user saves here
    (`common.dashboard_layout.apply_layout`). Same keys, validated against
    the same `WIDGET_KEYS`, for the same reason: a Persian wording change to
    a KPI must never invalidate a saved layout.
    """

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="dashboard_layout", primary_key=True,
    )
    hidden_widgets = models.JSONField(default=list, blank=True)
    widget_order = models.JSONField(default=list, blank=True)
    #: `{widget key: size token}`, the tokens being the keys of
    #: `common.dashboard_layout.WIDGET_SIZES`. A widget missing from this map
    #: keeps the width its own card was designed at, so resizing one widget
    #: never requires pinning the width of every other one.
    widget_sizes = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"چیدمان داشبورد {self.user_id}"


class BackupJob(TimeStampedModel):
    """One request the panel made of `backup-agent`, and what came back.

    The spool files are the *channel* between the web container and the
    agent; this table is the *record*. Keeping both is not duplication:
    the spool is cleaned up, holds no history and cannot be queried, while
    an operator asking "who restored the database, when, from which file"
    is asking a question only a row can answer — and `auditlog.log_activity`
    needs a real object to point at, which a file on a volume is not.

    `status` is advanced by `common.backups.reconcile_jobs`, which reads the
    result files the agent wrote. The agent never touches this table: it has
    no Django, no application database credentials, and giving it either
    would defeat the split that makes it safe to hold the privileged ones
    (see `common/backups.py`).
    """

    class Kind(models.TextChoices):
        BACKUP = "backup", "پشتیبان‌گیری"
        RESTORE = "restore", "بازگردانی"

    class Status(models.TextChoices):
        WAITING = "waiting", "در صف اجرا"
        DONE = "done", "انجام شد"
        FAILED = "failed", "ناموفق"
        EXPIRED = "expired", "منقضی شد"

    #: The same 32 hex characters that name the request and result files on
    #: the spool volume, which is how a row and its files find each other.
    token = models.CharField(max_length=32, unique=True)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.WAITING)
    requested_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    #: For a restore: what the operator called the file they uploaded, and
    #: what it actually hashed to. Display and evidence only — nothing is
    #: ever opened by this name (the stored file is named from the token).
    original_filename = models.CharField(max_length=120, blank=True)
    sha256 = models.CharField(max_length=64, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    #: The archive the agent produced: the new backup for a backup job, and
    #: for a restore the *safety* backup it took of the live database before
    #: replacing it — which is the row an operator needs most if a restore
    #: turns out to have been a mistake.
    archive_name = models.CharField(max_length=128, blank=True)
    message = models.TextField(blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["-created_at"], name="backupjob_created_idx")]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.get_status_display()}"
