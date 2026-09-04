"""One search box for the whole panel.

Product-owner request (2026-09-04): finding a customer by phone meant
remembering which page holds customers, opening it, and filling in that
page's own filter — fifty-one pages in, that is the panel's biggest
navigation cost. This module answers "where is X" across every module at
once.

The same three shapes as `common/reminders.py`, for the same reasons:

**No index, no new table.** Each source is a plain `icontains` over columns
the owning module already declares searchable — the very `search_fields`
its own list endpoint uses, so a name found here is a name that page would
have found too. Postgres full-text search would mean a migration, a
`SearchVector` column per model, and a Persian text configuration this
deployment has no basis to choose; a panel whose largest table is measured
in thousands does not need one yet. If it ever does, this module is the one
place that changes.

**Object scope is not reimplemented.** Every query starts from the owning
module's selector (`customers_for`, `leads_for`, `invoices_for`, …), each of
which already returns nothing for a role that may not see those rows. Only
feature availability is checked here.

**Digits are normalised both ways.** The panel *prints* Persian digits
(1.7.14), so a user who copies an invoice number off the screen types
«۱۴۰۵-۰۰۱۲» and must still find it; a user typing a phone from a Latin
keyboard must find the same customer. Every numeric column is therefore
matched against the Latin form of whatever was typed, and phone columns
against its bare digits, since `CustomerPhone.normalized_phone` is stored as
`+98…` and nobody types it that way.
"""

import re

from django.db.models import Q

from aftersales.selectors import after_sales_requests_for
from billing.selectors import invoices_for, orders_for, payments_for
from common.deployment.profile import feature_enabled
from common.jalali import to_latin_digits
from sales.selectors import (
    customers_for,
    leads_for,
    products_for,
    sales_documents_for,
)

#: Shorter than this and every source matches nearly everything, which is
#: slow to produce and useless to read.
MIN_QUERY_LENGTH = 2

#: Rows per group. This is a "jump straight to it" box, not a report: when
#: the right answer is not in the first few, the module's own list page with
#: its real filters is the better tool, and each group links to it.
GROUP_LIMIT = 5

_NON_DIGITS = re.compile(r"[^0-9]")

#: Below this, a digit string matches nearly every phone in the book and the
#: clause is worth more noise than it saves — `09` would match all of them.
MIN_PHONE_DIGITS = 3

#: What a typed Iranian number may carry in front of the part that is
#: actually stored. `CustomerPhone.normalized_phone` holds `+98` followed by
#: ten digits with no leading zero (see `common/phones.py`), so a typed
#: `0912…`, `98912…` or `0098912…` all have to lose their prefix before they
#: can match. Longest first, so `0098` is not mistaken for `0`.
_PHONE_PREFIXES = ("0098", "98", "0")


def _phone_digits(text):
    """The part of a typed number that could appear in a stored one.

    Returns `""` when there is too little to go on, which drops the phone
    clause from the query entirely rather than matching everything.
    """
    digits = _NON_DIGITS.sub("", to_latin_digits(text))
    for prefix in _PHONE_PREFIXES:
        if digits.startswith(prefix) and len(digits) > len(prefix):
            digits = digits[len(prefix):]
            break
    return digits if len(digits) >= MIN_PHONE_DIGITS else ""


def _customer_results(user, *, text, latin, digits):
    matches = Q(full_name__icontains=text) | Q(national_id__icontains=latin) | Q(city__icontains=text)
    if digits:
        # Stored as `+98XXXXXXXXXX`, so a typed `0912…` only ever matches by
        # its tail — `contains`, deliberately not `startswith`.
        matches |= Q(phones__normalized_phone__contains=digits)
    found = customers_for(user).filter(matches).distinct().order_by("full_name", "id")
    return _group(
        "customers", "مشتریان", "ki-profile-user", "primary", "/customers/", found,
        lambda row: (row.full_name, row.city or row.national_id or "بدون اطلاعات تکمیلی", f"/customers/{row.pk}/"),
    )


def _lead_results(user, *, text, latin, digits):
    matches = (
        Q(customer__full_name__icontains=text)
        | Q(source__icontains=text)
        | Q(campaign_or_batch__icontains=text)
    )
    found = leads_for(user).filter(matches).select_related("customer").distinct().order_by("-id")
    return _group(
        "leads", "سرنخ‌ها", "ki-call", "info", "/leads/", found,
        lambda row: (
            getattr(row.customer, "full_name", "") or f"سرنخ #{row.pk}",
            row.source or row.campaign_or_batch or "بدون منبع ثبت‌شده",
            f"/leads/{row.pk}/",
        ),
    )


def _product_results(user, *, text, latin, digits):
    matches = (
        Q(name__icontains=text) | Q(sku__icontains=latin) | Q(barcode__icontains=latin)
        | Q(brand__icontains=text)
    )
    found = products_for(user).filter(matches).distinct().order_by("name", "id")
    return _group(
        "products", "محصولات", "ki-package", "success", "/products/", found,
        lambda row: (row.name, row.sku or row.barcode or "بدون کد", f"/products/{row.pk}/"),
    )


def _invoice_results(user, *, text, latin, digits):
    return _document_group(
        invoices_for(user), text=text, latin=latin,
        kind="invoices", label="فاکتورها", icon="ki-document", accent="warning", path="/invoices/",
    )


def _order_results(user, *, text, latin, digits):
    return _document_group(
        orders_for(user), text=text, latin=latin,
        kind="orders", label="سفارش‌ها", icon="ki-basket", accent="info", path="/orders/",
    )


def _payment_results(user, *, text, latin, digits):
    matches = (
        Q(number__icontains=latin) | Q(customer__full_name__icontains=text)
        | Q(payee__icontains=text) | Q(reference__icontains=latin)
    )
    found = payments_for(user).filter(matches).select_related("customer").distinct().order_by("-id")
    return _group(
        "payments", "دریافت و پرداخت", "ki-dollar", "success", "/payments/", found,
        lambda row: (
            row.number,
            getattr(row.customer, "full_name", "") or row.payee or "بدون طرف حساب",
            f"/payments/{row.pk}/",
        ),
    )


def _sales_document_results(user, *, text, latin, digits):
    matches = (
        Q(document_number__icontains=latin)
        | Q(customer__full_name__icontains=text)
        | Q(postal_status__icontains=text)
    )
    found = sales_documents_for(user).filter(matches).select_related("customer").distinct().order_by("-id")
    return _group(
        "sales_documents", "اسناد فروش", "ki-delivery", "primary", "/sales-documents/", found,
        lambda row: (
            row.document_number,
            getattr(row.customer, "full_name", "") or row.postal_status or "—",
            f"/sales-documents/{row.pk}/",
        ),
    )


def _after_sales_results(user, *, text, latin, digits):
    matches = (
        Q(subject__icontains=text) | Q(customer__full_name__icontains=text) | Q(status__icontains=text)
    )
    found = (
        after_sales_requests_for(user).filter(matches).select_related("customer").distinct().order_by("-id")
    )
    return _group(
        "after_sales", "خدمات پس از فروش", "ki-wrench", "danger", "/after-sales/", found,
        lambda row: (
            getattr(row.customer, "full_name", "") or f"پرونده #{row.pk}",
            row.subject or row.status,
            f"/after-sales/{row.pk}/",
        ),
    )


def _document_group(queryset, *, text, latin, kind, label, icon, accent, path):
    """Invoices and orders differ only in their label and their URL."""
    matches = (
        Q(number__icontains=latin)
        | Q(customer__full_name__icontains=text)
        | Q(items__product_name_snapshot__icontains=text)
    )
    found = queryset.filter(matches).select_related("customer").distinct().order_by("-id")
    return _group(
        kind, label, icon, accent, path, found,
        lambda row: (
            row.number,
            getattr(row.customer, "full_name", "") or "—",
            f"{path}{row.pk}/",
        ),
    )


#: Every source, in the order the panel lists them: who first, then what,
#: then the paperwork. Each entry pairs the feature that must be enabled
#: with the function that reads it.
SOURCES = (
    ("customers", _customer_results),
    ("leads", _lead_results),
    ("products", _product_results),
    ("invoices", _invoice_results),
    ("orders", _order_results),
    ("payments", _payment_results),
    ("sales_documents", _sales_document_results),
    ("after_sales", _after_sales_results),
)


def search(user, query):
    """Everything matching `query` that this user may see, grouped by module.

    Returns `{"query": str, "count": int, "groups": [...]}`. `count` is the
    true total across every source, not the number of rows listed — each
    group is capped at `GROUP_LIMIT` and carries the `list_url` of the page
    that can show the rest. A query shorter than `MIN_QUERY_LENGTH` returns
    no groups rather than an error: the box is typed into one letter at a
    time, and the first letter is not a mistake to report.
    """
    text = (query or "").strip()
    if len(text) < MIN_QUERY_LENGTH:
        return {"query": text, "count": 0, "groups": []}
    latin = to_latin_digits(text)
    digits = _phone_digits(text)
    groups = []
    for feature, source in SOURCES:
        if not feature_enabled(feature):
            continue
        group = source(user, text=text, latin=latin, digits=digits)
        if group["count"]:
            groups.append(group)
    return {"query": text, "count": sum(group["count"] for group in groups), "groups": groups}


def _group(kind, label, icon, accent, list_url, queryset, describe):
    """Build one group, counting the whole match but listing only a page."""
    total = queryset.count()
    items = []
    for row in queryset[:GROUP_LIMIT]:
        title, subtitle, url = describe(row)
        items.append({"id": row.pk, "title": title, "subtitle": subtitle, "url": url})
    return {
        "kind": kind,
        "label": label,
        "icon": icon,
        "accent": accent,
        "list_url": list_url,
        "count": total,
        "items": items,
    }
