"""Outbound SMS: a provider-agnostic core, plus one generic HTTP provider.

This deliberately does **not** integrate any specific Iranian SMS gateway
(Kavenegar, Melipayamak, Ghasedak, ...). Each exposes a different HTTP
contract, and hardcoding one into shared source would mean either every other
deployment carries dead code for a vendor it never signed with, or — worse —
this codebase silently assuming a specific vendor's request/response shape
without a reviewed integration for it. `common/pdf.py` made the same call
about a PDF library for a parallel reason and the comment there explains the
trade-off in full; the short version is: **no new Python dependency**, so
`requirements.txt`'s hash-pinned lock stays untouched, and the one supported
provider is a generic HTTP request built entirely from this deployment's own
settings (`DOLPHIN_SMS_*`, read in `config/settings.py`) — never a name or a
request shape hardcoded into shared source.

A deployment that has not configured a provider gets `configured_provider()
== ""`, and the feature is off — `provider_is_available()` is what a caller
checks before attempting anything, mirroring `common.pdf.renderer_is_available`
so a control that cannot act is never offered.

**Template substitution is on parsed values, not text.** `SMS_API_BODY_
TEMPLATE` is parsed as JSON *first*, and the placeholder tokens
(`__SMS_TO__`, `__SMS_BODY__`, `__SMS_SENDER__`) are only ever replaced inside
already-decoded Python strings, which are then re-encoded by `json.dumps`.
That ordering is not incidental: naive text substitution into a JSON template
(`template.format(...)`) would corrupt the request the moment a customer's
name or an SMS body contained a `"` or a newline, and open exactly the kind of
injection this order makes structurally impossible.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings


class SmsProviderUnavailable(RuntimeError):
    """No provider is configured for this deployment. Nothing was attempted."""


@dataclass(frozen=True)
class SmsSendResult:
    provider_code: str
    success: bool
    #: Short, safe-to-store diagnostic text — never headers, never the API
    #: key/token from `DOLPHIN_SMS_API_HEADERS`, only an HTTP status and a
    #: truncated response body (or a connection-error class name).
    status_detail: str


TO_PLACEHOLDER = "__SMS_TO__"
BODY_PLACEHOLDER = "__SMS_BODY__"
SENDER_PLACEHOLDER = "__SMS_SENDER__"

_MAX_RESPONSE_DETAIL = 200


def _setting(name, default=""):
    return getattr(settings, name, default)


def configured_provider():
    """The provider this deployment asked for, or "" when the feature is off."""
    return str(_setting("SMS_PROVIDER", "") or "").strip().lower()


def provider_is_available():
    """True when sending really can be attempted right now.

    Checked before offering a "send SMS" control, or before a service
    function does anything else, so the control never appears on a deployment
    where pressing it could only fail on missing configuration.
    """
    if configured_provider() != "http":
        return False
    return bool(str(_setting("SMS_API_URL", "")).strip()) and bool(
        str(_setting("SMS_API_BODY_TEMPLATE", "")).strip()
    )


def _substitute(node, *, to, body, sender):
    if isinstance(node, str):
        return (
            node.replace(TO_PLACEHOLDER, to)
            .replace(BODY_PLACEHOLDER, body)
            .replace(SENDER_PLACEHOLDER, sender)
        )
    if isinstance(node, dict):
        return {key: _substitute(value, to=to, body=body, sender=sender) for key, value in node.items()}
    if isinstance(node, list):
        return [_substitute(item, to=to, body=body, sender=sender) for item in node]
    return node


def send_via_configured_provider(*, to, body):
    """Attempt one send through this deployment's configured provider.

    Raises `SmsProviderUnavailable` only when nothing was attempted at all
    (no provider configured — the caller should have checked
    `provider_is_available()` first). Once an attempt is made, every outcome
    — success, a misconfigured template, a network error, a non-2xx response —
    comes back as an `SmsSendResult`, never an exception, so a caller can
    always record exactly one outcome row for exactly one attempt.
    """
    provider = configured_provider()
    if provider != "http":
        raise SmsProviderUnavailable("No SMS provider is configured for this deployment.")
    return _send_via_http(to=to, body=body)


def _send_via_http(*, to, body):
    url = str(_setting("SMS_API_URL", "")).strip()
    if not url:
        return SmsSendResult(provider_code="http", success=False, status_detail="misconfigured: DOLPHIN_SMS_API_URL is empty")

    template_text = str(_setting("SMS_API_BODY_TEMPLATE", "")).strip()
    if not template_text:
        return SmsSendResult(
            provider_code="http", success=False,
            status_detail="misconfigured: DOLPHIN_SMS_API_BODY_TEMPLATE is empty",
        )
    try:
        template = json.loads(template_text)
    except ValueError:
        return SmsSendResult(
            provider_code="http", success=False,
            status_detail="misconfigured: DOLPHIN_SMS_API_BODY_TEMPLATE is not valid JSON",
        )
    sender = str(_setting("SMS_SENDER_ID", "")).strip()
    payload = _substitute(template, to=to, body=body, sender=sender)

    headers = {"Content-Type": "application/json"}
    raw_headers = str(_setting("SMS_API_HEADERS", "")).strip()
    if raw_headers:
        try:
            extra = json.loads(raw_headers)
            if not isinstance(extra, dict):
                raise ValueError("DOLPHIN_SMS_API_HEADERS must be a JSON object")
            headers.update({str(key): str(value) for key, value in extra.items()})
        except ValueError:
            return SmsSendResult(
                provider_code="http", success=False,
                status_detail="misconfigured: DOLPHIN_SMS_API_HEADERS is not a valid JSON object",
            )

    try:
        timeout = int(_setting("SMS_API_TIMEOUT_SECONDS", 10) or 10)
    except (TypeError, ValueError):
        timeout = 10

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.status
            response_text = response.read(_MAX_RESPONSE_DETAIL).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        status = error.code
        response_text = error.read(_MAX_RESPONSE_DETAIL).decode("utf-8", errors="replace") if error.fp else ""
    except (urllib.error.URLError, OSError, ValueError) as error:
        return SmsSendResult(
            provider_code="http", success=False,
            status_detail=f"connection error: {error.__class__.__name__}",
        )

    success = 200 <= status <= 299
    detail = f"HTTP {status}: {response_text[:_MAX_RESPONSE_DETAIL]}".strip()
    return SmsSendResult(provider_code="http", success=success, status_detail=detail)
