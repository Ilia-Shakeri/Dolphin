"""The webhook PBX provider (2.30.0) - any PBX that can push call events.

Where the Asterisk provider speaks AMI, this one is *pushed to*: the PBX (or a
small script beside it) posts JSON to the connection's webhook address and the
chosen vendor parser (`telephony.vendors`) turns it into calls. Calls, the
popup, missed-call tasks, recordings and click-to-call then behave exactly as
with Asterisk. Per-vendor set-up is in `docs/ops/PBX_CONNECTION_GUIDES.md`.
"""

import base64
import hashlib
import hmac
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from common.deployment.profile import feature_enabled
from integrations.providers import ConfigField, ConnectionResult, Provider, register
from telephony import vendors
from telephony.vendors import PayloadError

logger = logging.getLogger("dolphin.telephony.webhook")

MAX_EVENTS = 200


def _zone(config):
    try:
        return ZoneInfo(config.get("pbx_timezone") or "Asia/Tehran")
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Tehran")


class PbxWebhookProvider(Provider):
    key = "pbx_webhook"
    name = "مرکز تلفن با وب‌هوک (Yeastar، Grandstream، FreeSWITCH و هر مرکز دیگر)"
    description = (
        "مرکز تلفن رویداد تماس را به نشانی وب‌هوک دلفین می‌فرستد؛ دلفین تماس را ذخیره، به مشتری "
        "تطبیق و اعلان می‌کند. برای هر برند یک قالب آماده هست و هر سامانهٔ دیگری با قالب استاندارد "
        "دلفین وصل می‌شود. برقراری تماس از پنل در صورت داشتن API تماس مرکز تلفن ممکن است."
    )
    capabilities = ("telephony", "webhook")
    required_feature = "telephony"
    accepts_webhooks = True
    fields = (
        ConfigField("vendor", "برند / قالب رویداد", kind="select", required=True, default="generic",
                    choices=tuple((vendor.key, vendor.label) for vendor in vendors.VENDORS.values()),
                    help="قالبی که مرکز تلفن شما می‌فرستد. راهنمای هر برند در مستند اتصال مرکز تلفن است."),
        ConfigField("signing_secret", "کلید امضا / توکن", kind="password", required=True, secret=True,
                    help="همان کلیدی که در مرکز تلفن برای امضا یا توکن وب‌هوک گذاشته‌اید (حداقل ۱۶ نویسه)."),
        ConfigField("internal_extension_max_length", "بیشترین طول شمارهٔ داخلی", kind="int", default=5,
                    help="شماره‌ای با این طول یا کوتاه‌تر داخلی شمرده می‌شود (مگر در فهرست داخلی‌ها باشد)."),
        ConfigField("outbound_prefix", "پیش‌شمارهٔ خط بیرون", placeholder="مثلاً 9", ltr=True),
        ConfigField("pbx_timezone", "منطقهٔ زمانی مرکز تلفن", default="Asia/Tehran", ltr=True,
                    help="زمان‌های بدون منطقه در رویداد به این منطقه خوانده می‌شوند."),
        ConfigField("missed_call_task", "ساخت وظیفه برای تماس بی‌پاسخ مشتری", kind="bool", default=True),
        ConfigField("call_popup", "پنجرهٔ تماس ورودی", kind="bool", default=True),
        ConfigField("recordings_mode", "دسترسی به ضبط مکالمه", kind="select", default="none",
                    choices=(("none", "ندارد"), ("mount", "پوشهٔ متصل (فقط‌خواندنی)"), ("url", "سرویس HTTPS مرکز تلفن"))),
        ConfigField("recordings_path", "مسیر پوشهٔ ضبط", default="/recordings", ltr=True),
        ConfigField("recordings_base_url", "نشانی پایهٔ ضبط (https)", kind="url"),
        ConfigField("recordings_username", "کاربر سرویس ضبط", ltr=True),
        ConfigField("recordings_password", "گذرواژهٔ سرویس ضبط", kind="password"),
        ConfigField("dial_mode", "برقراری تماس از دلفین", kind="select", default="none",
                    choices=(("none", "ندارد"), ("yeastar", "Yeastar OpenAPI"), ("http", "درخواست HTTP دلخواه")),
                    help="بدون API تماس، اعلان و ذخیرهٔ تماس‌ها کار می‌کند ولی دکمهٔ تماس نیست."),
        ConfigField("api_base_url", "نشانی API مرکز تلفن", kind="url", placeholder="https://pbx.example.com:8088"),
        ConfigField("api_username", "نام کاربری / Client ID API", ltr=True),
        ConfigField("api_password", "گذرواژه / Client Secret API", kind="password"),
        ConfigField("api_token", "توکن API (به‌جای نام کاربری و گذرواژه)", kind="password"),
        ConfigField("api_verify_tls", "بررسی گواهی TLS مرکز تلفن", kind="bool", default=True),
        ConfigField("dial_url", "نشانی درخواست تماس (حالت دلخواه)", kind="url", ltr=True,
                    help="می‌تواند {extension} و {number} داشته باشد."),
        ConfigField("dial_method", "روش درخواست تماس", kind="select", default="POST", choices=(("POST", "POST"), ("GET", "GET"))),
        ConfigField("dial_body", "قالب بدنهٔ JSON درخواست تماس", ltr=True, placeholder='{"from": "{extension}", "to": "{number}"}'),
        ConfigField("dial_call_id_key", "کلید شناسهٔ تماس در پاسخ", placeholder="مثلاً data.call_id", ltr=True,
                    help="اگر پاسخ شناسهٔ تماس می‌دهد، رویدادهای همان تماس به همین ردیف وصل می‌شوند."),
    )

    def validate(self, config, secrets):
        errors = {}
        if len(secrets.get("signing_secret", "")) < 16:
            errors["signing_secret"] = "کلید امضا دست‌کم ۱۶ نویسه باشد."
        if config.get("recordings_mode") == "url" and not str(config.get("recordings_base_url", "")).startswith("https://"):
            errors["recordings_base_url"] = "برای حالت سرویس، نشانی https لازم است."
        mode = config.get("dial_mode") or "none"
        if mode == "yeastar" and not config.get("api_base_url"):
            errors["api_base_url"] = "برای Yeastar نشانی API لازم است."
        if mode == "yeastar" and not (secrets.get("api_token") or (config.get("api_username") and secrets.get("api_password"))):
            errors["api_password"] = "نام کاربری و گذرواژهٔ API یا توکن لازم است."
        if mode == "http" and not config.get("dial_url"):
            errors["dial_url"] = "نشانی درخواست تماس لازم است."
        if config.get("pbx_timezone"):
            try:
                ZoneInfo(config["pbx_timezone"])
            except (ZoneInfoNotFoundError, ValueError):
                errors["pbx_timezone"] = "منطقهٔ زمانی شناخته‌شده نیست (مثلاً Asia/Tehran)."
        return errors

    def test_connection(self, integration, config, secrets):
        vendor = vendors.VENDORS.get(config.get("vendor") or "generic")
        note = "" if vendor is None or vendor.key in vendors.VERIFIED else " (قالب بر پایهٔ مستند سازنده است؛ با یک تماس آزمایشی تأیید کنید)"
        return ConnectionResult(
            True,
            "آمادهٔ دریافت است؛ نشانی وب‌هوک را در مرکز تلفن بگذارید و یک تماس آزمایشی بگیرید. "
            "دریافت اولین رویداد وضعیت اتصال را تأیید می‌کند." + note,
        )

    def verify_inbound(self, integration, secrets, request, body):
        secret = secrets.get("signing_secret", "")
        if not secret:
            return False
        key = secret.encode("utf-8")
        digest = hmac.new(key, body, hashlib.sha256).digest()
        candidates = (
            (request.headers.get("X-Signature", ""), base64.b64encode(digest).decode()),
            (request.headers.get("X-Dolphin-Signature", "").removeprefix("sha256="), digest.hex()),
        )
        for given, expected in candidates:
            if given and hmac.compare_digest(given.strip(), expected):
                return True
        token = request.headers.get("X-Dolphin-Token") or request.GET.get("token") or ""
        return bool(token) and hmac.compare_digest(token.encode("utf-8"), key)

    def handle_inbound(self, integration, config, payload):
        from telephony.ingest import apply_event
        from telephony.tracker import CallTracker

        if not feature_enabled("telephony"):
            return "تلفن در این استقرار فعال نیست؛ رویداد نادیده گرفته شد."
        if payload.get("event") == "test":
            return "پیام آزمایشی مرکز تلفن دریافت شد."
        vendor = vendors.VENDORS.get(config.get("vendor") or "generic", vendors.VENDORS["generic"])
        try:
            events = vendor.parse(payload, _zone(config))
        except PayloadError as error:
            raise_bad(str(error))
        tracker = CallTracker(integration)
        applied = 0
        for event in events[:MAX_EVENTS]:
            apply_event(integration, tracker, event)
            applied += 1
        return f"{applied} رویداد تماس ثبت شد." if applied else "رویداد تماس نداشت؛ نادیده گرفته شد."


def raise_bad(message):
    from common.exceptions import BusinessRuleError

    raise BusinessRuleError({"body": message})


register(PbxWebhookProvider())
