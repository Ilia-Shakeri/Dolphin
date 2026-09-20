"""A person's own picture, and the cartoon one they get until they upload it.

Product-owner request 2026-09-20: «برای بازاریاب‌ها آپلود عکس پروفایل مثل
پنل مترونیک، با برش/تغییر اندازه و محدودیت حجم و فرمت؛ به‌صورت پیش‌فرض از
آواتارهای کارتونی مترونیک استفاده شود».

**Stored in the row, not on disk.** `UserAvatar.content` is a `BinaryField`,
exactly as `common.models.BrandSettings.logo_content` already is, and for the
same two reasons that decision was made there: this product's container
filesystem is read-only and it has no `MEDIA_ROOT`, and a picture that lives
in the database is backed up and restored by the same `pg_dump` that already
carries everything else (`common/backups.py`). A picture is at most
`MAX_AVATAR_BYTES`, and there is one per person.

**Cropped and resized before it is sent.** The panel does that — the theme
ships an image-input component and a canvas is the right place for it — so
what arrives here is already square and already small. This module does not
trust that: it re-checks the size, sniffs the real type from the magic bytes
rather than believing a `Content-Type`, and refuses anything else. A client
is a convenience, never the boundary.

**The default is a cartoon, not an empty circle.** Metronic ships 52 of them
(`assets/media/svg/avatars/`), and which one a person gets is derived from
their own primary key rather than stored — so it never changes under them,
costs no column, and needs no migration to introduce.
"""

import hashlib

from django.db import models, transaction

from common.exceptions import BusinessPermissionDenied, BusinessRuleError


#: 2 MiB. A 512×512 JPEG is tens of kilobytes; this is generous for a photo
#: straight off a phone and small enough that a row stays cheap to read.
MAX_AVATAR_BYTES = 2 * 1024 * 1024

#: What a browser may actually send. SVG is deliberately absent: it is a
#: document, it can carry script, and nothing about a profile photo needs it
#: — the same reasoning `common.branding` applies to the panel logo.
ALLOWED_AVATAR_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")

#: The Metronic cartoon set, by filename. Kept as a count plus a pattern
#: rather than 52 literals: the files are numbered `001-`..`052-` with a
#: descriptive suffix, so the list is read from the directory once at import
#: and a set that grows or shrinks needs no edit here.
AVATAR_DIRECTORY = "common/avatars"


def _default_avatar_names():
    """Every cartoon avatar this build ships, sorted, or `()` if none are.

    Read from the collected static tree at import time. An empty tuple is a
    real possibility — a build that excluded the directory — and every reader
    here copes rather than raising: a missing cartoon is a blank circle, not
    a broken page.
    """
    from django.contrib.staticfiles import finders

    directory = finders.find(AVATAR_DIRECTORY)
    if not directory:
        return ()
    import pathlib

    path = pathlib.Path(directory)
    if not path.is_dir():
        return ()
    return tuple(sorted(item.name for item in path.glob("*.svg")))


#: Resolved once. `finders.find` walks the static directories, which is not
#: something to do per request for a constant.
_DEFAULT_AVATARS = None


def default_avatar_names():
    global _DEFAULT_AVATARS
    if _DEFAULT_AVATARS is None:
        _DEFAULT_AVATARS = _default_avatar_names()
    return _DEFAULT_AVATARS


def default_avatar_for(user):
    """The cartoon this person gets until they upload their own, or `None`.

    Derived from the primary key by a stable hash rather than `pk % count`:
    consecutive users would otherwise get consecutive files, and a team
    created in one sitting would appear as a tidy run through the set
    instead of looking assorted. Derived at all, rather than stored, so it
    never changes under someone and costs no column.
    """
    names = default_avatar_names()
    if not names or user is None or getattr(user, "pk", None) is None:
        return None
    digest = hashlib.sha256(str(user.pk).encode("ascii")).digest()
    return names[int.from_bytes(digest[:4], "big") % len(names)]


def default_avatar_url(user):
    """The static URL of that cartoon, or `None` when this build ships none."""
    from django.templatetags.static import static

    name = default_avatar_for(user)
    return static(f"{AVATAR_DIRECTORY}/{name}") if name else None


def sniff_avatar_content_type(content):
    """The real type, from the first bytes — never from what a client said.

    The same sniff `common.branding` and `attachments.services` already use.
    Returning `None` for anything unrecognised is what makes the caller's
    membership check a real gate rather than a formality.
    """
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def avatar_for(user):
    """This person's stored picture row, or `None`."""
    from accounts.models import UserAvatar

    if user is None or getattr(user, "pk", None) is None:
        return None
    return UserAvatar.objects.filter(pk=user.pk).first()


def has_avatar(user):
    return avatar_for(user) is not None


@transaction.atomic
def set_avatar(*, actor, target, content, original_filename=""):
    """Store `target`'s picture.

    Who may: the person themselves, or a role that already administers that
    user. Both are checked here rather than only in the view, because this is
    the boundary a management command or a script also comes through — and
    "whose face is on this account" is exactly the kind of thing that must
    not be settable by anyone who can reach the function.
    """
    from accounts.models import UserAvatar

    _require_may_edit(actor, target)
    if not content:
        raise BusinessRuleError({"avatar": "فایل خالی است."})
    if len(content) > MAX_AVATAR_BYTES:
        raise BusinessRuleError({
            "avatar": f"حجم تصویر نباید بیش از {MAX_AVATAR_BYTES // (1024 * 1024)} مگابایت باشد."
        })
    content_type = sniff_avatar_content_type(bytes(content[:32]))
    if content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
        raise BusinessRuleError({"avatar": "فقط تصویر jpeg، png یا webp مجاز است."})

    # `update_or_create`, not `get_or_create` then save: every column on this
    # table is required and constrained (`size_bytes > 0`, an allowed content
    # type), so a row created empty and filled in afterwards cannot be
    # inserted at all — measured, it failed with an IntegrityError on the
    # very first upload. One statement that writes the whole row is also the
    # honest shape: there is no moment when a half-written avatar is valid.
    row, _ = UserAvatar.objects.update_or_create(
        user=target,
        defaults={
            "content": bytes(content),
            "content_type": content_type,
            "size_bytes": len(content),
            "original_filename": str(original_filename or "").strip()[:255],
        },
    )
    return row


@transaction.atomic
def clear_avatar(*, actor, target):
    """Drop the stored picture, so the cartoon comes back.

    Deleting the row rather than blanking its columns: "no picture" and "a
    picture of nothing" are not the same fact, and only the first should
    fall back to the cartoon.
    """
    from accounts.models import UserAvatar

    _require_may_edit(actor, target)
    UserAvatar.objects.filter(pk=target.pk).delete()


def _require_may_edit(actor, target):
    from accounts.access import has_any_capability

    if actor is None or target is None:
        raise BusinessPermissionDenied("تغییر تصویر پروفایل مجاز نیست.")
    if actor.pk == target.pk:
        return
    if not has_any_capability(actor, "users.manage_all", "users.manage_agents", "users.manage_non_platform"):
        raise BusinessPermissionDenied("تغییر تصویر پروفایل کاربر دیگر مجاز نیست.")
