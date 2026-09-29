"""The Asterisk provider (2.22.0) — FreePBX or plain Asterisk 22 over AMI.

Everything a PBX differs in is a setting here, not code: the AMI address and
credentials, how Dolphin places a call (context and channel pattern), what
counts as an internal extension, where CDRs and recordings live, and the
PBX's time zone.
"""

import asyncio

from integrations.providers import ConfigField, ConnectionResult, Provider, register

#: Connection kinds that carry calls.
PBX_KEYS = ("asterisk", "pbx_webhook")


class AsteriskProvider(Provider):
    key = "asterisk"
    name = "مرکز تلفن Asterisk / FreePBX"
    description = (
        "تماس‌های ورودی و خروجی از رابط مدیریت Asterisk (AMI) خوانده می‌شود و به مشتری یا همکار "
        "تطبیق داده می‌شود؛ سوابق تماس (CDR) کمبودها را پر می‌کند؛ ضبط مکالمه از داخل دلفین پخش "
        "می‌شود و تماس با یک کلیک از پروفایل برقرار می‌شود."
    )
    capabilities = ("telephony",)
    required_feature = "telephony"
    presets = (
        {"key": "freepbx", "label": "FreePBX", "note": "نسخه‌های ۱۵ به بعد؛ CDR در asteriskcdrdb.cdr و ضبط‌ها در /var/spool/asterisk/monitor.",
         "values": {"originate_context": "from-internal", "originate_channel": "Local/{extension}@from-internal",
                    "cdr_database": "asteriskcdrdb", "cdr_table": "cdr", "internal_extension_max_length": 5}},
        {"key": "issabel", "label": "Issabel / Elastix", "note": "همان ساختار FreePBX؛ کاربر AMI را در manager_custom.conf بسازید.",
         "values": {"originate_context": "from-internal", "originate_channel": "Local/{extension}@from-internal",
                    "cdr_database": "asteriskcdrdb", "cdr_table": "cdr", "internal_extension_max_length": 5}},
        {"key": "vitalpbx", "label": "VitalPBX", "note": "نام context برقراری تماس در نصب شما را از مستند VitalPBX بررسی کنید؛ مقدار پیشنهادی تأییدنشده است.",
         "values": {"originate_context": "cos-all", "originate_channel": "Local/{extension}@cos-all",
                    "cdr_database": "asteriskcdrdb", "cdr_table": "cdr", "internal_extension_max_length": 5}},
        {"key": "asterisk", "label": "Asterisk ساده", "note": "context و پایگاه CDR را مطابق extensions.conf و cdr_adaptive_odbc خودتان بگذارید.",
         "values": {"originate_context": "default", "originate_channel": "Local/{extension}@default",
                    "cdr_table": "cdr", "internal_extension_max_length": 4}},
    )
    fields = (
        ConfigField("ami_host", "نشانی AMI", required=True, placeholder="10.0.0.5", help="میزبان مرکز تلفن؛ درگاه AMI فقط برای نشانی دلفین باز باشد.", ltr=True),
        ConfigField("ami_port", "درگاه AMI", kind="int", default=5038),
        ConfigField("ami_username", "نام کاربری AMI", required=True, help="یک کاربر مخصوص دلفین در manager.conf با read=call,cdr,agent و write=originate.", ltr=True),
        ConfigField("ami_password", "گذرواژهٔ AMI", kind="password", required=True),
        ConfigField("internal_extension_max_length", "بیشترین طول شمارهٔ داخلی", kind="int", default=5,
                    help="شماره‌ای با این طول یا کوتاه‌تر داخلی شمرده می‌شود (مگر در فهرست داخلی‌ها باشد)."),
        ConfigField("outbound_prefix", "پیش‌شمارهٔ خط بیرون", placeholder="مثلاً 9", help="اگر برای گرفتن خط بیرون رقمی پیش از شماره لازم است.", ltr=True),
        ConfigField("originate_context", "Context برقراری تماس", default="from-internal", ltr=True),
        ConfigField("originate_channel", "الگوی کانال برقراری تماس", default="Local/{extension}@from-internal",
                    help="{extension} با داخلی کاربر جایگزین می‌شود؛ اول تلفن کاربر زنگ می‌خورد، سپس شماره گرفته می‌شود.", ltr=True),
        ConfigField("originate_timeout", "مهلت پاسخ داخلی (ثانیه)", kind="int", default=30),
        ConfigField("originate_caller_id", "شناسهٔ تماس‌گیرنده", placeholder="مثلاً Dolphin <201>", ltr=True),
        ConfigField("cdr_host", "میزبان پایگاه CDR", placeholder="10.0.0.5", ltr=True),
        ConfigField("cdr_port", "درگاه پایگاه CDR", kind="int", default=3306),
        ConfigField("cdr_database", "نام پایگاه CDR", default="asteriskcdrdb", ltr=True),
        ConfigField("cdr_table", "جدول CDR", default="cdr", ltr=True),
        ConfigField("cdr_username", "کاربر پایگاه CDR", help="کاربری با فقط اجازهٔ SELECT روی جدول CDR.", ltr=True),
        ConfigField("cdr_password", "گذرواژهٔ پایگاه CDR", kind="password"),
        ConfigField("recordings_mode", "دسترسی به ضبط مکالمه", kind="select", default="none",
                    choices=(("none", "ندارد"), ("mount", "پوشهٔ متصل (فقط‌خواندنی)"), ("url", "سرویس HTTPS مرکز تلفن"))),
        ConfigField("recordings_path", "مسیر پوشهٔ ضبط", default="/recordings", help="مسیر پوشهٔ متصل داخل کانتینر دلفین.", ltr=True),
        ConfigField("recordings_base_url", "نشانی پایهٔ ضبط (https)", kind="url"),
        ConfigField("recordings_username", "کاربر سرویس ضبط", ltr=True),
        ConfigField("recordings_password", "گذرواژهٔ سرویس ضبط", kind="password"),
        ConfigField("pbx_timezone", "منطقهٔ زمانی مرکز تلفن", default="Asia/Tehran", ltr=True),
        ConfigField("missed_call_task", "ساخت وظیفه برای تماس بی‌پاسخ مشتری", kind="bool", default=True),
        ConfigField("call_popup", "پنجرهٔ تماس ورودی", kind="bool", default=True),
    )

    def validate(self, config, secrets):
        errors = {}
        if "{extension}" not in (config.get("originate_channel") or "{extension}"):
            errors["originate_channel"] = "الگو باید {extension} داشته باشد."
        if config.get("recordings_mode") == "url" and not str(config.get("recordings_base_url", "")).startswith("https://"):
            errors["recordings_base_url"] = "برای حالت سرویس، نشانی https لازم است."
        return errors

    def test_connection(self, integration, config, secrets):
        from telephony.ami import AMIConnection

        async def probe():
            connection = await AMIConnection.open(config["ami_host"], int(config.get("ami_port") or 5038))
            try:
                await connection.login(config["ami_username"], secrets.get("ami_password", ""))
                await connection.ping()
                return connection.banner
            finally:
                await connection.close()

        try:
            banner = asyncio.run(asyncio.wait_for(probe(), 20))
        except Exception as error:  # noqa: BLE001 — the reason is the answer
            return ConnectionResult(False, f"AMI پاسخ نداد یا ورود رد شد: {type(error).__name__}: {error}"[:300])
        message = f"AMI متصل است ({banner})."
        from telephony.cdr import CdrUnavailable, configured, fetch_rows

        if configured(config):
            from django.utils import timezone

            try:
                now = timezone.now()
                fetch_rows(config, secrets, now, now, limit=1)
                message += " پایگاه CDR هم در دسترس است."
            except CdrUnavailable as error:
                return ConnectionResult(False, f"{message} اما {error}")
        return ConnectionResult(True, message)


register(AsteriskProvider())
