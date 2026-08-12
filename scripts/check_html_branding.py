#!/usr/bin/env python3
"""Normalize and verify Kariz-owned HTML branding without touching theme contracts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".cache",
    ".next",
    "build",
    "dist",
    "node_modules",
    "vendor",
}
THIRD_PARTY_HTML_PREFIXES = ("src/plugins/keenicons/",)
ROBOTS_VALUE = "noindex,nofollow,noarchive"
PRODUCT_NAME = "Kariz CRM | کاریز"
DESCRIPTION = "سامانه مدیریت ارتباط با مشتری کاریز"

VENDOR_TEXT_RE = re.compile(
    r"metronic|مترونیک|keenthemes?|ساتراس\s*وب|satras\s*web|satrasweb\.ir|"
    r"themeforest|envato",
    re.IGNORECASE,
)
VENDOR_URL_RE = re.compile(
    r"(?:https?:)?//(?:[^/\s\"'<>]+\.)?(?:keenthemes\.com|envato\.market|"
    r"themeforest\.net|facebook\.com|twitter\.com|x\.com|instagram\.com|"
    r"linkedin\.com|youtube\.com|dribbble\.com|github\.com|authy\.com|"
    r"momentjs\.com|microsoft\.com|rtl-theme\.com)(?:/|\b)|"
    r"(?:https?:)?//support\.[^/\s\"'<>]+(?:/|\b)",
    re.IGNORECASE,
)
REMOVABLE_LINK_RE = re.compile(
    r"(?is)<(?P<tag>a|iframe)\b(?=[^>]*(?:href|src)\s*=\s*[\"'][^\"']*(?:"
    r"keenthemes|envato|themeforest|rtl-theme\.com/metronic|facebook\.com|"
    r"twitter\.com|x\.com/|instagram\.com|linkedin\.com|youtube\.com|"
    r"dribbble\.com|github\.com|rtl-theme\.com|authy\.com|momentjs\.com|microsoft\.com|"
    r"support\.|landing\.html)[^\"']*[\"'])[^>]*>.*?"
    r"</(?P=tag)>"
)
TOP_VENDOR_COMMENT_RE = re.compile(
    r"(?is)(<!doctype\s+html>\s*)<!--\s*(?:نویسنده|author)\s*:.*?-->\s*"
)
HTML_TAG_RE = re.compile(r"<html\b[^>]*>", re.IGNORECASE)
TITLE_RE = re.compile(r"<title>.*?</title>", re.IGNORECASE | re.DOTALL)
DESCRIPTION_RE = re.compile(
    r"<meta\b(?=[^>]*\bname\s*=\s*[\"']description[\"'])[^>]*>", re.IGNORECASE
)
KEYWORDS_RE = re.compile(
    r"\s*<meta\b(?=[^>]*\bname\s*=\s*[\"']keywords[\"'])[^>]*>\s*",
    re.IGNORECASE,
)
ROBOTS_RE = re.compile(
    r"<meta\b(?=[^>]*\bname\s*=\s*[\"']robots[\"'])[^>]*>", re.IGNORECASE
)
CANONICAL_RE = re.compile(
    r"\s*<link\b(?=[^>]*\brel\s*=\s*[\"']canonical[\"'])[^>]*>\s*",
    re.IGNORECASE,
)
OG_URL_RE = re.compile(
    r"\s*<meta\b(?=[^>]*\bproperty\s*=\s*[\"']og:url[\"'])[^>]*>\s*",
    re.IGNORECASE,
)
TWITTER_META_RE = re.compile(
    r"\s*<meta\b(?=[^>]*(?:\bname|\bproperty)\s*=\s*[\"']twitter:)[^>]*>\s*",
    re.IGNORECASE,
)

ENTITY_NAMES = {
    "account": "حساب کاربری",
    "activity": "فعالیت",
    "api-keys": "کلیدهای دسترسی",
    "billing": "صورتحساب",
    "calendar": "تقویم",
    "campaigns": "کمپین‌ها",
    "careers": "فرصت‌های شغلی",
    "categories": "دسته‌بندی محصولات",
    "category": "دسته‌بندی محصول",
    "chat": "گفتگو",
    "contacts": "مشتریان",
    "customers": "مشتریان",
    "documents": "اسناد",
    "ecommerce": "فروش",
    "faq": "پرسش‌های متداول",
    "feeds": "رویدادها",
    "file-manager": "مدیریت فایل",
    "files": "فایل‌ها",
    "folders": "پوشه‌ها",
    "followers": "دنبال‌کنندگان",
    "inbox": "صندوق پیام",
    "invoices": "فاکتورها",
    "logs": "گزارش رویدادها",
    "orders": "سفارش‌ها",
    "permissions": "دسترسی‌ها",
    "pricing": "قیمت‌گذاری",
    "products": "محصولات",
    "projects": "پروژه‌ها",
    "referrals": "معرفی‌ها",
    "reports": "گزارش‌ها",
    "roles": "نقش‌ها",
    "sales": "فروش‌ها",
    "security": "امنیت",
    "settings": "تنظیمات",
    "shipping": "ارسال",
    "social": "شبکه اجتماعی",
    "statements": "صورت‌حساب‌ها",
    "subscriptions": "اشتراک‌ها",
    "support-center": "مرکز پشتیبانی",
    "team": "تیم",
    "tickets": "تیکت‌ها",
    "tutorials": "راهنماها",
    "user-management": "مدیریت کاربران",
    "user-profile": "پروفایل کاربر",
    "users": "کاربران",
    "widgets": "ابزارک‌ها",
}
ACTION_NAMES = {
    "activity": "فعالیت",
    "add": "افزودن",
    "add-category": "افزودن دسته‌بندی",
    "add-contact": "افزودن مشتری",
    "add-order": "افزودن سفارش",
    "add-product": "افزودن محصول",
    "apply": "ثبت درخواست",
    "blank": "صفحه خالی",
    "budget": "بودجه",
    "compose": "نوشتن پیام",
    "contact": "تماس",
    "create": "ایجاد",
    "details": "جزئیات",
    "edit-category": "ویرایش دسته‌بندی",
    "edit-contact": "ویرایش مشتری",
    "edit-order": "ویرایش سفارش",
    "edit-product": "ویرایش محصول",
    "files": "فایل‌ها",
    "folders": "پوشه‌ها",
    "getting-started": "شروع کار",
    "list": "فهرست",
    "listing": "فهرست",
    "logs": "گزارش رویدادها",
    "overview": "نمای کلی",
    "permissions": "دسترسی‌ها",
    "post": "مطلب",
    "private": "گفتگوی خصوصی",
    "project": "پروژه",
    "reply": "پاسخ پیام",
    "returns": "مرجوعی‌ها",
    "sales": "گزارش فروش",
    "security": "امنیت",
    "settings": "تنظیمات",
    "shipping": "گزارش ارسال",
    "statements": "صورت‌حساب‌ها",
    "targets": "هدف‌ها",
    "users": "کاربران",
    "view": "جزئیات",
}
AUTH_TITLES = {
    "account-deactivated": "حساب غیرفعال",
    "card-declined": "رد شدن کارت",
    "coming-soon": "به‌زودی",
    "error-404": "صفحه پیدا نشد",
    "error-500": "خطای سامانه",
    "multi-steps-sign-up": "ثبت‌نام چندمرحله‌ای",
    "new-password": "رمز عبور جدید",
    "password-confirmation": "تایید رمز عبور",
    "reset-password": "بازیابی رمز عبور",
    "sign-in": "ورود",
    "sign-up": "ثبت‌نام",
    "subscription-confirmed": "تایید اشتراک",
    "two-factor": "تایید دومرحله‌ای",
    "verify-email": "تایید ایمیل",
    "welcome": "خوش‌آمدید",
    "welcome-message": "پیام خوش‌آمد",
}


def html_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.html"):
        relative = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if relative.startswith(THIRD_PARTY_HTML_PREFIXES):
            continue
        files.append(path)
    return sorted(files)


def persian_title(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    parts = path.relative_to(ROOT).parts
    stem = path.stem.lower()
    if relative == "common/templates/common/home.html":
        return "خانه"
    if relative == "index.html":
        return "داشبورد"
    if relative == "landing.html":
        return "معرفی کاریز"
    if parts[0] == "authentication":
        return AUTH_TITLES.get(stem, "احراز هویت")
    if parts[0] == "dashboards":
        return f"داشبورد {ENTITY_NAMES.get(stem, 'مدیریت')}"
    if parts[0] == "asides":
        number = stem.rsplit("-", 1)[-1]
        return f"نمای کناری {number}"
    if parts[0] == "layouts":
        return "چیدمان سامانه"
    if parts[0] == "toolbars":
        return "نوار ابزار"
    if parts[0] == "widgets":
        return f"ابزارک‌های {ENTITY_NAMES.get(stem, 'سامانه')}"
    entity = next(
        (ENTITY_NAMES[part.lower()] for part in reversed(parts[:-1]) if part.lower() in ENTITY_NAMES),
        "سامانه",
    )
    action = ACTION_NAMES.get(stem)
    if action:
        return action if action == entity else f"{action} {entity}"
    return f"صفحه {entity}"


def replace_meta(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    return pattern.sub(replacement, text, count=1)


def normalize(path: Path) -> bool:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    original = text
    if re.search(r"{%\s*extends\b", text):
        return False
    newline = "\r\n" if "\r\n" in text else "\n"
    title = f"{persian_title(path)} | Kariz CRM"

    text = TOP_VENDOR_COMMENT_RE.sub(r"\1", text, count=1)

    def normalize_html_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        tag = re.sub(r"\s+direction\s*=\s*[\"'][^\"']*[\"']", "", tag, flags=re.IGNORECASE)
        if re.search(r"\slang\s*=", tag, re.IGNORECASE):
            tag = re.sub(r"\slang\s*=\s*[\"'][^\"']*[\"']", ' lang="fa"', tag, flags=re.IGNORECASE)
        else:
            tag = tag[:-1].rstrip() + ' lang="fa">'
        if re.search(r"\sdir\s*=", tag, re.IGNORECASE):
            tag = re.sub(r"\sdir\s*=\s*[\"'][^\"']*[\"']", ' dir="rtl"', tag, flags=re.IGNORECASE)
        else:
            tag = tag[:-1].rstrip() + ' dir="rtl">'
        return tag

    text = HTML_TAG_RE.sub(normalize_html_tag, text, count=1)
    text = TITLE_RE.sub(f"<title>{title}</title>", text, count=1)
    description_meta = f'<meta name="description" content="{DESCRIPTION}" />'
    if DESCRIPTION_RE.search(text):
        text = replace_meta(text, DESCRIPTION_RE, description_meta)
    else:
        charset = re.search(r"<meta\b(?=[^>]*\bcharset\s*=)[^>]*>", text, re.IGNORECASE)
        if charset:
            text = text[: charset.end()] + newline + "    " + description_meta + text[charset.end() :]
    text = KEYWORDS_RE.sub(newline, text)
    text = CANONICAL_RE.sub(newline, text)
    text = OG_URL_RE.sub(newline, text)
    text = TWITTER_META_RE.sub(newline, text)
    text = re.sub(
        r'<meta\b(?=[^>]*\bproperty\s*=\s*["\']og:locale["\'])[^>]*>',
        '<meta property="og:locale" content="fa_IR" />',
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'<meta\b(?=[^>]*\bproperty\s*=\s*["\']og:type["\'])[^>]*>',
        '<meta property="og:type" content="website" />',
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'<meta\b(?=[^>]*\bproperty\s*=\s*["\']og:title["\'])[^>]*>',
        f'<meta property="og:title" content="{title}" />',
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'<meta\b(?=[^>]*\bproperty\s*=\s*["\']og:site_name["\'])[^>]*>',
        f'<meta property="og:site_name" content="{PRODUCT_NAME}" />',
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    robots = f'<meta name="robots" content="{ROBOTS_VALUE}" />'
    if ROBOTS_RE.search(text):
        text = ROBOTS_RE.sub(robots, text, count=1)
    else:
        viewport = re.search(
            r'(?P<indent>^[ \t]*)<meta\b(?=[^>]*\bname\s*=\s*["\']viewport["\'])[^>]*>',
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        if viewport:
            insert_at = viewport.end()
            text = text[:insert_at] + newline + viewport.group("indent") + robots + text[insert_at:]
        else:
            head = re.search(r"<head\b[^>]*>", text, re.IGNORECASE)
            if head:
                text = text[: head.end()] + newline + "    " + robots + text[head.end() :]

    text = REMOVABLE_LINK_RE.sub("", text)
    text = re.sub(
        r"(?is)<source\b(?=[^>]*\bsrc\s*=\s*[\"']https?://www\.soundhelix\.com/)[^>]*>",
        "",
        text,
    )
    text = re.sub(r'https://path/to/file/[^"\']*', "", text, flags=re.IGNORECASE)
    text = re.sub(r"[\w.+-]+@keenthemes\.com", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)https?://[^\s\"'<>]*(?:keenthemes|envato|themeforest)[^\s\"'<>]*", "", text)
    text = re.sub(r"(?i)www\.(?:keenthemes|twitter|dribbble|facebook)\.com[^\s\"'<>]*", "", text)
    text = re.sub(r"(?i)metronic|مترونیک", "کاریز", text)
    text = re.sub(r"(?i)keenthemes?", "Kariz CRM", text)
    text = re.sub(r"(?i)satras\s*web|ساتراس\s*وب|satrasweb\.ir", "کاریز", text)
    text = re.sub(r"(?i)themeforest|envato", "", text)
    text = re.sub(r"[ \t]+(?=\r?$)", "", text, flags=re.MULTILINE)

    if text != original:
        path.write_bytes(text.encode("utf-8"))
        return True
    return False


def validate(path: Path) -> list[str]:
    text = path.read_bytes().decode("utf-8-sig")
    relative = path.relative_to(ROOT).as_posix()
    errors: list[str] = []
    inherited_template = bool(re.search(r"{%\s*extends\b", text))
    if not inherited_template:
        html_tag = HTML_TAG_RE.search(text)
        if not html_tag or not re.search(r'\blang=["\']fa["\']', html_tag.group(0), re.IGNORECASE):
            errors.append("missing lang=fa")
        if not html_tag or not re.search(r'\bdir=["\']rtl["\']', html_tag.group(0), re.IGNORECASE):
            errors.append("missing dir=rtl")
        title = TITLE_RE.search(text)
        if not title or not re.fullmatch(r"<title>[^<]*[\u0600-\u06ff][^<]* \| Kariz CRM</title>", title.group(0)):
            errors.append("invalid Persian Kariz title")
        robots = ROBOTS_RE.search(text)
        if not robots or not re.search(
            rf'\bcontent=["\']{re.escape(ROBOTS_VALUE)}["\']', robots.group(0), re.IGNORECASE
        ):
            errors.append("invalid internal-app robots")
        description = DESCRIPTION_RE.search(text)
        if not description or not re.search(
            rf'\bcontent=["\']{re.escape(DESCRIPTION)}["\']', description.group(0), re.IGNORECASE
        ):
            errors.append("invalid Kariz description")
    if TOP_VENDOR_COMMENT_RE.search(text):
        errors.append("vendor header comment remains")
    if VENDOR_TEXT_RE.search(text):
        errors.append("vendor name remains")
    if VENDOR_URL_RE.search(text):
        errors.append("vendor, support, purchase, or social URL remains")
    if KEYWORDS_RE.search(text):
        errors.append("keywords metadata remains")
    if OG_URL_RE.search(text):
        errors.append("OG URL remains")
    if CANONICAL_RE.search(text):
        errors.append("canonical URL remains")
    if re.search(r'href\s*=\s*["\'][^"\']*landing\.html', text, re.IGNORECASE):
        errors.append("landing demo link remains")
    if errors:
        return [f"{relative}: {error}" for error in errors]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="apply the bounded branding normalization")
    args = parser.parse_args()
    files = html_files()
    if args.fix:
        changed = sum(1 for path in files if normalize(path))
        print(f"normalized_html={changed}")
    errors = [error for path in files for error in validate(path)]
    if errors:
        print("\n".join(errors))
        return 1
    print(f"HTML_BRANDING_PASS files={len(files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
