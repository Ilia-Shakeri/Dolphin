"""Client for Iran Post's «بازار الکترونیک» (Ebazar) web service, v1.0.0.10.

One module, no Django models: it speaks the documented protocol and hands
back plain data. Every call is a POST of JSON with a bearer token obtained
from `/token` (form-encoded username + password, `grant_type=password`); the
token is reused until its `expires_in`. A response is `{ResCode, ResMsg,
Data}`; a *batch* call also carries a per-item `Errors` list, and the
top-level `ResCode` alone does not say whether an item was accepted, so
`item_errors` is what callers check.

Credentials come from an `integrations.Integration` (encrypted at rest) and
are never logged or put in an exception message. Prices are rial and weights
are grams, exactly as the service defines them.
"""

import json
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://svc.ebazaar-post.ir/RestApi"
TOKEN_SAFETY_SECONDS = 60
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

SERVICE_TYPES = {
    0: "سفارشی",
    1: "پیشتاز",
    3: "مطبوعات (فقط فروشگاه‌های دارای قرارداد)",
}

PAY_TYPES = {
    0: "پرداخت در محل (COD)",
    1: "پرداخت آنلاین یا کارت‌به‌کارت به فروشگاه",
    88: "ارسال رایگان با پرداخت در محل",
    89: "هزینهٔ پست در مقصد",
    90: "اعتبار کیف پول برای پست، با پرداخت در محل",
    91: "اعتبار کیف پول برای پست، با پرداخت آنلاین",
}

#: `/token` failures come back as HTTP 400 with `{"error": "<code>"}`.
TOKEN_ERRORS = {
    "401": "اطلاعات فروشگاه یافت نشد.",
    "402": "فروشگاه در بازار الکترونیک غیرفعال است.",
    "403": "فروشگاه بدهکار است و دسترسی‌اش بسته شده.",
    "404": "دسترسی این فروشگاه به سامانه بسته است.",
    "405": "نام کاربری یا گذرواژه اشتباه است.",
    "406": "خطای سیستمی در سامانهٔ پست.",
    "407": "خطای سیستمی در سامانهٔ پست.",
    "408": "این کاربر مجوز استفاده از وب‌سرویس ندارد.",
}

RES_CODES = {
    -2: "خطای سیستمی در سامانهٔ پست.",
    -1: "تعداد فراخوانی از حد مجاز گذشته؛ کمی بعد دوباره تلاش کنید.",
    12: "مشکل در محاسبهٔ هزینهٔ ارسال یا پارامترها نامعتبر است.",
    13: "اطلاعات سفارش نامعتبر است.",
    14: "خطا در ثبت سفارش در درگاه پست.",
    16: "کد فروشگاه نامعتبر است.",
    17: "کد رهگیری خالی است.",
    18: "فهرست مرسوله‌ها خالی است.",
    19: "درخواست تغییر وضعیت نامعتبر است.",
    21: "مرسوله پیدا نشد.",
    22: "خطا در دریافت بارکد از درگاه.",
    25: "صورت‌حساب پیدا نشد.",
    26: "خطا در دریافت جزئیات صورت‌حساب.",
}

ERROR_CODES = {
    1101: "نام کالا خالی است.",
    1102: "موجودی کالا باید بیشتر از صفر باشد.",
    1103: "وزن کالا کمتر از حد مجاز است.",
    1104: "وزن کالا از ۳۰٬۰۰۰ گرم بیشتر است.",
    1105: "قیمت باید بین ۵۰٬۰۰۰ تا ۱٬۰۰۰٬۰۰۰٬۰۰۰ ریال باشد.",
    1106: "درصد تخفیف نامعتبر است.",
    1107: "درصد تخفیف نامعتبر است.",
    1121: "شناسهٔ کالا نامعتبر است.",
    1122: "شناسهٔ کالا نامعتبر است.",
    2101: "کد فروشگاه نامعتبر است.",
    2102: "استان نامعتبر است.",
    2103: "شهر نامعتبر است.",
    2106: "روش ارسال نامعتبر است.",
    2107: "این فروشگاه قرارداد «مطبوعات» ندارد.",
    2108: "نوع پرداخت نامعتبر است.",
    2109: "مرسولهٔ بیش از ۵۰۰۰ گرم باید «پیشتاز» ارسال شود.",
    2111: "وزن مرسوله مجاز نیست.",
    2112: "خطا در دریافت قیمت از درگاه.",
    2113: "خطا در دریافت قیمت از درگاه.",
    2201: "نام گیرنده خالی است.",
    2202: "نام خانوادگی گیرنده خالی است.",
    2203: "نشانی گیرنده خالی است.",
    2204: "تلفن گیرنده خالی است.",
    2205: "موبایل گیرنده خالی است.",
    2206: "ایمیل گیرنده خالی است.",
    2207: "نشانی IP خالی است.",
    2208: "کد پستی نامعتبر است.",
    2209: "فهرست کالاهای مرسوله خالی است.",
    2212: "کالای مرسوله نامعتبر است.",
    2213: "کالای مرسوله نامعتبر است.",
    2214: "کالای مرسوله نامعتبر است.",
    2215: "کالای مرسوله نامعتبر است.",
    2301: "کیوسک و پستی‌گاه با هم قابل استفاده نیستند یا با شهر نمی‌خوانند.",
    2302: "کیوسک با شهر انتخاب‌شده نمی‌خواند.",
    2303: "پستی‌گاه با شهر انتخاب‌شده نمی‌خواند.",
    2304: "کیوسک و پستی‌گاه را هم‌زمان انتخاب نکنید.",
    2305: "کیوسک یا پستی‌گاه نامعتبر است.",
    9003: "وضعیت مرسوله در این مرحله قابل تغییر نیست.",
    9101: "کد پستی نامعتبر است.",
    9501: "استان نامعتبر است.",
    9502: "شهر نامعتبر است.",
    9505: "شناسهٔ سفارش تکراری است؛ این سفارش قبلاً ثبت شده.",
}

#: `Order/ParcelStatus` → (label, Dolphin postal state or None). A state is
#: given only where the document makes the meaning plain; the rest keep the
#: provider's own words on screen and move nothing (see `sales.postal`).
PARCEL_STATUSES = {
    -1: ("پیدا نشد", None),
    0: ("تحت بررسی", "in_store"),
    1: ("انصرافی", None),
    2: ("آماده ارسال", "handed_to_post"),
    3: ("اشتباه در آماده به ارسال", None),
    4: ("عدم حضور مدیر", None),
    5: ("ارسال شده", "with_post"),
    6: ("عدم قبول", None),
    7: ("توزیع شده", "out_for_delivery"),
    8: ("باجه معطله", None),
    9: ("توقیفی", None),
    10: ("پیش برگشتی", None),
    11: ("برگشتی نهایی", None),
    70: ("تایید شده مالی", None),
    71: ("وصول شده", None),
    255: ("تایید برگشتی", None),
}
#: Statuses Iran Post shows on its tracking page that the web-service document
#: (v1.0.0.10) gives no numeric code for. They are kept so the guide lists the
#: complete set and so a status text from the carrier is recognised; no code is
#: guessed for them.
UNCODED_STATUSES = (
    "خسارتی",
    "وارده به استان توزیع",
    "تحویل به نامه رسان",
    "مراجعه اول",
    "مراجعه دوم",
    "توزیع درصندوق پستی",
    "بی ترتیبی(کسری مرسوله)",
    "توزیع درصندوق هوشمند (لاکرز)",
    "منقضی شده",
)
#: Statuses after which polling the parcel again tells nothing new.
FINAL_STATUS_CODES = frozenset({1, 7, 11, 71, 255})


def status_label(code):
    entry = PARCEL_STATUSES.get(code)
    return entry[0] if entry else f"وضعیت ناشناختهٔ پست (کد {code})"


def dolphin_state_for(code):
    entry = PARCEL_STATUSES.get(code)
    return entry[1] if entry else None


class EbazarError(Exception):
    """A failed call, with a message safe to show an operator."""

    def __init__(self, message, *, code=None):
        super().__init__(message)
        self.message = message
        self.code = code


def normalize_name(value):
    """A place name for comparison: Arabic letters folded, spaces squeezed."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    for arabic, persian in (("ي", "ی"), ("ك", "ک"), ("ة", "ه"), ("‌", " ")):
        text = text.replace(arabic, persian)
    return " ".join(text.split())


def error_message(code, fallback=""):
    try:
        number = int(code)
    except (TypeError, ValueError):
        return fallback or "خطای نامشخص."
    if number in ERROR_CODES:
        return ERROR_CODES[number]
    if number in RES_CODES:
        return RES_CODES[number]
    return fallback or f"خطای سامانهٔ پست (کد {number})."


def item_errors(item):
    """`["<code>: <message>", …]` for one batch-call item; empty when it passed."""
    out = []
    for error in (item or {}).get("Errors") or []:
        code = error.get("ErrorCode")
        out.append(f"{code}: {error_message(code, error.get('ErrorMessage') or '')}")
    return out


_TOKENS = {}
_TOKENS_LOCK = threading.Lock()


class EbazarClient:
    def __init__(self, *, base_url, username, password, timeout=20):
        parsed = urllib.parse.urlsplit(base_url or "")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise EbazarError("نشانی سرویس پست نامعتبر است.")
        self.base_url = base_url.rstrip("/")
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout
        if not self.username or not self.password:
            raise EbazarError("نام کاربری یا گذرواژهٔ سرویس پست تنظیم نشده است.")

    def _open(self, request):
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310 — admin-configured host
                return response.status, response.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as error:
            return error.code, error.read(MAX_RESPONSE_BYTES)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise EbazarError("اتصال به سرویس پست برقرار نشد یا زمان پاسخ تمام شد.") from error

    def token(self):
        key = (self.base_url, self.username)
        with _TOKENS_LOCK:
            cached = _TOKENS.get(key)
            if cached and cached[1] > time.monotonic():
                return cached[0]
        body = urllib.parse.urlencode(
            {"username": self.username, "password": self.password, "grant_type": "password"}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        status, raw = self._open(request)
        try:
            data = json.loads(raw.decode("utf-8", "replace") or "{}")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        if status != 200 or not data.get("access_token"):
            code = str(data.get("error", ""))
            raise EbazarError(
                TOKEN_ERRORS.get(code, f"ورود به سرویس پست پذیرفته نشد (HTTP {status})."),
                code=code or status,
            )
        lifetime = int(data.get("expires_in") or 0)
        with _TOKENS_LOCK:
            _TOKENS[key] = (data["access_token"], time.monotonic() + max(lifetime - TOKEN_SAFETY_SECONDS, 0))
        return data["access_token"]

    def forget_token(self):
        with _TOKENS_LOCK:
            _TOKENS.pop((self.base_url, self.username), None)

    def call(self, path, payload=None, *, _retried=False):
        """POST `payload`; the response's `Data`. A non-zero `ResCode` raises."""
        request = urllib.request.Request(
            f"{self.base_url}/api/v0/{path.lstrip(chr(47))}",
            data=json.dumps(payload if payload is not None else {}, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "bearer " + self.token(),
            },
            method="POST",
        )
        status, raw = self._open(request)
        if status == 401 and not _retried:
            self.forget_token()
            return self.call(path, payload, _retried=True)
        try:
            data = json.loads(raw.decode("utf-8", "replace") or "{}")
        except ValueError as error:
            raise EbazarError(f"پاسخ سرویس پست قابل خواندن نبود (HTTP {status}).") from error
        if not isinstance(data, dict):
            raise EbazarError("پاسخ سرویس پست ساختار انتظاری را ندارد.")
        code = data.get("ResCode")
        if status != 200 or code not in (0, None):
            raise EbazarError(error_message(code, data.get("ResMsg") or f"کد پاسخ {status}"), code=code)
        return data.get("Data")

    # -- the documented calls -------------------------------------------------

    def provinces(self):
        return self.call("BaseInfo/Province") or []

    def cities(self, province_code):
        return self.call("BaseInfo/City", {"ProvinceCode": province_code}) or []

    def box_sizes(self):
        return self.call("BaseInfo/BoxSize") or []

    def kiosks(self, province_code, city_id):
        return self.call("BaseInfo/Kiosk", {"ProvinceCode": province_code, "CityID": city_id}) or []

    def pudo_nodes(self, province_code, city_id):
        return self.call("BaseInfo/PudoPostNode", {"ProvinceCode": province_code, "CityID": city_id}) or []

    def delivery_price(self, items):
        return self.call("Order/DeliveryPrice", items) or []

    def add_parcel(self, items):
        return self.call("Order/AddParcel", items) or []

    def parcel_status(self, barcodes):
        return self.call("Order/ParcelStatus", list(barcodes)) or []

    def change_status(self, new_status, parcel_codes):
        return self.call("Order/ChangeStatus", {"NewStatus": new_status, "ParcelCodes": list(parcel_codes)}) or []

    def parcel_detail(self, parcel_code):
        return self.call("Order/ParcelDetail", {"ParcelCode": parcel_code})

    def inquiry(self, client_order_id):
        return self.call("Order/Inquiry", {"ClientOrderId": client_order_id})

    def product_add(self, items):
        return self.call("Product/Add", items) or []

    def wallet_credit(self):
        return self.call("Wallet/Credit")

    def billing(self, from_date, to_date, page=1):
        return self.call("Finance/Billing", {"FromDate": from_date, "ToDate": to_date, "Page": page}) or []
