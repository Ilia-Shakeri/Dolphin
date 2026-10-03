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


def L(lang, fa, en):
    """One piece of page copy, Persian and English side by side.

    For the longer, page-specific sentences: keeping both versions at the
    place they are used makes a missing or stale translation visible in the
    same diff that changed the other one. Shared labels live in `STRINGS`.
    """
    return en if lang == "en" else fa


#: How the checklist is grouped, in display order: key -> (Persian, English).
FEATURE_GROUPS = {
    "crm": ("مشتریان و فروش", "Customers & sales"),
    "billing": ("اسناد و مالی", "Documents & finance"),
    "stock": ("کالا و انبار", "Products & warehouse"),
    "comms": ("ارتباطات و کار روزانه", "Communication & daily work"),
    "insight": ("گزارش و تحلیل", "Insight & reports"),
    "platform": ("پلتفرم و یکپارچه‌سازی", "Platform & integrations"),
}

#: Every deployment feature: key -> (group, Persian name, English name,
#: Persian one-line description, English one-line description). A test checks
#: the keys against `FEATURE_DEPENDENCIES`, so a feature added to the registry
#: without an entry here fails loudly instead of showing up bare.
FEATURE_META = {
    "customers": ("crm", "مشتریان", "Customers", "دفتر مشتریان حقیقی و حقوقی، تلفن‌ها و پروفایل.", "The customer book (individuals and companies), phones and profiles."),
    "leads": ("crm", "سرنخ‌ها و جامعهٔ هدف", "Leads & target audience", "صف کار بازاریاب، تماس‌ها و جامعهٔ هدف کمپین.", "The marketer work queue, calls and the campaign audience."),
    "lead_kanban": ("crm", "تابلوی سرنخ‌ها", "Lead board", "نمای ستونی سرنخ‌ها با کشیدن و رها کردن.", "A drag-and-drop column view of leads."),
    "sales": ("crm", "نتایج فروش", "Sales results", "ثبت و فهرست فروش‌های ثبت‌شده از کمپین.", "Recording and listing sales made from campaigns."),
    "campaigns": ("crm", "کمپین‌ها", "Campaigns", "کمپین به‌عنوان موجودیت، انتساب فاکتور و آنالیز.", "Campaigns as entities, invoice attribution and analytics."),
    "after_sales": ("crm", "خدمات پس از فروش", "After-sales service", "پرونده‌ها و تقویم قرار خدمات پس از فروش.", "After-sales cases and their appointment calendar."),
    "customer_timeline": ("crm", "تاریخچهٔ ۳۶۰ درجهٔ مشتری", "Customer 360 timeline", "همهٔ رویدادهای یک مشتری در یک خط زمانی.", "Every event of one customer on a single timeline."),
    "customer_ledger": ("billing", "دفتر حساب مشتری", "Customer ledger", "بدهی، بستانکاری و گردش حساب هر مشتری.", "Each customer debt, credit and account movements."),
    "quotations": ("billing", "پیش‌فاکتور", "Quotations", "ساخت و پیگیری پیش‌فاکتور.", "Creating and following up quotations."),
    "orders": ("billing", "درخواست تأمین از انبار", "Warehouse fulfilment requests", "درخواست تأمین کالا (سفارش) و کسر موجودی.", "Supply requests (orders) that move stock."),
    "order_kanban": ("billing", "تابلوی درخواست‌های تأمین", "Fulfilment board", "نمای ستونی درخواست‌های تأمین.", "A column view of fulfilment requests."),
    "invoices": ("billing", "فاکتورها", "Invoices", "فاکتور رسمی و غیررسمی، اقساط و چاپ.", "Official and unofficial invoices, instalments and printing."),
    "payments": ("billing", "دریافت‌ها و پرداخت‌ها", "Payments", "دریافت، تخصیص به فاکتور و اقساط.", "Receipts, allocation to invoices and instalments."),
    "cheques": ("billing", "چک", "Cheques", "ثبت و پیگیری وضعیت چک‌ها.", "Registering and tracking cheques."),
    "sales_documents": ("billing", "اسناد فروش و رهگیری پستی", "Sales documents & postal tracking", "سند فروش داخلی، مرسولهٔ پستی و وضعیت آن.", "Internal sales documents, postal shipments and their status."),
    "accounting_ledger": ("billing", "دفتر حسابداری", "Accounting ledger", "ثبت دوطرفهٔ اسناد در دفتر کل.", "Double-entry posting of documents to the general ledger."),
    "products": ("stock", "کاتالوگ محصولات", "Product catalogue", "کالاها، دسته‌بندی‌ها و قیمت‌ها.", "Products, categories and prices."),
    "inventory": ("stock", "انبار و موجودی", "Inventory", "انبارها، حرکت‌ها و موجودی.", "Warehouses, movements and stock levels."),
    "inbound_sms": ("comms", "پیامک دریافتی", "Inbound SMS", "گزارش پیامک‌های دریافتی از درگاه.", "A report of SMS received through the gateway."),
    "outbound_sms": ("comms", "پیامک ارسالی", "Outbound SMS", "ارسال تکی، گروهی و زمان‌بندی‌شده.", "Single, group and scheduled sends."),
    "internal_chat": ("comms", "گفتگوی داخلی", "Internal chat", "پیام‌رسان داخلی تیم.", "The internal team messenger."),
    "reminders": ("comms", "زنگ یادآور", "Reminders", "یادآوری پیگیری‌ها و قرارها.", "Reminders for follow-ups and appointments."),
    "tasks": ("comms", "وظایف", "Tasks", "فهرست کار کوچک هر شخص.", "A small to-do list for each person."),
    "person_notes": ("comms", "یادداشت روی پروفایل", "Profile notes", "یادداشت‌های پروفایل مشتری و کاربر.", "Notes on customer and user profiles."),
    "dashboard_insights": ("insight", "داشبورد تحلیلی", "Dashboard insights", "KPI، روند فروش و وضعیت‌ها.", "KPIs, sales trend and status breakdowns."),
    "global_search": ("insight", "جست‌وجوی سراسری", "Global search", "یک جعبهٔ جست‌وجو برای همهٔ بخش‌ها.", "One search box across the panel."),
    "reports": ("insight", "گزارش‌ها", "Reports", "گزارش عملکرد کاربران و شرکت.", "User and company performance reports."),
    "audit_log": ("insight", "گزارش رویدادها", "Audit log", "ثبت و مرور رویدادهای سیستم.", "Recording and reviewing system events."),
    "person_scoring": ("insight", "امتیازدهی اشخاص", "Person scoring", "امتیاز توضیح‌پذیر برای مشتری و کاربر.", "An explainable score per customer and user."),
    "attachments": ("insight", "پیوست فایل", "Attachments", "پیوست فایل به رکوردها.", "Attaching files to records."),
    "integrations": ("platform", "چارچوب یکپارچه‌سازی", "Integrations framework", "اتصال‌ها، صندوق خروجی و وب‌هوک ورودی.", "Connections, the outbox and inbound webhooks."),
    "outbound_webhooks": ("platform", "وب‌هوک خروجی", "Outbound webhooks", "ارسال رویدادها به سامانه‌های دیگر.", "Pushing events to other systems."),
    "public_api": ("platform", "API عمومی", "Public API", "فراخوانی API با توکن.", "Calling the API with a bearer token."),
    "telephony": ("platform", "مرکز تلفن", "Telephony", "اتصال PBX، پاپ‌آپ تماس و تماس با یک کلیک.", "PBX connection, call popup and click-to-call."),
    "realtime": ("platform", "بروزرسانی زنده", "Live updates", "تازه‌شدن لحظه‌ای فهرست‌ها و گفتگو.", "Instant refresh of lists and chat."),
    "custom_branding": ("platform", "برند اختصاصی", "Custom branding", "نام و لوگوی خود مشتری در پنل.", "The customer own name and logo in the panel."),
    "panel_backup": ("platform", "پشتیبان‌گیری از پنل", "Panel backup", "پشتیبان‌گیری و بازگردانی از داخل پنل.", "Backing up and restoring from inside the panel."),
    "internal_it_role": ("platform", "نقش مدیر فنی مشتری", "Customer IT role", "نقشی جدا برای مدیر فنی سمت مشتری.", "A separate role for the customer own technical admin."),
}

STRINGS.update({
    "brand": {"fa": "کنسول دلفین", "en": "Dolphin Console"},
    "home": {"fa": "خانه", "en": "Home"},
    "off_by_default": {"fa": "پیش‌فرض خاموش", "en": "Off by default"},
    "search_features": {"fa": "جست‌وجوی قابلیت…", "en": "Search features…"},
    "selected_count": {"fa": "انتخاب‌شده", "en": "selected"},
    "only_selected": {"fa": "فقط انتخاب‌شده‌ها", "en": "Selected only"},
    "no_match": {"fa": "قابلیتی با این عبارت پیدا نشد.", "en": "No feature matches that."},
    "feature_key": {"fa": "کلید", "en": "key"},
})
