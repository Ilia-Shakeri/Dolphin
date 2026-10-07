"""Every error a reader sees, in Persian (2.40.35).

Product owner, 2026-10-07: «تمامی ارورها در تمامی صفحه‌ها و ویزاردها باید تماماً
فارسی باشند تا فهم بهتری برای یوزرها داشته باشند».

Django and DRF already answer in Persian (`LANGUAGE_CODE = "fa"`), but a few of
their messages carry the machinery with them — «باید pk ارسال می‌شد اما str»,
«از یکی از این فرمت‌ها استفاده کنید: YYYY-MM-DD», «متد PATCH مجاز نیست» — and one
(`get_object_or_404`'s «No Attachment matches the given query.») is not
translated at all. `persianise` replaces exactly those, by the error's own code,
with a sentence a reader can act on; a business message — Persian by
construction, sometimes with a deliberate Latin word such as «xlsx» or a
document number — is left as it is.

`network_reason` does the same for the network failures an integration test
reports (`ConnectionRefusedError`, `[WinError 10061] …`): what happened, in
Persian, instead of the exception's name.
"""

import re
import socket
import ssl
import urllib.error

from rest_framework.exceptions import ErrorDetail

_PERSIAN = re.compile(r"[؀-ۿ]")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
#: Words that only ever come from the framework, never from a business rule.
_TECHNICAL = re.compile(
    r"\b(pk|str|int|dict|list|float|bool|JSON|YYYY|MM|DD|hh|mm|ss|uuuuuu|ISO|"
    r"PATCH|POST|PUT|GET|DELETE|HEAD|OPTIONS|query|matches|object)\b"
)

#: The reader's sentence for each framework error code.
BY_CODE = {
    "incorrect_type": "نوع مقدار واردشده درست نیست.",
    "does_not_exist": "مورد انتخاب‌شده پیدا نشد.",
    "invalid_choice": "گزینهٔ انتخاب‌شده معتبر نیست.",
    "not_a_list": "شکل داده‌های ارسال‌شده درست نیست.",
    "not_a_dict": "شکل داده‌های ارسال‌شده درست نیست.",
    "parse_error": "داده‌های ارسال‌شده قابل خواندن نیست.",
    "method_not_allowed": "این کار برای این بخش امکان‌پذیر نیست.",
    "not_found": "مورد خواسته‌شده پیدا نشد.",
    "unsupported_media_type": "نوع داده‌های ارسال‌شده پذیرفته نیست.",
    "not_acceptable": "پاسخ با این قالب در دسترس نیست.",
}
DATE_SENTENCE = "تاریخ یا زمان معتبر نیست؛ آن را از تقویم انتخاب کنید."
FALLBACK = "مقدار واردشده معتبر نیست."


def needs_persian(text):
    """A framework message that still speaks its own language."""
    if not isinstance(text, str) or not _LATIN_WORD.search(text):
        return False
    return not _PERSIAN.search(text) or bool(_TECHNICAL.search(text))


def _sentence_for(text, code):
    if "YYYY" in text or "hh:mm" in text:
        return DATE_SENTENCE
    if "dict" in text or "list" in text:
        return BY_CODE["not_a_dict"]
    return BY_CODE.get(code, FALLBACK)


def persianise(data):
    """`data` (a DRF error payload) with every machine-worded message replaced."""
    if isinstance(data, dict):
        return {key: (value if key == "error" else persianise(value)) for key, value in data.items()}
    if isinstance(data, list):
        return [persianise(value) for value in data]
    if isinstance(data, str) and needs_persian(data):
        code = getattr(data, "code", None)
        return ErrorDetail(_sentence_for(data, code), code=code)
    return data


def network_reason(error):
    """What went wrong talking to another server, in Persian."""
    if isinstance(error, urllib.error.URLError) and getattr(error, "reason", None) is not None:
        reason = error.reason
        if isinstance(reason, BaseException):
            return network_reason(reason)
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "سرور مقصد در زمان مقرر پاسخ نداد."
    if isinstance(error, ConnectionRefusedError):
        return "سرور مقصد اتصال را رد کرد (درگاه بسته است یا سرویس روشن نیست)."
    if isinstance(error, socket.gaierror):
        return "نشانی سرور مقصد پیدا نشد."
    if isinstance(error, ssl.SSLError):
        return "گواهی امنیتی (SSL) سرور مقصد پذیرفته نشد."
    if isinstance(error, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return "اتصال با سرور مقصد نیمه‌کاره قطع شد."
    if isinstance(error, ValueError):
        return "نشانی سرور مقصد معتبر نیست."
    if isinstance(error, OSError):
        return "ارتباط شبکه با سرور مقصد برقرار نشد."
    return "ارتباط با سرور مقصد ناموفق بود."


def http_answer(status, text=""):
    """A remote server's answer, for a diagnostic line: «پاسخ سرور مقصد (کد ۴۰۰): …»."""
    text = (text or "").strip()
    return f"پاسخ سرور مقصد (کد {status})" + (f": {text}" if text else "")


def ami_reason(error):
    """Why the phone exchange (Asterisk AMI) did not answer, in Persian."""
    if isinstance(error, (OSError, TimeoutError, ValueError)):
        return network_reason(error)
    return "نام کاربری یا گذرواژهٔ AMI پذیرفته نشد یا مرکز تلفن پاسخ نامعتبر داد."
