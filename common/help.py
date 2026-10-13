"""The «راهنما» drawer's words, one topic per menu group (2.40.42).

Roadmap item 13: the UI kit's help drawer, with real content. Each topic says
what the section holds and the few things people most often need to know
there; the drawer shows the one for the section the reader is in, and the
others they can open. Keyed by `common.navigation.GROUPS` keys, so a section
and its help are named the same.

Help never describes what the reader cannot reach. A section's summary is the
pages of it the reader's own menu shows, and every tip names what it needs:
a page of the menu (`"lead-board"`, an `Item.module`), a deployment feature
(`"feature:two_factor"`) or a capability (`"capability:sales_documents.manage"`).
A tip whose needs are not all met is left out, so a deployment without the lead
board, or a reader without deployment settings, never reads about them.
"""

#: group key -> (summary for a one-page section, or None to list its pages; tips).
HELP_TOPICS = {
    "dashboard": (
        "خلاصهٔ کار امروز و ارقام اصلی، بر پایهٔ نقش شما.",
        (
            ("با دکمهٔ «شخصی‌سازی» بالای صفحه، ویجت‌ها را جابه‌جا، بزرگ و کوچک یا پنهان کنید؛ چیدمان فقط برای خود شماست.",
             ("feature:dashboard_insights",)),
            ("ارقام زنده‌اند: فاکتور، دریافت یا سرنخ تازه بدون رفرش در آن‌ها دیده می‌شود.", ("feature:realtime",)),
        ),
    ),
    "campaigns": (
        None,
        (
            ("مخاطبان کمپین را از فایل اکسل بارگذاری کنید؛ هر سرنخ تازه خودکار و برابر میان مسئولان کمپین تقسیم می‌شود.",
             ("campaigns",)),
            ("فاکتوری که از یک کمپین آمده به همان کمپین نسبت داده می‌شود تا نتیجهٔ مالی کمپین دیده شود.", ("campaign-results",)),
            ("در «تحلیل کمپین‌ها» چند کمپین را کنار هم مقایسه کنید.", ("campaign-analytics",)),
        ),
    ),
    "leads": (
        None,
        (
            ("هر سرنخ به یک کمپین تعلق دارد و مسئولش از میان مسئولان همان کمپین است.", ("leads",)),
            ("تاریخ پیگیری بعدی را روی سرنخ بگذارید تا در «تقویم پیگیری» دیده شود.", ("lead-calendar",)),
            ("هر تماس روی یکی از مخاطبان کمپین ثبت می‌شود و نتیجه‌اش در پروفایل مشتری می‌ماند.", ("interactions",)),
        ),
    ),
    "customers": (
        None,
        (
            ("پروفایل مشتری همه‌چیز را در زبانه‌های جدا دارد؛ کارت‌های بالا ارقام همان مشتری در بازهٔ انتخابی‌اند.",
             ("customers",)),
            ("شمارهٔ تکراری پذیرفته نمی‌شود؛ پیش از ثبت، مشتری را جست‌وجو کنید.", ("customers",)),
            ("مشتری غیرفعال حذف نمی‌شود و همهٔ سابقه‌اش می‌ماند.", ("customers",)),
            ("در «اسناد و پیوست‌ها» همهٔ فایل‌هایی را که اجازهٔ دیدنشان را دارید یکجا جست‌وجو کنید.",
             ("attachment-library",)),
        ),
    ),
    "sales": (
        None,
        (
            ("فاکتور تا «پیش‌نویس» است ویرایش می‌شود؛ پس از صدور، اقلام و مبالغ ثابت می‌مانند.", ("invoices",)),
            ("فاکتور اقساطی پیش‌پرداخت و اقساطش را خودش می‌سازد؛ دریافت‌ها به ترتیب به آن‌ها تخصیص می‌یابند.",
             ("invoices",)),
            ("درخواست تأمین تأییدشده کالا را از انبار کم می‌کند و لغو آن برمی‌گرداند.", ("orders",)),
            ("اسناد مالی حذف نمی‌شوند؛ اشتباه با ابطال یا سند برگشتی اصلاح می‌شود.", ()),
        ),
    ),
    "inventory": (
        None,
        (
            ("موجودی فقط با ثبت گردش (ورود، خروج، انتقال) تغییر می‌کند؛ عدد آن مستقیم ویرایش نمی‌شود.",
             ("stock-movements",)),
        ),
    ),
    "finance": (
        None,
        (
            ("دریافت را به فاکتورهای همان مشتری تخصیص دهید تا مانده و دفتر حساب درست شود.", ("payments",)),
            ("چک تا وصول، دریافت را در انتظار نگه می‌دارد؛ وضعیت چک را از صفحهٔ «چک‌ها» به‌روز کنید.", ("cheques",)),
        ),
    ),
    "after_sales": (
        None,
        (
            ("هر پرونده یک مسئول دارد و هر تغییر وضعیتش در تاریخچهٔ همان پرونده می‌ماند.", ("after-sales",)),
            ("نوبت بعدی را روی پرونده بگذارید تا در تقویم خدمات دیده شود.", ("after-sales-calendar",)),
        ),
    ),
    "shipping": (
        None,
        (
            ("در رهگیری پستی چند مرسوله را انتخاب کنید و با «تغییر وضعیت» یکجا به وضعیت تازه ببرید.",
             ("sales-documents", "capability:sales_documents.manage")),
        ),
    ),
    "communication": (
        None,
        (
            ("در گفت‌وگو، Enter پیام را می‌فرستد و Shift+Enter به خط تازه می‌رود.", ("chat",)),
            ("پیامک گروهی را می‌توانید برای زمانی دیگر زمان‌بندی کنید.", ("outbound-sms",)),
        ),
    ),
    "reports": (
        None,
        (
            ("بازهٔ هر گزارش را بالای صفحه انتخاب کنید؛ «خروجی اکسل» همان بازه و همان پالایش را می‌گیرد.", ()),
            ("هدف ماهانهٔ فروش هر بازاریاب کنار رتبه‌بندی دیده می‌شود.", ("marketer-ranking",)),
        ),
    ),
    "administration": (
        None,
        (
            ("حساب هر کاربر و دسترسی‌هایش در پروفایل همان کاربر است.", ("users",)),
            ("رویدادهای سامانه هر تغییر مهم را با نام انجام‌دهنده و زمانش نگه می‌دارند.", ("audit",)),
        ),
    ),
    "settings": (
        "نمایش پنل و امنیت حساب شما.",
        (
            ("قلم، اندازه و حالت روشن یا تیره فقط برای خود شما تنظیم می‌شود.", ()),
            ("در «امنیت» نشست‌های فعال حسابتان را ببینید و ببندید.", ()),
            ("ورود دومرحله‌ای را هم از «امنیت» روشن کنید.", ("feature:two_factor",)),
        ),
    ),
}

#: The keys that work anywhere in the panel, with what each needs.
SHORTCUTS = (
    ("Ctrl + K", "جست‌وجوی سراسری", ("feature:global_search",)),
    ("Enter", "ثبت فرم", ()),
    ("Esc", "بستن پنجره‌ای که چیزی در آن تغییر نکرده", ()),
    ("← →", "جابه‌جایی میان زبانه‌ها و گزینه‌ها", ()),
)


def _met(needs, modules, features, capabilities):
    for need in needs:
        kind, _, name = need.rpartition(":")
        if kind == "feature" and name not in features:
            return False
        if kind == "capability" and name not in capabilities:
            return False
        if not kind and name not in modules:
            return False
    return True


def _listed(labels):
    quoted = [f"«{label}»" for label in labels]
    return quoted[0] if len(quoted) == 1 else "، ".join(quoted[:-1]) + " و " + quoted[-1]


def topics_for(groups, *, features=(), capabilities=()):
    """The topics of the menu groups a reader is shown, in menu order, each
    with only the tips that reader can act on."""
    features, capabilities = set(features), set(capabilities)
    shown = []
    for group in groups:
        topic = HELP_TOPICS.get(group["key"])
        if not topic:
            continue
        summary, tips = topic
        modules = {link["module"] for link in group["links"]}
        shown.append({
            "key": group["key"],
            "title": group["label"],
            "summary": summary or f"{_listed([link['label'] for link in group['links']])}.",
            "points": [text for text, needs in tips if _met(needs, modules, features, capabilities)],
        })
    return shown


def shortcuts_for(features=()):
    features = set(features)
    return [(keys, meaning) for keys, meaning, needs in SHORTCUTS if _met(needs, set(), features, set())]
