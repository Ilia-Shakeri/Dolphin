"""Which panel pages each deployment feature actually turns on.

Product-owner request 2026-09-20: the build console's checklist should offer
every page and option of the panel, «با منبع واقعی فیچرها همگام باشند (نه یک
لیست دستیِ قدیمی)» — synced with the real source, not a hand-maintained list
that has gone stale.

So nothing here is a list. The pages are read off `common.ui_urls` itself and
the feature each one needs is read off the view class that serves it
(`required_feature`, the same attribute `FeatureGatedViewMixin` enforces at
request time). A page added to the panel appears in the console the moment it
is routed; a page whose gate changes moves under the new feature by itself;
and a feature that gates nothing is reported as gating nothing rather than
quietly listing something it does not.

The one thing that cannot be derived is what a page is called in Persian — a
URL name is `common_ui:sales-documents` and a person reads «رهگیری پستی». That
mapping lives in `PAGE_TITLES` below and is the only hand-written part, which
is why `common/tests/` asserts it covers every routed page: a new page without
a title fails the test rather than appearing in the console as a slug.
"""

from django.urls import get_resolver


#: `url name -> what a person calls that page`. The only hand-written table
#: here, and the one a test pins against the real route list so it cannot
#: fall behind. Taken from each page's own `{% block page_title %}`, so the
#: console and the panel call a page the same thing.
PAGE_TITLES = {
    "common_ui:home": "داشبورد",
    "common_ui:customers": "مشتریان",
    "common_ui:customer-detail": "جزئیات مشتری",
    "common_ui:lead-board": "تابلوی سرنخ‌ها",
    "common_ui:order-board": "تابلوی سفارش‌ها",
    "common_ui:interaction-detail": "جزئیات تماس",
    "common_ui:sale-detail": "جزئیات فروش",
    "common_ui:product-detail": "جزئیات محصول",
    "common_ui:product-category-detail": "جزئیات دسته‌بندی",
    "common_ui:warehouse-detail": "جزئیات انبار",
    "common_ui:disbursements": "پرداخت‌ها و دریافت‌ها",
    "common_ui:payment-detail": "جزئیات پرداخت",
    "common_ui:installments": "اقساط",
    "common_ui:invoice-print": "چاپ فاکتور",
    "common_ui:invoice-pdf": "پی‌دی‌اف فاکتور",
    "common_ui:user-detail": "جزئیات کاربر",
    "common_ui:user-profile": "پروفایل کاربر",
    "common_ui:activity-log-detail": "جزئیات رویداد",
    "common_ui:leads": "سرنخ‌ها",
    "common_ui:lead-detail": "جزئیات سرنخ",
    "common_ui:lead-calendar": "تقویم پیگیری سرنخ",
    "common_ui:interactions": "تماس‌ها",
    "common_ui:sales": "نتایج کمپین",
    "common_ui:sales-documents": "رهگیری پستی",
    "common_ui:sales-document-detail": "جزئیات سند فروش",
    "common_ui:products": "محصولات",
    "common_ui:product-categories": "دسته‌بندی محصولات",
    "common_ui:warehouses": "انبارها",
    "common_ui:stock-levels": "موجودی انبار",
    "common_ui:stock-movements": "گردش انبار",
    "common_ui:orders": "سفارش‌ها",
    "common_ui:order-detail": "جزئیات سفارش",
    "common_ui:invoices": "فاکتورها",
    "common_ui:invoice-detail": "جزئیات فاکتور",
    "common_ui:payments": "پرداخت‌ها",
    "common_ui:cheques": "چک‌ها",
    "common_ui:after-sales": "خدمات پس از فروش",
    "common_ui:after-sales-detail": "جزئیات درخواست پس از فروش",
    "common_ui:after-sales-calendar": "تقویم پس از فروش",
    "common_ui:outbound-sms": "پیامک خروجی",
    "common_ui:sms-provider-settings": "سامانهٔ پیامک",
    "common_ui:inbound-sms-report": "گزارش پیامک ورودی",
    "common_ui:sales-document-report": "گزارش اسناد فروش و پست",
    "common_ui:receivables-report": "گزارش مطالبات",
    "common_ui:profit-report": "گزارش سود",
    "common_ui:stock-valuation-report": "گزارش ارزش موجودی",
    "common_ui:customer-ledger": "دفتر حساب مشتری",
    "common_ui:user-performance": "عملکرد کاربران",
    "common_ui:my-profile": "عملکرد من",
    "common_ui:users": "مدیریت کاربران",
    "common_ui:activity-logs": "رویدادهای سامانه",
    "common_ui:branding-settings": "شخصی‌سازی پنل",
    "common_ui:settings": "تنظیمات",
    "common_ui:integrations": "اتصال سرویس‌ها",
    "common_ui:login": "ورود",
}


def _ui_patterns():
    """Every named route under the panel's own URL namespace."""
    resolver = get_resolver()
    for namespace, sub in resolver.namespace_dict.items():
        if namespace != "common_ui":
            continue
        _prefix, sub_resolver = sub
        for pattern in sub_resolver.url_patterns:
            if getattr(pattern, "name", None):
                yield pattern
        return


def _required_feature(pattern):
    """The feature that route's view declares, or `None` for an open page.

    Read off the view class rather than a table: `FeatureGatedViewMixin`
    enforces exactly this attribute at request time, so what the console
    shows and what the deployment does cannot disagree.
    """
    callback = getattr(pattern, "callback", None)
    view_class = getattr(callback, "view_class", None)
    return getattr(view_class, "required_feature", None) if view_class else None


def pages_by_feature():
    """`feature -> [(url name, Persian title)]`, derived from the routes.

    Pages with no feature gate — the login screen, the dashboard, the
    settings page every role has — are collected under `None`, so a caller
    can show them as "always present" rather than pretending they are
    optional.
    """
    grouped = {}
    for pattern in _ui_patterns():
        name = f"common_ui:{pattern.name}"
        feature = _required_feature(pattern)
        grouped.setdefault(feature, []).append((name, PAGE_TITLES.get(name, name)))
    for rows in grouped.values():
        rows.sort(key=lambda row: row[1])
    return grouped


def routed_page_names():
    """Every named panel route, for the test that pins `PAGE_TITLES`."""
    return frozenset(f"common_ui:{pattern.name}" for pattern in _ui_patterns())


def feature_page_titles():
    """`feature -> ["مشتریان", "جزئیات مشتری", …]`, for the console's checklist.

    Only the gated ones: a checkbox's job is to say what ticking it adds,
    and the pages that are always there are not that.
    """
    return {
        feature: [title for _name, title in rows]
        for feature, rows in pages_by_feature().items()
        if feature is not None
    }
