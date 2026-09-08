"""Outbound SMS: a provider-agnostic core, plus two generic HTTP providers.

This deliberately does **not** integrate any specific Iranian SMS gateway
(Kavenegar, Melipayamak, Ghasedak, TIARA's own payamsms.com, ...). Each
exposes a different HTTP contract, and hardcoding one into shared source
would mean either every other deployment carries dead code for a vendor it
never signed with, or — worse — this codebase silently assuming a specific
vendor's request/response shape without a reviewed integration for it.
`common/pdf.py` made the same call about a PDF library for a parallel reason
and the comment there explains the trade-off in full; the short version is:
**no new Python dependency**, so `requirements.txt`'s hash-pinned lock stays
untouched, and every supported provider is a generic HTTP request built
entirely from this deployment's own configuration — never a name or a
request shape hardcoded into shared source.

**Two generic shapes, because one real gateway needed a second one.**
`AuthMode.API_KEY` (the original, and still the common case — Kavenegar,
Melipayamak, Ghasedak and most others: a static header or query value that
never expires) sends one request. `AuthMode.OAUTH2_PASSWORD` — added when
TIARA supplied payamsms.com's real API docs (docs/ops/TIARA_SMS_SETUP.md) —
first exchanges a username/password for a short-lived bearer token (RFC 6749
"Resource Owner Password Credentials" grant), then sends the same generic
request with `Authorization: Bearer <token>` added. Neither shape names
TIARA, payamsms.com, or any other vendor; `docs/ops/TIARA_SMS_SETUP.md` is
where that association lives, not this file.

**Two configuration sources, checked in order.** `resolve_config()` reads
`communications.models.SmsProviderSettings` (a Platform-Admin-editable
singleton — `/settings/sms-provider/` in the panel) first; only when that row
is absent or `is_enabled=False` does it fall back to the original
`DOLPHIN_SMS_*` environment variables. A deployment that configured
everything before this settings page existed keeps working with no change;
a deployment that has never touched `.env` can be fully configured from the
panel by a Platform Admin. Never both at once — the row, when enabled, is the
whole configuration, not a set of overrides layered onto the environment.

A deployment with neither source configured gets `resolve_config() is None`,
and the feature is off — `provider_is_available()` is what a caller checks
before attempting anything, mirroring `common.pdf.renderer_is_available` so a
control that cannot act is never offered.

**Template substitution is on parsed values, not text.** A body template is
parsed as JSON *first*, and the placeholder tokens (`__SMS_TO__`,
`__SMS_BODY__`, `__SMS_SENDER__`, `__SMS_ID__`) are only ever replaced inside
already-decoded Python strings, which are then re-encoded by `json.dumps`.
That ordering is not incidental: naive text substitution into a JSON template
(`template.format(...)`) would corrupt the request the moment a customer's
name or an SMS body contained a `"` or a newline, and open exactly the kind
of injection this order makes structurally impossible.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass

from django.conf import settings


class SmsProviderUnavailable(RuntimeError):
    """No provider is configured for this deployment. Nothing was attempted."""


@dataclass(frozen=True)
class SmsSendResult:
    provider_code: str
    success: bool
    #: Short, safe-to-store diagnostic text — never a header, a password, an
    #: API key, or a bearer token, only an HTTP status and a truncated
    #: response body (or a connection-error class name).
    status_detail: str


@dataclass(frozen=True)
class ResolvedSmsConfig:
    """Everything one send attempt needs, regardless of which of the two
    sources (database row or environment variables) it came from.
    """

    source: str  # "database" | "environment" — diagnostic only, never sent anywhere
    auth_mode: str  # SmsProviderSettings.AuthMode value
    recipient_number_style: str  # SmsProviderSettings.NumberStyle value
    send_url: str
    body_template: str
    headers: str
    sender_id: str
    timeout_seconds: int
    token_url: str = ""
    token_username: str = ""
    token_password: str = ""
    token_extra_params: str = ""
    #: The admin's own free-text label (`SmsProviderSettings.label`) — blank
    #: for the environment-variable source, which has no such field. Purely
    #: for a human reading a status line; never sent in any request.
    label: str = ""
    #: Only meaningful to `test_connectivity()` — blank for the
    #: environment-variable source, which offers no "تست اتصال" button.
    test_url: str = ""


TO_PLACEHOLDER = "__SMS_TO__"
BODY_PLACEHOLDER = "__SMS_BODY__"
SENDER_PLACEHOLDER = "__SMS_SENDER__"
#: A fresh `uuid4` generated for each send attempt. Several gateways
#: (TIARA's own among them — `customerId` on `SmsItem`) require a caller-
#: supplied tracking identifier on every line but never validate it against
#: anything this codebase stores, so a random value satisfies the contract
#: without inventing a second numbering scheme alongside `OutboundSMS.pk`,
#: which does not exist yet at the moment the request is built (the row is
#: written only after the provider has answered — see
#: `communications.services.send_outbound_sms`).
ID_PLACEHOLDER = "__SMS_ID__"

_MAX_RESPONSE_DETAIL = 200


def _env_setting(name, default=""):
    return getattr(settings, name, default)


def config_from_row(row):
    """A `ResolvedSmsConfig` built from one `SmsProviderSettings` row,
    regardless of `row.is_enabled` — used by the settings page's own "تست
    اتصال" button, which must be able to check a row before it is switched
    on. `_config_from_database()` below is the `is_enabled`-checking path
    every real send goes through.
    """
    return ResolvedSmsConfig(
        source="database",
        auth_mode=row.auth_mode,
        recipient_number_style=row.recipient_number_style,
        send_url=row.send_url,
        body_template=row.body_template,
        headers=row.headers,
        sender_id=row.sender_id,
        timeout_seconds=row.timeout_seconds,
        token_url=row.token_url,
        token_username=row.token_username,
        token_password=row.token_password,
        token_extra_params=row.token_extra_params,
        label=row.label,
        test_url=row.test_url,
    )


def _config_from_database():
    """The enabled `SmsProviderSettings` row's config, or `None`.

    A bare `.filter().first()`, not `get_or_create`: this runs on the hot
    path of every availability check and every send, and creating the empty
    singleton row is the settings page's job (`get_sms_provider_settings`),
    not this function's.
    """
    from communications.models import SmsProviderSettings

    row = SmsProviderSettings.objects.filter(
        singleton=SmsProviderSettings.SINGLETON, is_enabled=True
    ).first()
    return config_from_row(row) if row is not None else None


def _config_from_environment():
    """The legacy `DOLPHIN_SMS_*` environment variables, or `None`.

    Unchanged contract from before `SmsProviderSettings` existed: only
    `SMS_PROVIDER=http` is recognised here, and both `SMS_API_URL` and
    `SMS_API_BODY_TEMPLATE` must be non-blank.
    """
    if str(_env_setting("SMS_PROVIDER", "") or "").strip().lower() != "http":
        return None
    send_url = str(_env_setting("SMS_API_URL", "")).strip()
    body_template = str(_env_setting("SMS_API_BODY_TEMPLATE", "")).strip()
    if not send_url or not body_template:
        return None
    try:
        timeout = int(_env_setting("SMS_API_TIMEOUT_SECONDS", 10) or 10)
    except (TypeError, ValueError):
        timeout = 10
    return ResolvedSmsConfig(
        source="environment",
        auth_mode="api_key",
        recipient_number_style="e164",
        send_url=send_url,
        body_template=body_template,
        headers=str(_env_setting("SMS_API_HEADERS", "")).strip(),
        sender_id=str(_env_setting("SMS_SENDER_ID", "")).strip(),
        timeout_seconds=timeout,
    )


def resolve_config():
    """The configuration this deployment should send through right now, or
    `None` when nothing is configured at all. See this module's own
    docstring for the precedence between the two sources.
    """
    return _config_from_database() or _config_from_environment()


def configured_provider():
    """The auth mode this deployment resolves to, or "" when unconfigured.

    Kept for backward compatibility with anything that still asks "is it
    the http provider" — every caller inside this codebase now goes through
    `provider_is_available()`/`send_via_configured_provider()` instead, which
    do not need to know the auth mode at all.
    """
    config = resolve_config()
    return config.auth_mode if config else ""


def provider_is_available():
    """True when sending really can be attempted right now.

    Checked before offering a "send SMS" control, or before a service
    function does anything else, so the control never appears on a
    deployment where pressing it could only fail on missing configuration.
    """
    return resolve_config() is not None


def _substitute(node, *, to, body, sender, msg_id):
    if isinstance(node, str):
        return (
            node.replace(TO_PLACEHOLDER, to)
            .replace(BODY_PLACEHOLDER, body)
            .replace(SENDER_PLACEHOLDER, sender)
            .replace(ID_PLACEHOLDER, msg_id)
        )
    if isinstance(node, dict):
        return {key: _substitute(value, to=to, body=body, sender=sender, msg_id=msg_id) for key, value in node.items()}
    if isinstance(node, list):
        return [_substitute(item, to=to, body=body, sender=sender, msg_id=msg_id) for item in node]
    return node


def _format_recipient(to, style):
    """`to` always arrives as this codebase's own canonical E.164 form
    (`+98912xxxxxxx` — `common.phones.normalize_customer_phone`); this is the
    one place that gets rewritten into whatever a gateway actually expects.
    """
    if style == "digits_only":
        return to.lstrip("+")
    if style == "local_zero" and to.startswith("+98"):
        return "0" + to[3:]
    return to


def send_via_configured_provider(*, to, body):
    """Attempt one send through this deployment's configured provider.

    Raises `SmsProviderUnavailable` only when nothing was attempted at all
    (no provider configured — the caller should have checked
    `provider_is_available()` first). Once an attempt is made, every outcome
    — success, a misconfigured template, a network error, a non-2xx response —
    comes back as an `SmsSendResult`, never an exception, so a caller can
    always record exactly one outcome row for exactly one attempt.
    """
    config = resolve_config()
    if config is None:
        raise SmsProviderUnavailable("No SMS provider is configured for this deployment.")
    recipient = _format_recipient(to, config.recipient_number_style)
    msg_id = str(uuid.uuid4())
    if config.auth_mode == "oauth2_password":
        return _send_via_oauth2_http(config, to=recipient, body=body, msg_id=msg_id)
    return _send_via_http(config, to=recipient, body=body, msg_id=msg_id, provider_code="http")


def _parse_json_object(raw_headers, *, field_label):
    """Returns `(headers_dict, error_detail)`; exactly one is `None`."""
    if not raw_headers.strip():
        return {}, None
    try:
        extra = json.loads(raw_headers)
        if not isinstance(extra, dict):
            raise ValueError(f"{field_label} must be a JSON object")
    except ValueError:
        return None, f"misconfigured: {field_label} is not a valid JSON object"
    return {str(key): str(value) for key, value in extra.items()}, None


def _build_send_request(config, *, to, body, sender, msg_id, extra_headers):
    """Shared by both auth modes: parse the template, substitute, and hand
    back a ready `urllib.request.Request` — or `None` plus a diagnostic
    `SmsSendResult` when the template/headers are themselves invalid.
    """
    if not config.send_url:
        return None, SmsSendResult(provider_code="http", success=False, status_detail="misconfigured: send URL is empty")
    if not config.body_template.strip():
        return None, SmsSendResult(provider_code="http", success=False, status_detail="misconfigured: body template is empty")
    try:
        template = json.loads(config.body_template)
    except ValueError:
        return None, SmsSendResult(provider_code="http", success=False, status_detail="misconfigured: body template is not valid JSON")

    static_headers, error = _parse_json_object(config.headers, field_label="headers")
    if error is not None:
        return None, SmsSendResult(provider_code="http", success=False, status_detail=error)

    payload = _substitute(template, to=to, body=body, sender=sender, msg_id=msg_id)
    headers = {"Content-Type": "application/json", **static_headers, **extra_headers}
    request = urllib.request.Request(
        config.send_url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST",
    )
    return request, None


def _execute(request, *, timeout):
    """Runs one HTTP request and returns `(status, response_text, error_detail)`.

    Exactly one of `(status, response_text)` and `error_detail` is
    meaningful: a connection failure never raises past this point.
    """
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(_MAX_RESPONSE_DETAIL).decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as error:
        text = error.read(_MAX_RESPONSE_DETAIL).decode("utf-8", errors="replace") if error.fp else ""
        return error.code, text, None
    except (urllib.error.URLError, OSError, ValueError) as error:
        return None, "", f"connection error: {error.__class__.__name__}"


def _send_via_http(config, *, to, body, msg_id, provider_code):
    sender = config.sender_id
    request, failure = _build_send_request(config, to=to, body=body, sender=sender, msg_id=msg_id, extra_headers={})
    if failure is not None:
        return SmsSendResult(provider_code=provider_code, success=failure.success, status_detail=failure.status_detail)

    status, response_text, error_detail = _execute(request, timeout=config.timeout_seconds)
    if error_detail is not None:
        return SmsSendResult(provider_code=provider_code, success=False, status_detail=error_detail)

    success = 200 <= status <= 299
    detail = f"HTTP {status}: {response_text[:_MAX_RESPONSE_DETAIL]}".strip()
    return SmsSendResult(provider_code=provider_code, success=success, status_detail=detail)


def _acquire_oauth2_token(config):
    """Returns `(access_token, error_detail)`; exactly one is not `None`.

    `access_token` is the standard field name RFC 6749 §5.1 defines for a
    successful token response — reading that one key is not a vendor
    assumption, it is reading the grant type this auth mode already commits
    to by name (`oauth2_password`).

    TIARA's own gateway is delivered credentials **both** ways at once — a
    `Basic` auth header *and* the same username/password repeated as query
    parameters (see the real Postman collection behind
    docs/ops/TIARA_SMS_SETUP.md) — an unusual, redundant shape, but sending
    both costs nothing against a gateway that only reads one of them.
    """
    if not config.token_url.strip():
        return None, "misconfigured: token URL is empty"

    query = {}
    if config.token_username:
        query["username"] = config.token_username
    if config.token_password:
        query["password"] = config.token_password
    extra_params, error = _parse_json_object(config.token_extra_params, field_label="token extra params")
    if error is not None:
        return None, error
    query.update(extra_params)

    url = config.token_url
    if query:
        joiner = "&" if "?" in url else "?"
        url = f"{url}{joiner}{urllib.parse.urlencode(query)}"

    headers = {}
    if config.token_username or config.token_password:
        basic = base64.b64encode(f"{config.token_username}:{config.token_password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {basic}"

    request = urllib.request.Request(url, headers=headers, method="POST")
    status, response_text, error_detail = _execute(request, timeout=config.timeout_seconds)
    if error_detail is not None:
        return None, error_detail
    if not (200 <= status <= 299):
        return None, f"token request failed: HTTP {status}: {response_text[:_MAX_RESPONSE_DETAIL]}".strip()
    try:
        parsed = json.loads(response_text) if response_text else {}
    except ValueError:
        return None, "token response was not valid JSON"
    token = parsed.get("access_token") if isinstance(parsed, dict) else None
    if not token or not isinstance(token, str):
        return None, "token response carried no access_token"
    return token, None


def _send_via_oauth2_http(config, *, to, body, msg_id):
    """No token caching yet — every send performs its own login-then-send
    round trip. Deliberate, not an oversight: none of the gateway
    documentation collected so far (docs/ops/TIARA_SMS_SETUP.md) states a
    token lifetime, and caching a token for an unknown duration risks
    sending with one already rejected by the gateway, which would surface as
    a silent, hard-to-diagnose failure. Add caching once a real TTL is
    confirmed with the provider — see that document's own open-questions
    section.
    """
    token, error_detail = _acquire_oauth2_token(config)
    if token is None:
        return SmsSendResult(provider_code="oauth2", success=False, status_detail=error_detail)

    return _send_via_http_with_bearer(config, to=to, body=body, msg_id=msg_id, token=token)


def _send_via_http_with_bearer(config, *, to, body, msg_id, token):
    sender = config.sender_id
    request, failure = _build_send_request(
        config, to=to, body=body, sender=sender, msg_id=msg_id,
        extra_headers={"Authorization": f"Bearer {token}"},
    )
    if failure is not None:
        return SmsSendResult(provider_code="oauth2", success=False, status_detail=failure.status_detail)

    status, response_text, error_detail = _execute(request, timeout=config.timeout_seconds)
    if error_detail is not None:
        return SmsSendResult(provider_code="oauth2", success=False, status_detail=error_detail)

    success = 200 <= status <= 299
    detail = f"HTTP {status}: {response_text[:_MAX_RESPONSE_DETAIL]}".strip()
    return SmsSendResult(provider_code="oauth2", success=success, status_detail=detail)


def test_connectivity(config):
    """Calls `config`'s optional `test_url` (a GET) with whichever auth this
    config resolves to, for the settings page's own "تست اتصال" button.

    Takes an explicit `config` (built by `config_from_row`) rather than
    `resolve_config()`: a row being tested may not be `is_enabled` yet, and
    `resolve_config()` would then see straight past it to the environment
    fallback or to nothing at all.
    """
    test_url = config.test_url or ""
    if not test_url.strip():
        return SmsSendResult(provider_code="test", success=False, status_detail="نشانی آزمایشی تنظیم نشده است.")

    headers = {}
    if config.auth_mode == "oauth2_password":
        token, error_detail = _acquire_oauth2_token(config)
        if token is None:
            return SmsSendResult(provider_code="test", success=False, status_detail=error_detail)
        headers["Authorization"] = f"Bearer {token}"
    else:
        static_headers, error = _parse_json_object(config.headers, field_label="headers")
        if error is not None:
            return SmsSendResult(provider_code="test", success=False, status_detail=error)
        headers.update(static_headers)

    request = urllib.request.Request(test_url, headers=headers, method="GET")
    status, response_text, error_detail = _execute(request, timeout=config.timeout_seconds)
    if error_detail is not None:
        return SmsSendResult(provider_code="test", success=False, status_detail=error_detail)
    success = 200 <= status <= 299
    detail = f"HTTP {status}: {response_text[:_MAX_RESPONSE_DETAIL]}".strip()
    return SmsSendResult(provider_code="test", success=success, status_detail=detail)
