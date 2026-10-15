"""The deployment's own language model, over HTTP (2.40.55, feature `ai_assistant`).

Owner decision 2026-10-14 (Q19): «باید داخلی باشد». The model runs on the
customer's own server, in the `ai` service of `compose.ai.yml` (llama.cpp's
server, an open-weights model the operator puts in place offline), on the
internal `backend` network with no way out. This module only speaks its
OpenAI-compatible chat endpoint; nothing here can reach anything else, and no
deployment value names a public provider.
"""

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

from django.conf import settings

logger = logging.getLogger("dolphin.assistant")


class AssistantUnavailable(RuntimeError):
    """The model could not be asked or did not answer usefully."""


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    seconds: float


def base_url():
    """`DOLPHIN_AI_URL`, or `""` when this deployment runs no model."""
    url = str(getattr(settings, "DOLPHIN_AI_URL", "") or "").strip().rstrip("/")
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return ""
    return url


def model_label():
    return str(getattr(settings, "DOLPHIN_AI_MODEL_LABEL", "") or "").strip()


def _post(path, payload, *, timeout):
    request = urllib.request.Request(
        base_url() + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    # A plain opener with no proxy: the model is on the internal network.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read(2_000_000).decode("utf-8"))


def complete(messages, *, max_tokens=700, temperature=0.3):
    """One chat completion. Raises `AssistantUnavailable` on any failure."""
    if not base_url():
        raise AssistantUnavailable("no model is configured")
    timeout = float(getattr(settings, "DOLPHIN_AI_TIMEOUT_SECONDS", 90))
    started = time.monotonic()
    try:
        data = _post(
            "/v1/chat/completions",
            {"model": model_label() or "local", "messages": messages, "max_tokens": max_tokens,
             "temperature": temperature, "stream": False},
            timeout=timeout,
        )
        text = str(data["choices"][0]["message"]["content"] or "").strip()
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
        logger.warning("assistant model request failed: %s", type(error).__name__)
        raise AssistantUnavailable(type(error).__name__) from error
    if not text:
        raise AssistantUnavailable("empty answer")
    return Completion(text=text, model=str(data.get("model") or model_label() or ""), seconds=round(time.monotonic() - started, 2))


def health():
    """`{"configured", "reachable", "model"}` for the settings page."""
    if not base_url():
        return {"configured": False, "reachable": False, "model": ""}
    request = urllib.request.Request(base_url() + "/health", method="GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            reachable = 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        reachable = False
    return {"configured": True, "reachable": reachable, "model": model_label()}
