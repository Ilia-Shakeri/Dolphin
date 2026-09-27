"""The kinds of outside system Dolphin can connect to (2.21.0).

A provider says what it is, what it can do (`capabilities`), which settings it
needs (`fields` — the admin page builds its form from them), how to check a
connection, and — if it accepts inbound webhooks — how to verify and handle
one. Adding a system is one provider module and one `register(...)` call; the
page, the API and the storage need no change.

A provider never stores anything itself: its settings live on an
`Integration` row, its secrets encrypted there (`integrations.crypto`).
"""

from dataclasses import dataclass

CAPABILITY_LABELS = {
    "telephony": "تلفن",
    "messaging": "پیام‌رسان",
    "sms": "پیامک",
    "email": "ایمیل",
    "payment": "پرداخت",
    "accounting": "حسابداری",
    "webhook": "وب‌هوک",
}


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    #: `text`, `url`, `int`, `bool`, `select`, or `password` (always secret).
    kind: str = "text"
    required: bool = False
    secret: bool = False
    help: str = ""
    default: object = None
    choices: tuple = ()
    placeholder: str = ""
    #: A technical value — a host, a path, a dial pattern — typed and read
    #: left to right even on the Persian page.
    ltr: bool = False

    @property
    def is_secret(self):
        return self.secret or self.kind == "password"

    def describe(self):
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "required": self.required,
            "secret": self.is_secret,
            "help": self.help,
            "default": self.default,
            "choices": [{"value": value, "label": label} for value, label in self.choices],
            "placeholder": self.placeholder,
            "ltr": self.ltr,
        }


@dataclass
class ConnectionResult:
    ok: bool
    message: str


class Provider:
    key = ""
    name = ""
    description = ""
    capabilities = ()
    fields = ()
    #: The deployment feature this provider needs beyond `integrations`.
    required_feature = None
    #: Whether an integration of this kind accepts inbound webhooks.
    accepts_webhooks = False
    #: At most one integration of this kind per deployment.
    singleton = False

    def describe(self):
        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "capabilities": [
                {"key": capability, "label": CAPABILITY_LABELS.get(capability, capability)}
                for capability in self.capabilities
            ],
            "fields": [item.describe() for item in self.fields],
            "accepts_webhooks": self.accepts_webhooks,
            "singleton": self.singleton,
        }

    def validate(self, config, secrets):
        """`{field: message}` for anything wrong beyond the schema itself."""
        return {}

    def test_connection(self, integration, config, secrets):
        return ConnectionResult(False, "این نوع اتصال آزمایش خودکار ندارد.")

    def verify_inbound(self, integration, secrets, request, body):
        return False

    def handle_inbound(self, integration, config, payload):
        """Turn one verified payload into domain events; a short result text."""
        return ""


_PROVIDERS = {}


def register(provider):
    if not provider.key:
        raise ValueError("A provider needs a key.")
    _PROVIDERS[provider.key] = provider
    return provider


def provider_for(key):
    return _PROVIDERS.get(key)


def providers():
    return [provider for _, provider in sorted(_PROVIDERS.items())]


def clean_config(provider, raw_config, raw_secrets, *, existing_secrets=None):
    """Validate and coerce against the provider's fields.

    Returns `(config, secrets, errors)`. A secret left blank keeps the value
    already stored — secrets are write-only, so "empty" in a form means "not
    changing it", never "clear it".
    """
    existing_secrets = existing_secrets or {}
    raw_config = raw_config if isinstance(raw_config, dict) else {}
    raw_secrets = raw_secrets if isinstance(raw_secrets, dict) else {}
    known = {item.key for item in provider.fields}
    errors = {name: "این فیلد برای این نوع اتصال تعریف نشده است." for name in (set(raw_config) | set(raw_secrets)) - known}
    config, secrets = {}, dict(existing_secrets)
    for item in provider.fields:
        if item.is_secret:
            value = raw_secrets.get(item.key)
            if value not in (None, ""):
                if not isinstance(value, str) or len(value) > 500:
                    errors[item.key] = "مقدار نامعتبر است."
                    continue
                secrets[item.key] = value
            if item.required and not secrets.get(item.key):
                errors[item.key] = "این مقدار لازم است."
            continue
        value = raw_config.get(item.key, item.default)
        if value in (None, ""):
            if item.required:
                errors[item.key] = "این مقدار لازم است."
            continue
        try:
            config[item.key] = _coerce(item, value)
        except ValueError as error:
            errors[item.key] = str(error)
    if not errors:
        errors.update(provider.validate(config, secrets))
    return config, secrets, errors


def _coerce(item, value):
    if item.kind == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError("بله یا خیر انتخاب کنید.")
    if item.kind == "int":
        if isinstance(value, bool):
            raise ValueError("عدد صحیح وارد کنید.")
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError("عدد صحیح وارد کنید.") from None
        if not 0 <= number <= 10_000_000:
            raise ValueError("عدد خارج از محدوده است.")
        return number
    text = str(value).strip()
    if len(text) > 500:
        raise ValueError("حداکثر ۵۰۰ نویسه.")
    if item.kind == "select":
        if text not in {choice for choice, _ in item.choices}:
            raise ValueError("از فهرست انتخاب کنید.")
    if item.kind == "url" and not text.lower().startswith(("https://", "http://")):
        raise ValueError("نشانی باید با https:// شروع شود.")
    return text
