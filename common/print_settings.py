"""How this company's printed documents look (2.40.44).

Three controls stay separate, as everywhere else:

* **feature availability** — `print_customization` (`common/deployment/
  registry.py`): may this deployment customise its printed documents at all;
* **role permission** — the `print_settings.manage` capability (Platform Admin
  by default, grantable per user in the permission matrix);
* **the stored choice** — `common.models.PrintSettings`.

`effective_print_settings` is what every printed document reads: it folds the
feature gate in, so a deployment without the feature prints the standard
document whatever row is stored, and turning the feature off keeps the row.
Nothing here can drop a part of the official invoice; the template keeps those
whatever the settings say (`common/templates/common/invoices/print.html`).
"""

import base64
import unicodedata

from django.db import DatabaseError, transaction

from accounts.access import has_any_capability
from accounts.models import User
from auditlog.services import log_activity
from common.branding import effective_brand, get_brand_settings, sniff_image_type
from common.color import is_valid_hex_color, normalize_hex_color
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.models import ALLOWED_LOGO_CONTENT_TYPES, MAX_LOGO_BYTES, PrintSettings

FEATURE = "print_customization"
CAPABILITY = "print_settings.manage"
#: The standard document's own accent: what prints when nothing is chosen.
DEFAULT_ACCENT = "#087f73"
TAGLINE_MAX_LENGTH = 120
FOOTER_MAX_LENGTH = 600
#: The images a company may put on its documents, by the field that holds each.
IMAGES = {"logo": "لوگو", "stamp": "مهر و امضا"}


def get_print_settings():
    """The singleton row, created empty on first read."""
    row, _ = PrintSettings.objects.get_or_create(singleton=PrintSettings.SINGLETON)
    return row


def can_manage(user):
    return feature_enabled(FEATURE) and has_any_capability(user, CAPABILITY)


def _data_uri(content, content_type):
    """An image inline in the page: the PDF renderer makes no network request
    (`DocumentPdfView`), so a document's images travel inside it."""
    return f"data:{content_type};base64,{base64.b64encode(bytes(content)).decode('ascii')}"


def _brand_logo():
    """The panel's own custom logo (`custom_branding`), the company's document
    logo until it sets one of its own; `None` without one."""
    if not effective_brand()["is_custom"]:
        return None
    brand = get_brand_settings()
    return _data_uri(brand.logo_content, brand.logo_content_type) if brand.has_logo else None


def effective_print_settings():
    """What a printed document uses right now, feature gate included.

    A dict a template reads directly: `accent_color`, `tagline`, `footer_text`,
    `paper_size`, the three `show_*` flags, and `logo`/`stamp` as data URIs or
    `None`. Never raises — a document must print even when this cannot be read.
    """
    standard = {
        "customized": False,
        "accent_color": DEFAULT_ACCENT,
        "tagline": "",
        "footer_text": "",
        "paper_size": PrintSettings.PaperSize.A4,
        "show_warehouse": True,
        "show_payment_summary": True,
        "show_issuer": True,
        "logo": None,
        "stamp": None,
    }
    try:
        brand_logo = _brand_logo()
        brand_accent = effective_brand()["accent_color"]
        if not feature_enabled(FEATURE):
            return {**standard, "logo": brand_logo, "accent_color": brand_accent or DEFAULT_ACCENT}
        row = get_print_settings()
    except DatabaseError:
        return standard
    return {
        "customized": True,
        "accent_color": row.accent_color or brand_accent or DEFAULT_ACCENT,
        "tagline": row.tagline,
        "footer_text": row.footer_text,
        "paper_size": row.paper_size,
        "show_warehouse": row.show_warehouse,
        "show_payment_summary": row.show_payment_summary,
        "show_issuer": row.show_issuer,
        "logo": _data_uri(row.logo_content, row.logo_content_type) if row.has_logo else brand_logo,
        "stamp": _data_uri(row.stamp_content, row.stamp_content_type) if row.has_stamp else None,
    }


def _clean_text(value, *, field, limit, multiline=False):
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")) if multiline else " ".join(text.split())
    text = text.strip()
    if len(text) > limit:
        raise BusinessRuleError({field: f"این متن نباید بیش از {limit} نویسه باشد."})
    return text


def _clean_accent(value):
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if not is_valid_hex_color(cleaned):
        raise BusinessRuleError({"accent_color": "رنگ باید به شکل #rrggbb باشد."})
    return normalize_hex_color(cleaned)


def _clean_image(content, field):
    if not content:
        raise BusinessRuleError({field: "فایل خالی است."})
    if len(content) > MAX_LOGO_BYTES:
        raise BusinessRuleError({field: f"حجم تصویر نباید بیش از {MAX_LOGO_BYTES // (1024 * 1024)} مگابایت باشد."})
    content_type = sniff_image_type(bytes(content[:32]))
    if content_type not in ALLOWED_LOGO_CONTENT_TYPES:
        raise BusinessRuleError({field: "فقط تصویر jpeg، png یا webp مجاز است."})
    return bytes(content), content_type


def _lock_manager(actor):
    locked = User.objects.select_for_update().filter(pk=actor.pk, is_active=True).first()
    if locked is None or not has_any_capability(locked, CAPABILITY):
        raise BusinessPermissionDenied("اجازهٔ تغییر قالب چاپ اسناد را ندارید.")
    return locked


@transaction.atomic
def update_print_settings(*, actor, images=None, remove=(), **fields):
    """Change any of the settings; whatever is not given stays as it is.

    `fields` may hold `accent_color`, `tagline`, `footer_text`, `paper_size`,
    `show_warehouse`, `show_payment_summary`, `show_issuer`. `images` maps
    `logo`/`stamp` to new bytes; `remove` names images to clear — naming one
    in both is refused rather than guessed at.
    """
    images = images or {}
    remove = set(remove)
    if remove & set(images):
        raise BusinessRuleError({sorted(remove & set(images))[0]: "حذف و جایگزینی تصویر هم‌زمان ممکن نیست."})
    unknown = (set(images) | remove) - set(IMAGES)
    if unknown:
        raise BusinessRuleError({"images": "تصویر ناشناخته."})
    if not feature_enabled(FEATURE):
        raise BusinessPermissionDenied("شخصی‌سازی چاپ در این استقرار فعال نیست.")
    locked_actor = _lock_manager(actor)
    row = PrintSettings.objects.select_for_update().get_or_create(singleton=PrintSettings.SINGLETON)[0]
    changed = []
    if "accent_color" in fields:
        row.accent_color = _clean_accent(fields["accent_color"])
        changed.append("accent_color")
    if "tagline" in fields:
        row.tagline = _clean_text(fields["tagline"], field="tagline", limit=TAGLINE_MAX_LENGTH)
        changed.append("tagline")
    if "footer_text" in fields:
        row.footer_text = _clean_text(fields["footer_text"], field="footer_text", limit=FOOTER_MAX_LENGTH, multiline=True)
        changed.append("footer_text")
    if "paper_size" in fields:
        if fields["paper_size"] not in PrintSettings.PaperSize.values:
            raise BusinessRuleError({"paper_size": "اندازهٔ کاغذ نامعتبر است."})
        row.paper_size = fields["paper_size"]
        changed.append("paper_size")
    for flag in ("show_warehouse", "show_payment_summary", "show_issuer"):
        if flag in fields:
            setattr(row, flag, bool(fields[flag]))
            changed.append(flag)
    for name in IMAGES:
        if name in remove:
            setattr(row, f"{name}_content", None)
            setattr(row, f"{name}_content_type", "")
            setattr(row, f"{name}_size_bytes", None)
            changed += [f"{name}_content", f"{name}_content_type", f"{name}_size_bytes"]
        elif name in images:
            content, content_type = _clean_image(images[name], name)
            setattr(row, f"{name}_content", content)
            setattr(row, f"{name}_content_type", content_type)
            setattr(row, f"{name}_size_bytes", len(content))
            changed += [f"{name}_content", f"{name}_content_type", f"{name}_size_bytes"]
    if not changed:
        return row
    row.updated_by = locked_actor
    row.save(update_fields=[*changed, "updated_by", "updated_at"])
    log_activity(actor=locked_actor, operation="print_settings.updated", instance=row, changes={"fields": changed})
    return row
