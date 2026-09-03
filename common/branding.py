"""Whether this deployment shows Dolphin's own name/logo or a customer's.

Three things stay separate, on purpose:

* **feature availability** (`custom_branding` in `common/deployment/registry.
  py`) — may this deployment use white-labelling at all;
* **role permission** — only a Platform Admin may change it
  (`common.permissions.IsPlatformAdmin`);
* **the stored choice** (`common.models.BrandSettings`) — what, if anything,
  this deployment's own admin actually set.

`effective_brand` is the one function every reader (the context processor,
the login page, the printed document title) should call: it folds the
feature gate in, so nothing else has to remember that a disabled feature
means "show Dolphin" regardless of what row happens to be sitting in the
table — including a row left over from before the feature was turned off,
since disabling a feature must never delete data (see `CLAUDE.md`).
"""

import unicodedata

from django.db import DatabaseError, transaction

from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.models import ALLOWED_LOGO_CONTENT_TYPES, MAX_LOGO_BYTES, BrandSettings

DEFAULT_BRAND_NAME = "Dolphin"
DEFAULT_BRAND_SUBTITLE = "دلفین"

DISPLAY_NAME_MAX_LENGTH = 80


def get_brand_settings():
    """The singleton row, creating it (empty) on first read.

    Never raises — an empty row is the same as "nothing customised yet",
    which `effective_brand` already treats as "show Dolphin".
    """
    row, _ = BrandSettings.objects.get_or_create(singleton=BrandSettings.SINGLETON)
    return row


def effective_brand():
    """What every page should actually render, feature gate included.

    Returns a dict a template can use directly: `name`, `subtitle` (blank for
    a custom brand — the two-line "Dolphin / دلفین" lockup is this platform's
    own, not a customer's to inherit), `is_custom`, and `logo_updated_at` (for
    cache-busting the logo URL; `None` when there is no custom logo to serve).
    """
    default_brand = {
        "name": DEFAULT_BRAND_NAME,
        "subtitle": DEFAULT_BRAND_SUBTITLE,
        "is_custom": False,
        "logo_updated_at": None,
    }
    if not feature_enabled("custom_branding"):
        return default_brand
    try:
        settings_row = get_brand_settings()
    except DatabaseError:
        # Rendered on every page, including the login screen before any
        # session exists and the 500 handler after something has already
        # gone wrong with the database — this must never be a second point
        # of failure. Anything that stops the read (migrations not yet run,
        # the database briefly unreachable) falls back to the same default
        # every other reader gets when the feature is simply off.
        return default_brand
    if not settings_row.display_name:
        # Feature on, but this deployment's admin never set anything —
        # still Dolphin, not a blank name.
        return default_brand
    return {
        "name": settings_row.display_name,
        "subtitle": "",
        "is_custom": True,
        "logo_updated_at": settings_row.updated_at if settings_row.has_logo else None,
    }


def _clean_display_name(value):
    cleaned = unicodedata.normalize("NFKC", str(value or "")).strip()
    if len(cleaned) > DISPLAY_NAME_MAX_LENGTH:
        raise BusinessRuleError({"display_name": f"نام نباید بیش از {DISPLAY_NAME_MAX_LENGTH} کاراکتر باشد."})
    return cleaned


def _sniff_logo_content_type(content):
    """The same magic-byte sniff `attachments.services` uses, image types
    only — a logo is never a PDF.
    """
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _lock_platform_admin(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or locked.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("تغییر برند فقط برای مدیر پلتفرم مجاز است.")
    return locked


@transaction.atomic
def update_brand_settings(*, actor, display_name=None, logo_bytes=None, logo_original_filename="", remove_logo=False):
    """Update the name and/or logo. Any argument left `None`/`False` is
    left untouched — a name-only edit does not require re-uploading the
    logo, and vice versa. `remove_logo=True` clears the logo even if
    `logo_bytes` is also given; a caller sending both is almost certainly a
    bug, so `update_brand_settings` refuses that combination outright rather
    than picking one silently.
    """
    if remove_logo and logo_bytes:
        raise BusinessRuleError({"logo": "حذف و جایگزینی لوگو هم‌زمان ممکن نیست."})
    with transaction.atomic():
        locked_actor = _lock_platform_admin(actor)
        row = BrandSettings.objects.select_for_update().get_or_create(singleton=BrandSettings.SINGLETON)[0]
        changed_fields = []

        if display_name is not None:
            row.display_name = _clean_display_name(display_name)
            changed_fields.append("display_name")

        if remove_logo:
            row.logo_content = None
            row.logo_content_type = ""
            row.logo_size_bytes = None
            row.logo_original_filename = ""
            changed_fields += ["logo_content", "logo_content_type", "logo_size_bytes", "logo_original_filename"]
        elif logo_bytes is not None:
            if not logo_bytes:
                raise BusinessRuleError({"logo": "فایل خالی است."})
            if len(logo_bytes) > MAX_LOGO_BYTES:
                raise BusinessRuleError({"logo": f"حجم لوگو نباید بیش از {MAX_LOGO_BYTES // (1024 * 1024)} مگابایت باشد."})
            content_type = _sniff_logo_content_type(bytes(logo_bytes[:32]))
            if content_type not in ALLOWED_LOGO_CONTENT_TYPES:
                raise BusinessRuleError({"logo": "فقط تصویر jpeg، png یا webp مجاز است."})
            row.logo_content = bytes(logo_bytes)
            row.logo_content_type = content_type
            row.logo_size_bytes = len(logo_bytes)
            row.logo_original_filename = unicodedata.normalize("NFKC", str(logo_original_filename or "")).strip()[:255]
            changed_fields += ["logo_content", "logo_content_type", "logo_size_bytes", "logo_original_filename"]

        if not changed_fields:
            return row

        row.updated_by = locked_actor
        row.save(update_fields=[*changed_fields, "updated_by", "updated_at"])
        log_activity(
            actor=locked_actor,
            operation="brand_settings.updated",
            instance=row,
            changes={"fields": changed_fields},
        )
    return row
