"""The generic inbound webhook — any system that can POST signed JSON (2.21.0).

A messenger bot, a website form or an automation tool sends

    POST /api/v1/integrations/<id>/webhook/
    X-Dolphin-Signature: sha256=<hex HMAC-SHA256 of the raw body under the signing secret>
    {"id": "…", "type": "message.received", "channel": "telegram",
     "from": "+98912…", "text": "…", "occurred_at": "2026-09-27T10:00:00+03:30"}

and Dolphin matches the sender to a customer or colleague, records the
message on that person's timeline, and emits `message.received` to outbound
subscribers. `id` makes a retried delivery a no-op.
"""

import hashlib
import hmac

from integrations.providers import ConfigField, ConnectionResult, Provider, register

SUPPORTED_TYPES = ("message.received",)


class GenericWebhookProvider(Provider):
    key = "generic_webhook"
    name = "وب‌هوک ورودی عمومی"
    description = (
        "هر سامانه‌ای که بتواند JSON امضاشده بفرستد — ربات پیام‌رسان، فرم وب‌سایت یا ابزار اتوماسیون. "
        "فرستنده با شماره‌اش به مشتری یا همکار تطبیق داده و پیام در تاریخچهٔ او ثبت می‌شود."
    )
    capabilities = ("webhook", "messaging")
    accepts_webhooks = True
    fields = (
        ConfigField(
            "signing_secret", "کلید امضا (HMAC-SHA256)", kind="password", required=True,
            help="فرستنده با همین کلید بدنهٔ درخواست را امضا می‌کند (سرآیند X-Dolphin-Signature).",
        ),
        ConfigField(
            "channel_label", "نام کانال", placeholder="مثلاً تلگرام",
            help="در تاریخچه کنار پیام نوشته می‌شود وقتی خود پیام کانالی نام نبرد.",
        ),
    )

    def test_connection(self, integration, config, secrets):
        if not secrets.get("signing_secret"):
            return ConnectionResult(False, "کلید امضا تنظیم نشده است.")
        if not integration.enabled:
            return ConnectionResult(False, "اتصال خاموش است؛ درخواست‌های ورودی پذیرفته نمی‌شوند.")
        return ConnectionResult(
            True, "آمادهٔ دریافت است. اولین درخواست امضاشده به نشانی وب‌هوک، اتصال را واقعاً آزمایش می‌کند."
        )

    def verify_inbound(self, integration, secrets, request, body):
        header = request.headers.get("X-Dolphin-Signature", "")
        secret = secrets.get("signing_secret", "")
        if not secret or not header.startswith("sha256="):
            return False
        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header[len("sha256="):].strip())

    def handle_inbound(self, integration, config, payload):
        from integrations.events import emit
        from integrations.matching import best_match

        event_type = payload.get("type")
        if event_type not in SUPPORTED_TYPES:
            return f"نوع «{str(event_type)[:40]}» پشتیبانی نمی‌شود؛ نادیده گرفته شد."
        sender = str(payload.get("from") or "")[:64]
        match = best_match(sender)
        emit(
            "message.received",
            {
                "source": "webhook",
                "integration": integration.pk,
                "channel": str(payload.get("channel") or config.get("channel_label") or "")[:60],
                "from": sender,
                "text": str(payload.get("text") or "")[:2000],
                "external_id": str(payload.get("id") or "")[:128],
                "matched": match.how if match else "",
            },
            person_type=match.person_type if match else "",
            person_id=match.person_id if match else None,
            dedupe_key=f"inbound:{integration.pk}:{payload.get('id')}" if payload.get("id") else "",
        )
        return f"پیام از {sender or 'نامعلوم'}" + (f" — تطبیق با {match.name}" if match else " — بدون تطبیق")


register(GenericWebhookProvider())
