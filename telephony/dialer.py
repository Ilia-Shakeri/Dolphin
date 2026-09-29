"""Click-to-call over HTTP for a webhook-connected PBX (2.30.0).

A PBX with no AMI can still place a call when it has an HTTP "make call" API.
Two modes:

* `yeastar` - Yeastar P-Series OpenAPI: a token from `get_token`, then
  `call/dial` with the user's extension as caller (the extension's phone
  rings first, the number is dialled when it is answered).
* `http` - any other PBX: the connection holds a URL and a JSON body
  template; `{extension}` and `{number}` are replaced. A 2xx answer is success.

The PBX is usually on a private address, so the target is not restricted like
an outbound webhook; the address is set by the platform admin, never by the
person who clicks. Secrets stay in the connection and are never logged.
"""

import base64
import json
import ssl
import urllib.error
import urllib.request

TIMEOUT = 8


class DialError(Exception):
    pass


def _context(config):
    if config.get("api_verify_tls", True):
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def _send(request, config):
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=_context(config)) as response:
            raw = response.read(65536)
    except urllib.error.HTTPError as error:
        raise DialError(f"مرکز تلفن خطای {error.code} برگرداند.") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise DialError("به مرکز تلفن وصل نشد.") from error
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _yeastar(config, secrets, extension, number):
    base = str(config.get("api_base_url") or "").rstrip("/")
    if not base:
        raise DialError("نشانی API مرکز تلفن تنظیم نشده است.")
    token = secrets.get("api_token", "")
    if not token:
        body = json.dumps({"username": config.get("api_username", ""), "password": secrets.get("api_password", "")}).encode()
        answer = _send(
            urllib.request.Request(f"{base}/openapi/v1.0/get_token", data=body, method="POST",
                                   headers={"Content-Type": "application/json"}),
            config,
        )
        token = str(answer.get("access_token") or "")
        if not token:
            raise DialError("مرکز تلفن توکن نداد؛ نام کاربری و گذرواژهٔ API را بررسی کنید.")
    body = json.dumps({"caller": extension, "callee": number, "auto_answer": "no"}).encode()
    answer = _send(
        urllib.request.Request(f"{base}/openapi/v1.0/call/dial?access_token={token}", data=body, method="POST",
                               headers={"Content-Type": "application/json"}),
        config,
    )
    if answer.get("errcode") not in (0, "0", None):
        raise DialError("مرکز تلفن تماس را نپذیرفت.")
    return str(answer.get("call_id") or "")


def _fill(template, values):
    if isinstance(template, str):
        for key, value in values.items():
            template = template.replace("{" + key + "}", value)
        return template
    if isinstance(template, dict):
        return {key: _fill(value, values) for key, value in template.items()}
    if isinstance(template, list):
        return [_fill(value, values) for value in template]
    return template


def _dig(data, dotted):
    for part in dotted.split("."):
        if not isinstance(data, dict):
            return ""
        data = data.get(part, "")
    return "" if isinstance(data, (dict, list)) else str(data)


def _http(config, secrets, extension, number):
    url = str(config.get("dial_url") or "")
    if not url.lower().startswith(("http://", "https://")):
        raise DialError("نشانی درخواست تماس تنظیم نشده است.")
    values = {"extension": extension, "number": number}
    method = str(config.get("dial_method") or "POST").upper()
    headers = {"Content-Type": "application/json"}
    if secrets.get("api_token"):
        headers["Authorization"] = f"Bearer {secrets['api_token']}"
    elif config.get("api_username") and secrets.get("api_password"):
        pair = f"{config['api_username']}:{secrets['api_password']}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
    data = None
    if method == "GET":
        url = _fill(url, values)
    else:
        try:
            template = json.loads(config.get("dial_body") or "{}")
        except json.JSONDecodeError as error:
            raise DialError("قالب بدنهٔ درخواست تماس JSON معتبر نیست.") from error
        data = json.dumps(_fill(template, values)).encode()
        url = _fill(url, values)
    answer = _send(urllib.request.Request(url, data=data, method=method, headers=headers), config)
    key = str(config.get("dial_call_id_key") or "")
    return _dig(answer, key) if key else ""


def place_call(integration, secrets, extension, number):
    """Ask the PBX to call; the PBX's call id (may be empty) or `DialError`."""
    config = integration.config or {}
    mode = config.get("dial_mode") or "none"
    if mode == "yeastar":
        return _yeastar(config, secrets, extension, number)
    if mode == "http":
        return _http(config, secrets, extension, number)
    raise DialError("برقراری تماس از دلفین برای این مرکز تلفن تنظیم نشده است.")
