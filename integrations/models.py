"""The integrations framework's own tables (2.21.0).

- `Integration` — one configured connection to an outside system, driven by a
  provider from `integrations.providers`; its secrets are one encrypted token.
- `IntegrationLog` — what went in and out, trimmed and scrubbed of secrets.
- `DomainEvent` — the outbox: a normalized event written in the same
  transaction as the change that caused it, handled after commit, retried by
  the worker if anything failed.
- `InboundWebhookReceipt` — every accepted inbound webhook, keyed for
  idempotency.
- `WebhookSubscription` / `WebhookDelivery` — outbound webhooks, signed with
  HMAC-SHA256 and retried with backoff.
- `ApiToken` — a bearer token bound to one CRM user (decision D17), stored
  only as a hash.
"""

from django.conf import settings
from django.db import models


class Integration(models.Model):
    class Status(models.TextChoices):
        UNCONFIGURED = "unconfigured", "پیکربندی نشده"
        OK = "ok", "متصل"
        ERROR = "error", "خطا"
        DISABLED = "disabled", "غیرفعال"

    provider_key = models.CharField(max_length=40, db_index=True)
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=False)
    #: Everything that is not secret, keyed by the provider's field names.
    config = models.JSONField(default=dict, blank=True)
    #: The secret fields, as one `integrations.crypto` token. Never serialized.
    secrets_token = models.TextField(blank=True)
    #: `{field: "••••1234"}` — what the page may show instead of a secret.
    secret_hints = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNCONFIGURED)
    last_health_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider_key", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["provider_key", "name"], name="integration_provider_name_unique"),
            models.CheckConstraint(
                condition=models.Q(status__in=["unconfigured", "ok", "error", "disabled"]),
                name="integration_status_valid",
            ),
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="integration_name_nonblank"),
        ]

    def __str__(self):
        return self.name


class IntegrationLog(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "ورودی"
        OUTBOUND = "outbound", "خروجی"
        INTERNAL = "internal", "داخلی"

    class Status(models.TextChoices):
        OK = "ok", "موفق"
        ERROR = "error", "خطا"
        SKIPPED = "skipped", "نادیده"

    integration = models.ForeignKey(
        Integration, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs"
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    event_type = models.CharField(max_length=60)
    status = models.CharField(max_length=10, choices=Status.choices)
    message = models.CharField(max_length=500, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["integration", "-created_at"], name="integration_log_recent")]


class DomainEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در انتظار"
        PROCESSED = "processed", "پردازش‌شده"
        FAILED = "failed", "ناموفق"

    event_type = models.CharField(max_length=60, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    person_type = models.CharField(max_length=32, blank=True)
    person_id = models.PositiveBigIntegerField(null=True, blank=True)
    #: Set when the same fact could be emitted twice (a row saved again);
    #: unique, so the second emit is a no-op.
    dedupe_key = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    available_at = models.DateTimeField()
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["status", "available_at"], name="domain_event_due")]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"], condition=~models.Q(dedupe_key=""), name="domain_event_dedupe_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "processed", "failed"]), name="domain_event_status_valid"
            ),
        ]


class InboundWebhookReceipt(models.Model):
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="receipts")
    idempotency_key = models.CharField(max_length=128)
    payload = models.JSONField(default=dict, blank=True)
    result = models.CharField(max_length=200, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-received_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["integration", "idempotency_key"], name="inbound_webhook_receipt_unique"
            ),
        ]


class WebhookSubscription(models.Model):
    name = models.CharField(max_length=120)
    url = models.URLField(max_length=500)
    #: Event types this subscriber receives; empty means every event.
    event_types = models.JSONField(default=list, blank=True)
    #: The HMAC signing secret, as an `integrations.crypto` token.
    secret_token = models.TextField()
    secret_hint = models.CharField(max_length=40, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="webhook_subscription_name_nonblank"),
        ]


class WebhookDelivery(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "در صف"
        DELIVERED = "delivered", "تحویل‌شده"
        FAILED = "failed", "ناموفق"

    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE, related_name="deliveries")
    event = models.ForeignKey(DomainEvent, on_delete=models.CASCADE, related_name="deliveries")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(db_index=True)
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="webhook_delivery_due")]
        constraints = [
            models.UniqueConstraint(fields=["subscription", "event"], name="webhook_delivery_once"),
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "delivered", "failed"]), name="webhook_delivery_status_valid"
            ),
        ]


class ApiToken(models.Model):
    class Scope(models.TextChoices):
        READ = "read", "خواندن"
        WRITE = "write", "نوشتن"

    name = models.CharField(max_length=120)
    #: Whose rights the token carries — every role, capability and scope rule
    #: of this user applies to it unchanged (decision D17).
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_tokens")
    token_hash = models.CharField(max_length=64, unique=True)
    #: The first characters, so a token can be recognised without being stored.
    prefix = models.CharField(max_length=16)
    scopes = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(name__regex=r"\S"), name="api_token_name_nonblank"),
        ]
