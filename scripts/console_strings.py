"""What the deployment console says, in Persian and in English.

Product-owner request 2026-09-20: «تب‌های فارسی/انگلیسی» on the build
console. The operator running it is not always the person who wrote it, and
a signing tool whose every label is in a language you do not read is a tool
you use by guessing.

**What is translated, and what deliberately is not.** Every label, heading,
button and status line the operator acts on is here in both languages. Three
kinds of string are not, and each for a reason rather than for lack of time:

* **Feature keys** (`customers`, `sales_documents`) and **profile ids** are
  identifiers, not prose. They are what goes into the signed manifest and
  what a server reads back; translating them on screen would mean an
  operator reading one word and typing another.
* **Page titles** (`common.deployment.pages.PAGE_TITLES`) are what the panel
  itself calls those pages, in the language that panel is served in. An
  English gloss here would name something the customer's screen does not.
* **The long explanatory notices** — the warning about what this tool does
  and does not reach, the note about where the signing key must live — stay
  Persian. They are the parts a Dolphin operator must have read and
  understood before running this at all, and a translation of a safety
  notice that nobody has reviewed is worse than one language of it.

`T(lang, key)` falls back to Persian for an unknown language and to the key
itself for an unknown key, so a missing entry shows up as a visible slug
rather than as a blank label or an exception in the middle of a page.
"""

#: The two the console offers. Ordered: Persian first, because that is the
#: language the product and its operators are in.
LANGUAGES = (("fa", "فارسی"), ("en", "English"))
DEFAULT_LANGUAGE = "fa"

STRINGS = {
    # --- the checklist ----------------------------------------------------
    "requires": {"fa": "نیازمند", "en": "requires"},
    "opens": {"fa": "صفحه‌ها", "en": "pages"},
    "no_pages": {"fa": "بدون صفحهٔ اختصاصی", "en": "no page of its own"},
    "features_legend": {"fa": "قابلیت‌ها", "en": "Features"},
    "select_all": {"fa": "انتخاب همه", "en": "Select all"},
    "select_none": {"fa": "هیچ‌کدام", "en": "Select none"},
    # --- the console's own chrome ----------------------------------------
    "console_title": {"fa": "کنسول استقرار دلفین", "en": "Dolphin deployment console"},
    "language": {"fa": "زبان", "en": "Language"},
    "start": {"fa": "شروع", "en": "Start"},
    "deployments": {"fa": "استقرارها", "en": "Deployments"},
    "new_deployment": {"fa": "استقرار تازه", "en": "New deployment"},
    "build": {"fa": "ساخت", "en": "Build"},
    "preview": {"fa": "پیش‌نمایش زنده", "en": "Live preview"},
    "download": {"fa": "دانلود", "en": "Download"},
    "cancel": {"fa": "انصراف", "en": "Cancel"},
    "save": {"fa": "ذخیره", "en": "Save"},
    # --- fields -----------------------------------------------------------
    "profile_id": {"fa": "شناسهٔ پروفایل", "en": "Profile id"},
    "customer_slug": {"fa": "نام کوتاه مشتری", "en": "Customer slug"},
    "host": {"fa": "نشانی میزبان", "en": "Host"},
    "key_path": {"fa": "مسیر کلید امضا", "en": "Signing key path"},
    "key_id": {"fa": "شناسهٔ کلید", "en": "Key id"},
    "output": {"fa": "مسیر خروجی", "en": "Output path"},
    # --- outcomes ---------------------------------------------------------
    "built_ok": {"fa": "manifest ساخته و امضا شد.", "en": "Manifest built and signed."},
    "build_failed": {"fa": "ساخت manifest انجام نشد.", "en": "Manifest build failed."},
    "nothing_selected": {
        "fa": "دست‌کم یک قابلیت را انتخاب کنید.",
        "en": "Choose at least one feature.",
    },
}


def T(lang, key):
    """One string, in the requested language.

    Falls back twice, and visibly: an unknown language reads Persian, and an
    unknown key reads as the key. A label that silently rendered empty would
    be a blank button nobody could report.
    """
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key


def normalize_language(value):
    """The language to use for a request, from whatever the query said."""
    text = str(value or "").strip().lower()
    return text if text in dict(LANGUAGES) else DEFAULT_LANGUAGE
