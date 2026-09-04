"""Persian words for the stored codes, in one place on the Python side.

Several model enums in this codebase carry English `TextChoices` labels
(`Invoice.Status` is `Draft/Issued/Cancelled`, `Payment.Method` is
`Cash/Card/…`), because the stored value is a contract and the label was
never the thing being read: every page renders these through its own map.
Until now the only Python copy lived in `common/ui_views.py`, for the two
maps the printed invoice needed, and everything else was translated in
`common/static/common/dolphin-app.js`.

The customer timeline composes its own sentences server-side, so it needs
these words in Python too. Rather than a second copy beside the first, the
Python-side maps live here and `ui_views` imports them.

`dolphin-app.js` still holds its own copies (`DOCUMENT_STATUS_TEXT`,
`PAYMENT_METHOD_TEXT`, …) and that is deliberate: those pages render rows
the API sends as raw codes, in the browser, with no round trip to ask what
a word is. The two sides must agree, and `common/tests/test_label_coverage.py`
is where that is held.
"""

#: Quotation, order and invoice statuses — one graph per document, but the
#: words overlap, so one map covers all three.
DOCUMENT_STATUS_LABELS = {
    "draft": "پیش‌نویس",
    "sent": "ارسال‌شده",
    "accepted": "پذیرفته‌شده",
    "rejected": "ردشده",
    "expired": "منقضی‌شده",
    "cancelled": "لغوشده",
    "confirmed": "تأییدشده",
    "fulfilled": "تحویل‌شده",
    "issued": "صادرشده",
}

SETTLEMENT_LABELS = {
    "unpaid": "تسویه‌نشده",
    "partially_paid": "تسویه جزئی",
    "paid": "تسویه کامل",
}

PAYMENT_METHOD_LABELS = {
    "cash": "نقدی",
    "card": "کارت‌خوان",
    "bank_transfer": "حواله بانکی",
    "cheque": "چک",
}

INTERACTION_DIRECTION_LABELS = {
    "inbound": "ورودی",
    "outbound": "خروجی",
}

OUTBOUND_SMS_STATUS_LABELS = {
    "sent": "ارسال‌شده",
    "failed": "ناموفق",
}

INBOUND_SMS_STATE_LABELS = {
    "unmatched": "بدون تطبیق",
    "linked": "تطبیق‌یافته",
}


def label(mapping, value):
    """The Persian word for a stored code, or the code itself.

    Falling back to the raw value rather than to an empty string on purpose:
    a code nobody has translated yet should look untranslated, not missing.
    """
    return mapping.get(value, value)
