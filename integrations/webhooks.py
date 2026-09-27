"""Outbound webhooks — signed, retried, logged (2.21.0).

Each delivery is a `POST` of

    {"id": <event id>, "type": "call.ended", "occurred_at": "...", "data": {...}}

with `X-Dolphin-Event`, `X-Dolphin-Delivery` and
`X-Dolphin-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<body>">`
under the subscription's own secret — the receiver recomputes it and rejects
anything older than a few minutes, which defeats replay.

A 2xx answer delivers it. Anything else, or no answer within `TIMEOUT`, is
retried after 1 minute, 5, 30, 2 hours and 12 hours, then marked failed.

Targets must be `https://` on a public address (`validate_target`): an
administrator cannot point Dolphin at its own database host or the cloud
metadata service by mistake or on purpose.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
import urllib.error
import urllib.request
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from integrations.crypto import decrypt_json

logger = logging.getLogger("dolphin.integrations.webhooks")

TIMEOUT = 10
RETRY_DELAYS = (60, 300, 1800, 7200, 43200)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
RESPONSE_EXCERPT = 200


class TargetRefused(ValueError):
    pass


def validate_target(url):
    """Refuse anything but `https://` to a public address."""
    parts = urlsplit(url or "")
    if parts.scheme != "https" or not parts.hostname:
        raise TargetRefused("نشانی باید با https:// شروع شود.")
    if parts.username or parts.password:
        raise TargetRefused("نشانی نباید نام کاربری یا گذرواژه داشته باشد.")
    if getattr(settings, "DOLPHIN_WEBHOOKS_ALLOW_PRIVATE_TARGETS", False):
        return
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
    except socket.gaierror as error:
        raise TargetRefused("نام میزبان این نشانی پیدا نشد.") from error
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise TargetRefused("نشانی به یک شبکهٔ داخلی یا خصوصی اشاره می‌کند.")


def sign(secret, timestamp, body):
    message = f"{timestamp}.".encode("ascii") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def body_for(event):
    return json.dumps(
        {
            "id": event.pk,
            "type": event.event_type,
            "occurred_at": event.created_at.isoformat(),
            "data": event.payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")


def queue_deliveries(event, *, now):
    """One pending delivery per active subscription that wants this event."""
    from integrations.models import WebhookDelivery, WebhookSubscription

    for subscription in WebhookSubscription.objects.filter(active=True):
        if subscription.event_types and event.event_type not in subscription.event_types:
            continue
        WebhookDelivery.objects.get_or_create(
            subscription=subscription, event=event, defaults={"next_attempt_at": now}
        )


def _post(url, body, headers):
    """One HTTP POST; `(status, excerpt)`. Isolated so tests replace it."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 — https only, validated
            return response.status, response.read(RESPONSE_EXCERPT).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read(RESPONSE_EXCERPT).decode("utf-8", "replace")


def attempt(delivery, *, now=None):
    """Send one delivery once and record the outcome."""
    from integrations.models import IntegrationLog, WebhookDelivery

    now = now or timezone.now()
    subscription, event = delivery.subscription, delivery.event
    delivery.attempts += 1
    body = body_for(event)
    try:
        validate_target(subscription.url)
        secret = decrypt_json(subscription.secret_token).get("secret", "")
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "Dolphin-Webhooks/1",
            "X-Dolphin-Event": event.event_type,
            "X-Dolphin-Delivery": str(delivery.pk),
            "X-Dolphin-Signature": f"t={timestamp},v1={sign(secret, timestamp, body)}",
        }
        status, excerpt = _post(subscription.url, body, headers)
        delivery.response_status = status
        ok = 200 <= status < 300
        error = "" if ok else f"پاسخ {status}: {excerpt}"
    except Exception as failure:  # noqa: BLE001 — network, TLS, refusal: all retried
        ok = False
        error = f"{type(failure).__name__}: {failure}"
    if ok:
        delivery.status = WebhookDelivery.Status.DELIVERED
        delivery.delivered_at = now
        delivery.last_error = ""
    else:
        delivery.last_error = error[:500]
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = WebhookDelivery.Status.FAILED
        else:
            delivery.next_attempt_at = now + timedelta(seconds=RETRY_DELAYS[delivery.attempts - 1])
    delivery.save()
    IntegrationLog.objects.create(
        direction=IntegrationLog.Direction.OUTBOUND,
        event_type=event.event_type,
        status=IntegrationLog.Status.OK if ok else IntegrationLog.Status.ERROR,
        message=(f"وب‌هوک «{subscription.name}»" + ("" if ok else f" — {delivery.last_error}"))[:500],
        payload={"delivery": delivery.pk, "attempt": delivery.attempts, "response_status": delivery.response_status},
    )
    return delivery


def deliver_due(*, now=None, limit=50):
    """What the worker sweeps: every pending delivery whose time has come."""
    from integrations.models import WebhookDelivery

    now = now or timezone.now()
    count = 0
    for delivery_id in list(
        WebhookDelivery.objects.filter(status=WebhookDelivery.Status.PENDING, next_attempt_at__lte=now)
        .order_by("next_attempt_at", "id")
        .values_list("pk", flat=True)[:limit]
    ):
        with transaction.atomic():
            delivery = (
                WebhookDelivery.objects.select_for_update(skip_locked=True)
                .select_related("subscription", "event")
                .filter(pk=delivery_id, status=WebhookDelivery.Status.PENDING)
                .first()
            )
            if delivery is None:
                continue
            attempt(delivery, now=now)
            count += 1
    return count
