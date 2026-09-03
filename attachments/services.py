"""Upload and delete for attachments.

Reading (list, download) needs no service function — object scope alone
(`attachments/selectors.py`) decides what a request may see, exactly like
every read-only endpoint elsewhere in this codebase. Only a state change
needs the actor lock, the capability check, and an audit log entry.
"""

import unicodedata

from django.conf import settings
from django.db import transaction

from accounts.access import is_crm_identity
from accounts.models import User
from attachments.models import ALLOWED_CONTENT_TYPES, DEFAULT_MAX_ATTACHMENT_BYTES, Attachment
from attachments.selectors import PARENT_FIELDS, can_write_parent, parent_is_visible
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied, BusinessRuleError


#: {sales_manager, company_it, platform_admin} — the exact "elevated
#: operator" set repeated across sales/billing/inventory's own services.py.
#: Product-owner decision 2026-09-03: deletion is theirs alone, regardless of
#: which parent type the attachment is on, so a sales_agent who may upload a
#: receipt to their own invoice still may not remove one after the fact.
ELEVATED_OPERATORS = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}

FILENAME_MAX_LENGTH = 255


def _lock_active_actor(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not is_crm_identity(locked):
        raise BusinessPermissionDenied("کاربر باید فعال باشد.")
    return locked


def max_attachment_bytes():
    """The effective per-file ceiling: the configured setting, never above
    the database's own fixed CheckConstraint — see attachments/models.py.
    """
    configured = int(getattr(settings, "ATTACHMENT_MAX_BYTES", DEFAULT_MAX_ATTACHMENT_BYTES))
    return min(configured, DEFAULT_MAX_ATTACHMENT_BYTES)


def _sniff_content_type(content):
    """The file's real type from its own bytes, never the client's claim.

    A browser's `Content-Type` header and a filename's extension are both
    exactly what the person uploading typed or their OS guessed — neither is
    checked here at all. `imghdr` is not used: it was removed from the
    standard library in Python 3.13 (this deployment's runtime), and four
    magic-byte checks are simpler than working around that anyway.
    """
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    return None


def _clean_filename(value):
    cleaned = unicodedata.normalize("NFKC", str(value or "")).strip()
    # A path separator in the *stored* name would mean nothing on this
    # column (it is never used to build a filesystem path — the file lives
    # in `content`, a database column), but a name a download response
    # echoes back into a Content-Disposition header must not smuggle one in.
    cleaned = cleaned.replace("/", "_").replace("\\", "_")
    if not cleaned:
        raise BusinessRuleError({"file": "نام فایل نامعتبر است."})
    if len(cleaned) > FILENAME_MAX_LENGTH:
        cleaned = cleaned[:FILENAME_MAX_LENGTH]
    return cleaned


def _resolve_parent(field_name, parent_id):
    if field_name not in PARENT_FIELDS or not parent_id:
        raise BusinessRuleError({"parent": "دقیقاً یکی از مشتری، سرنخ، فاکتور، سند فروش یا درخواست پس‌ازفروش را مشخص کنید."})


@transaction.atomic
def upload_attachment(*, actor, field_name, parent_id, original_filename, content):
    """Validate, sniff, and store one file against exactly one parent record.

    `field_name` names which of the five parent fields is being set (e.g.
    `"customer"`), and `parent_id` its primary key — the caller (the
    serializer) has already checked exactly one of the five was supplied at
    all; what remains here is permission, size, and real content type.
    """
    _resolve_parent(field_name, parent_id)
    with transaction.atomic():
        locked_actor = _lock_active_actor(actor)
        if not can_write_parent(locked_actor, field_name):
            raise BusinessPermissionDenied("افزودن پیوست برای این رکورد مجاز نیست.")
        if not parent_is_visible(locked_actor, field_name, parent_id):
            raise BusinessRuleError({"parent": "رکورد مقصد پیدا نشد."})

        if not content:
            raise BusinessRuleError({"file": "فایل خالی است."})
        limit = max_attachment_bytes()
        if len(content) > limit:
            raise BusinessRuleError({"file": f"حجم فایل نباید بیش از {limit // (1024 * 1024)} مگابایت باشد."})
        content_type = _sniff_content_type(bytes(content[:32]))
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise BusinessRuleError({"file": "فقط تصویر (jpeg/png/webp) یا PDF مجاز است."})

        attachment = Attachment.objects.create(
            **{f"{field_name}_id": parent_id},
            original_filename=_clean_filename(original_filename),
            content_type=content_type,
            size_bytes=len(content),
            content=bytes(content),
            uploaded_by=locked_actor,
        )
        log_activity(
            actor=locked_actor,
            operation="attachment.uploaded",
            instance=attachment,
            changes={"fields": ["original_filename", "content_type", "size_bytes", field_name]},
        )
    return attachment


@transaction.atomic
def delete_attachment(*, actor, attachment):
    with transaction.atomic():
        locked_actor = _lock_active_actor(actor)
        if locked_actor.role not in ELEVATED_OPERATORS:
            raise BusinessPermissionDenied("حذف پیوست فقط برای مدیر یا مدیر پلتفرم مجاز است.")
        log_activity(
            actor=locked_actor,
            operation="attachment.deleted",
            instance=attachment,
            changes={"fields": ["original_filename"]},
        )
        attachment.delete()
