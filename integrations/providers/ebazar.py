"""Iran Post — «بازار الکترونیک» (Ebazar) shipping (2.29.0).

The connection Dolphin uses to register parcels, quote postage, follow a
parcel's status and read the shop's post wallet. The username and password are
the shop's web-service credentials, stored encrypted like every integration's
secrets. What the operator does with the connection lives on the sales
document (`sales.shipping`); this module only says how to reach the service.
"""

from integrations.providers import ConfigField, ConnectionResult, Provider, register
from sales import ebazar

FIELD_TIMEOUT_DEFAULT = 20


class EbazarPostProvider(Provider):
    key = "ebazar_post"
    name = "پست ایران — بازار الکترونیک"
    description = (
        "ثبت مرسوله، محاسبهٔ هزینهٔ ارسال، دریافت کد رهگیری و پیگیری وضعیت مرسوله در سامانهٔ "
        "بازار الکترونیک پست ایران، با اطلاعات وب‌سرویس فروشگاه شما."
    )
    capabilities = ("shipping",)
    required_feature = "sales_documents"
    singleton = True
    fields = (
        ConfigField(
            "base_url", "نشانی سرویس", kind="url", required=True, default=ebazar.DEFAULT_BASE_URL, ltr=True,
            help="نشانی پایهٔ وب‌سرویس که پست به شما داده؛ معمولاً همان مقدار پیش‌فرض است.",
        ),
        ConfigField(
            "username", "نام کاربری وب‌سرویس", secret=True, required=True, ltr=True,
            help="نام کاربری‌ای که پست برای وب‌سرویس فروشگاه شما صادر کرده (نه ورود به پنل بازار الکترونیک).",
        ),
        ConfigField("password", "گذرواژهٔ وب‌سرویس", kind="password", required=True),
        ConfigField(
            "default_service_type", "نوع سرویس پیش‌فرض", kind="select", default="1",
            choices=tuple((str(code), label) for code, label in ebazar.SERVICE_TYPES.items()),
            help="هنگام ثبت مرسوله پیشنهاد می‌شود و برای هر مرسوله قابل تغییر است. مرسولهٔ بالای ۵۰۰۰ گرم باید «پیشتاز» باشد.",
        ),
        ConfigField(
            "default_pay_type", "نوع پرداخت پیش‌فرض", kind="select", default="1",
            choices=tuple((str(code), label) for code, label in ebazar.PAY_TYPES.items()),
            help="چه کسی و کجا هزینهٔ کالا و پست را می‌پردازد. هر مرسوله می‌تواند نوع دیگری بگیرد.",
        ),
        ConfigField(
            "sms_service", "پیامک اطلاع‌رسانی تحویل", kind="bool", default=False,
            help="پست هنگام تحویل به گیرنده پیامک می‌فرستد (هزینهٔ جداگانه دارد).",
        ),
        ConfigField(
            "pod", "اثبات تحویل (POD)", kind="bool", default=False,
            help="تحویل فقط با کد تأییدی که گیرنده دارد انجام می‌شود.",
        ),
        ConfigField(
            "timeout_seconds", "مهلت پاسخ (ثانیه)", kind="int", default=FIELD_TIMEOUT_DEFAULT,
            help="سرویس پست گاهی کند است؛ کمتر از ۱۰ ثانیه توصیه نمی‌شود.",
        ),
    )

    def validate(self, config, secrets):
        errors = {}
        if not 1 <= int(config.get("timeout_seconds") or FIELD_TIMEOUT_DEFAULT) <= 120:
            errors["timeout_seconds"] = "مهلت باید بین ۱ تا ۱۲۰ ثانیه باشد."
        return errors

    def test_connection(self, integration, config, secrets):
        try:
            client = client_for(config, secrets)
            client.forget_token()
            client.token()
            wallet = client.wallet_credit() or {}
        except ebazar.EbazarError as error:
            return ConnectionResult(False, error.message)
        credit = wallet.get("Credit")
        suffix = f" اعتبار کیف پول پست: {int(credit):,} ریال." if isinstance(credit, (int, float)) else ""
        return ConnectionResult(True, "ورود به سرویس پست پذیرفته شد." + suffix)


def client_for(config, secrets):
    return ebazar.EbazarClient(
        base_url=config.get("base_url") or ebazar.DEFAULT_BASE_URL,
        username=secrets.get("username", ""),
        password=secrets.get("password", ""),
        timeout=int(config.get("timeout_seconds") or FIELD_TIMEOUT_DEFAULT),
    )


register(EbazarPostProvider())
