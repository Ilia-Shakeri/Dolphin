"""Every change to the integrations framework goes through here (2.21.0).

Configuring an outside connection, a webhook subscriber or an API token is
the Platform Admin's, like the SMS gateway before it — each holds credentials
that act for the whole deployment. Each also needs its own feature:
`integrations`, `outbound_webhooks`, `public_api`. Every change is audited;
no secret value is ever written to the audit log, a log row or a response.
"""

import hashlib
import secrets as secrets_module

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from accounts.access import is_crm_identity
from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from common.integrations import mask_secret
from integrations.crypto import SecretsUnavailable, decrypt_json, encrypt_json
from integrations.events import EVENT_TYPES
from integrations.models import ApiToken, Integration, IntegrationLog, WebhookSubscription
from integrations.providers import clean_config, provider_for

TOKEN_PREFIX = "dol_"
#: Payload keys never written to a log, whatever a provider sends.
_SECRET_WORDS = ("password", "secret", "token", "key", "authorization", "signature")
LOG_PAYLOAD_LIMIT = 4000


def _require(actor, feature):
    if not feature_enabled(feature):
        raise BusinessPermissionDenied("این بخش در این استقرار فعال نیست.")
    if actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("این تنظیم فقط برای مدیر پلتفرم مجاز است.")


def redact(payload):
    """A copy of `payload` with anything secret-looking replaced, trimmed."""
    if isinstance(payload, dict):
        return {
            key: ("•••" if any(word in str(key).lower() for word in _SECRET_WORDS) else redact(value))
            for key, value in list(payload.items())[:50]
        }
    if isinstance(payload, list):
        return [redact(item) for item in payload[:50]]
    if isinstance(payload, str):
        return payload[:500]
    return payload


def log(integration, *, direction, event_type, status, message="", payload=None):
    return IntegrationLog.objects.create(
        integration=integration,
        direction=direction,
        event_type=event_type[:60],
        status=status,
        message=(message or "")[:500],
        payload=redact(payload or {}),
    )


def secrets_of(integration):
    """The decrypted secrets, for a provider to use and nobody to see."""
    return decrypt_json(integration.secrets_token)


def _store_secrets(integration, provider, values):
    try:
        integration.secrets_token = encrypt_json(values)
    except SecretsUnavailable as error:
        if values:
            raise BusinessRuleError(
                {"secrets": "کلید رمزنگاری (DOLPHIN_SECRETS_KEY) روی این استقرار تنظیم نشده؛ رمزها ذخیره نمی‌شوند."}
            ) from error
        integration.secrets_token = ""
    integration.secret_hints = {
        field.key: mask_secret(values[field.key]) for field in provider.fields if field.is_secret and values.get(field.key)
    }


# --- Integrations ----------------------------------------------------------------


@transaction.atomic
def create_integration(*, actor, provider_key, name, config=None, secrets=None, enabled=False):
    _require(actor, "integrations")
    provider = provider_for(provider_key)
    if provider is None:
        raise BusinessRuleError({"provider_key": "نوع اتصال ناشناخته است."})
    if provider.required_feature and not feature_enabled(provider.required_feature):
        raise BusinessPermissionDenied("این نوع اتصال در این استقرار فعال نیست.")
    if provider.singleton and Integration.objects.filter(provider_key=provider_key).exists():
        raise BusinessConflictError({"provider_key": "از این نوع اتصال فقط یکی مجاز است."})
    name = (name or "").strip()
    if not name:
        raise BusinessRuleError({"name": "نام اتصال را بنویسید."})
    clean, secret_values, errors = clean_config(provider, config, secrets)
    if errors:
        raise BusinessRuleError(errors)
    if Integration.objects.filter(provider_key=provider_key, name=name).exists():
        raise BusinessConflictError({"name": "اتصالی با همین نام وجود دارد."})
    integration = Integration(provider_key=provider_key, name=name[:120], config=clean, enabled=bool(enabled), created_by=actor)
    _store_secrets(integration, provider, secret_values)
    integration.status = Integration.Status.DISABLED if not integration.enabled else Integration.Status.UNCONFIGURED
    integration.save()
    log_activity(actor=actor, operation="integration.created", instance=integration, changes={"fields": sorted(clean)})
    return integration


@transaction.atomic
def update_integration(*, actor, integration, name=None, config=None, secrets=None, enabled=None):
    _require(actor, "integrations")
    integration = Integration.objects.select_for_update().get(pk=integration.pk)
    provider = provider_for(integration.provider_key)
    if provider is None:
        raise BusinessRuleError({"provider_key": "این نوع اتصال در این نسخه وجود ندارد."})
    changed = []
    if name is not None:
        name = name.strip()
        if not name:
            raise BusinessRuleError({"name": "نام اتصال را بنویسید."})
        if name != integration.name:
            if Integration.objects.filter(provider_key=integration.provider_key, name=name).exclude(pk=integration.pk).exists():
                raise BusinessConflictError({"name": "اتصالی با همین نام وجود دارد."})
            integration.name = name[:120]
            changed.append("name")
    if config is not None or secrets is not None:
        try:
            existing = secrets_of(integration)
        except SecretsUnavailable:
            existing = {}
        clean, secret_values, errors = clean_config(
            provider,
            config if config is not None else integration.config,
            secrets or {},
            existing_secrets=existing,
        )
        if errors:
            raise BusinessRuleError(errors)
        if clean != integration.config:
            integration.config = clean
            changed.append("config")
        if secret_values != existing:
            _store_secrets(integration, provider, secret_values)
            changed.append("secrets")
    if enabled is not None and bool(enabled) != integration.enabled:
        integration.enabled = bool(enabled)
        changed.append("enabled")
        integration.status = Integration.Status.UNCONFIGURED if integration.enabled else Integration.Status.DISABLED
    if changed:
        integration.save()
        log_activity(actor=actor, operation="integration.updated", instance=integration, changes={"fields": sorted(changed)})
    return integration


@transaction.atomic
def delete_integration(*, actor, integration):
    _require(actor, "integrations")
    log_activity(actor=actor, operation="integration.deleted", instance=integration, changes={})
    try:
        integration.delete()
    except ProtectedError as error:
        raise BusinessConflictError(
            {"id": "این اتصال سوابق وابسته (مثل تماس‌ها) دارد؛ به‌جای حذف، آن را غیرفعال کنید."}
        ) from error


def test_integration(*, actor, integration):
    """Run the provider's own check now; store and log what it said."""
    _require(actor, "integrations")
    provider = provider_for(integration.provider_key)
    try:
        result = provider.test_connection(integration, integration.config, secrets_of(integration))
    except SecretsUnavailable:
        from integrations.providers import ConnectionResult

        result = ConnectionResult(False, "رمزهای ذخیره‌شده با کلید فعلی باز نمی‌شوند؛ دوباره واردشان کنید.")
    except Exception as error:  # noqa: BLE001 — a provider's own failure is the answer
        from integrations.providers import ConnectionResult

        result = ConnectionResult(False, f"{type(error).__name__}: {error}")
    record_health(integration, result.ok, result.message)
    log(
        integration,
        direction=IntegrationLog.Direction.OUTBOUND,
        event_type="connection.test",
        status=IntegrationLog.Status.OK if result.ok else IntegrationLog.Status.ERROR,
        message=result.message,
    )
    log_activity(actor=actor, operation="integration.tested", instance=integration, changes={})
    return result


def record_health(integration, ok, message=""):
    """Store a health observation — from a test, a listener or a sync."""
    now = timezone.now()
    status = (
        Integration.Status.DISABLED
        if not integration.enabled
        else (Integration.Status.OK if ok else Integration.Status.ERROR)
    )
    Integration.objects.filter(pk=integration.pk).update(
        status=status, last_health_at=now, last_error="" if ok else (message or "")[:500]
    )
    integration.status, integration.last_health_at = status, now
    integration.last_error = "" if ok else (message or "")[:500]


# --- Outbound webhooks ----------------------------------------------------------------


def _clean_event_types(event_types):
    if not isinstance(event_types, list) or any(item not in EVENT_TYPES for item in event_types):
        raise BusinessRuleError({"event_types": "رویدادها را از فهرست انتخاب کنید."})
    return sorted(set(event_types))


@transaction.atomic
def create_subscription(*, actor, name, url, event_types=None):
    """A new subscriber and its signing secret, shown this once only."""
    from integrations.webhooks import TargetRefused, validate_target

    _require(actor, "outbound_webhooks")
    name = (name or "").strip()
    if not name:
        raise BusinessRuleError({"name": "نام را بنویسید."})
    try:
        validate_target(url)
    except TargetRefused as error:
        raise BusinessRuleError({"url": str(error)}) from error
    secret = secrets_module.token_urlsafe(32)
    try:
        token = encrypt_json({"secret": secret})
    except SecretsUnavailable as error:
        raise BusinessRuleError(
            {"url": "کلید رمزنگاری (DOLPHIN_SECRETS_KEY) روی این استقرار تنظیم نشده است."}
        ) from error
    subscription = WebhookSubscription.objects.create(
        name=name[:120], url=url, event_types=_clean_event_types(event_types or []),
        secret_token=token, secret_hint=mask_secret(secret), created_by=actor,
    )
    log_activity(actor=actor, operation="webhook_subscription.created", instance=subscription, changes={})
    return subscription, secret


@transaction.atomic
def update_subscription(*, actor, subscription, name=None, url=None, event_types=None, active=None):
    from integrations.webhooks import TargetRefused, validate_target

    _require(actor, "outbound_webhooks")
    subscription = WebhookSubscription.objects.select_for_update().get(pk=subscription.pk)
    changed = []
    if name is not None:
        name = name.strip()
        if not name:
            raise BusinessRuleError({"name": "نام را بنویسید."})
        subscription.name, changed = name[:120], [*changed, "name"]
    if url is not None and url != subscription.url:
        try:
            validate_target(url)
        except TargetRefused as error:
            raise BusinessRuleError({"url": str(error)}) from error
        subscription.url, changed = url, [*changed, "url"]
    if event_types is not None:
        subscription.event_types, changed = _clean_event_types(event_types), [*changed, "event_types"]
    if active is not None:
        subscription.active, changed = bool(active), [*changed, "active"]
    if changed:
        subscription.save()
        log_activity(actor=actor, operation="webhook_subscription.updated", instance=subscription, changes={"fields": sorted(changed)})
    return subscription


@transaction.atomic
def delete_subscription(*, actor, subscription):
    _require(actor, "outbound_webhooks")
    log_activity(actor=actor, operation="webhook_subscription.deleted", instance=subscription, changes={})
    subscription.delete()


def ping_subscription(*, actor, subscription):
    """Send one `webhook.ping` to this subscriber now; the delivery."""
    from integrations.models import DomainEvent, WebhookDelivery
    from integrations.webhooks import attempt

    _require(actor, "outbound_webhooks")
    now = timezone.now()
    event = DomainEvent.objects.create(
        event_type="webhook.ping",
        payload={"message": "آزمایش اتصال وب‌هوک از دلفین"},
        status=DomainEvent.Status.PROCESSED,
        available_at=now,
        processed_at=now,
    )
    delivery = WebhookDelivery.objects.create(subscription=subscription, event=event, next_attempt_at=now)
    return attempt(delivery, now=now)


# --- API tokens ----------------------------------------------------------------------------


def hash_token(plain):
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


@transaction.atomic
def create_api_token(*, actor, name, user, scopes, expires_at=None):
    """A new bearer token for `user`; the plain value is returned once only."""
    _require(actor, "public_api")
    name = (name or "").strip()
    if not name:
        raise BusinessRuleError({"name": "نام توکن را بنویسید."})
    if user is None or not is_crm_identity(user):
        raise BusinessRuleError({"user": "کاربرِ توکن باید یک کاربر فعال سامانه باشد."})
    if user.role == User.Role.PLATFORM_ADMIN:
        # A leaked token must never be a Platform Admin: bind integrations
        # to a dedicated account with only the rights they need.
        raise BusinessRuleError({"user": "توکن را به یک کاربر اختصاصی با کمترین دسترسی لازم بدهید، نه مدیر پلتفرم."})
    scopes = sorted(set(scopes or []))
    if not scopes or set(scopes) - set(ApiToken.Scope.values):
        raise BusinessRuleError({"scopes": "دامنهٔ توکن را انتخاب کنید (خواندن و/یا نوشتن)."})
    if expires_at is not None and expires_at <= timezone.now():
        raise BusinessRuleError({"expires_at": "تاریخ انقضا باید در آینده باشد."})
    plain = TOKEN_PREFIX + secrets_module.token_urlsafe(32)
    token = ApiToken.objects.create(
        name=name[:120], user=user, token_hash=hash_token(plain), prefix=plain[:12],
        scopes=scopes, created_by=actor, expires_at=expires_at,
    )
    log_activity(actor=actor, operation="api_token.created", instance=token, changes={"fields": scopes})
    return token, plain


@transaction.atomic
def revoke_api_token(*, actor, token):
    _require(actor, "public_api")
    token = ApiToken.objects.select_for_update().get(pk=token.pk)
    if token.revoked_at is None:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
        log_activity(actor=actor, operation="api_token.revoked", instance=token, changes={})
    return token
