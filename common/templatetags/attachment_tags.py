"""The upload rules the attachments panel states out loud.

Product-owner request 2026-09-19: every attachments panel should carry a short
line saying what may be uploaded and how large it may be, and should refuse an
oversized or wrong-typed file before sending it rather than after.

Nothing here decides those rules — they were decided in 2026-09-03 and live in
`attachments/`: `ALLOWED_CONTENT_TYPES` is the set every check validates
against (constraint, service, serializer), and `services.max_attachment_bytes()`
is the effective per-file ceiling (the configured `ATTACHMENT_MAX_BYTES`,
clamped by the database's own fixed constraint). This module only reads them,
so the sentence a user reads and the rule the server enforces cannot drift.

A template tag rather than a context processor: the panel is one include used
by five detail pages, and it can load what it needs itself without every view
in the product growing a context entry it does not use.
"""

from django import template

from attachments.models import ALLOWED_CONTENT_TYPES
from attachments.services import max_attachment_bytes
from common.jalali import to_persian_digits


register = template.Library()

#: How the four accepted types are named to a Persian reader. Keyed by the
#: content type itself — the thing that is actually validated — so a type
#: added to `ALLOWED_CONTENT_TYPES` without a name here still appears, under
#: its extension, instead of silently vanishing from the sentence.
TYPE_LABELS = {
    "image/jpeg": "JPG",
    "image/png": "PNG",
    "image/webp": "WebP",
    "application/pdf": "PDF",
}


@register.simple_tag
def attachment_accept():
    """The `accept` attribute for the file input, from the same source.

    The browser treats this as a hint only — the server still sniffs the real
    bytes — but a hint that matches the rule saves a person choosing a file
    that was never going to be accepted.
    """
    return ",".join(sorted(ALLOWED_CONTENT_TYPES))


@register.simple_tag
def attachment_max_bytes():
    """The per-file ceiling in bytes, for the panel's own pre-send check."""
    return max_attachment_bytes()


@register.simple_tag
def attachment_max_label():
    """The same ceiling as a reader sees it: «۱۰ مگابایت».

    Whole megabytes only. The ceiling has always been an exact multiple of one
    megabyte, and a fraction here would read as a precision the rule does not
    have.
    """
    megabytes = max_attachment_bytes() / (1024 * 1024)
    rounded = int(megabytes) if megabytes == int(megabytes) else round(megabytes, 1)
    return to_persian_digits(f"{rounded} مگابایت")


@register.simple_tag
def attachment_types_label():
    """The accepted types as a list a reader can check their file against."""
    names = [
        TYPE_LABELS.get(content_type, extensions[0].lstrip(".").upper())
        for content_type, extensions in sorted(ALLOWED_CONTENT_TYPES.items())
    ]
    return "، ".join(names)
