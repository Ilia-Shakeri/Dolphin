"""The integrations API (2.21.0). Management is Platform Admin only and behind
its feature; the inbound webhook is authenticated by the provider's own
signature instead of a session."""

import hashlib
import json

from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import User
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessRuleError
from common.openapi import ACCESS_DENIED_RESPONSE, CONFLICT_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsPlatformAdmin
from common.throttles import SensitiveRateThrottle
from integrations import services
from integrations.crypto import SecretsUnavailable, secrets_available
from integrations.events import EVENT_TYPES
from integrations.models import (
    ApiToken,
    InboundWebhookReceipt,
    Integration,
    IntegrationLog,
    WebhookDelivery,
    WebhookSubscription,
)
from integrations.providers import provider_for, providers


def serialize_integration(integration):
    provider = provider_for(integration.provider_key)
    return {
        "id": integration.pk,
        "provider_key": integration.provider_key,
        "provider_name": provider.name if provider else integration.provider_key,
        "name": integration.name,
        "enabled": integration.enabled,
        "status": integration.status,
        "status_label": integration.get_status_display(),
        "last_health_at": integration.last_health_at.isoformat() if integration.last_health_at else None,
        "last_error": integration.last_error,
        "config": integration.config,
        "secret_hints": integration.secret_hints,
        "webhook_path": f"/api/v1/integrations/{integration.pk}/webhook/" if provider and provider.accepts_webhooks else "",
        "created_at": integration.created_at.isoformat(),
        "updated_at": integration.updated_at.isoformat(),
    }


#: Log rows also record the framework's own actions, which are not domain
#: events; they need a name too.
LOG_EVENT_LABELS = {
    **EVENT_TYPES,
    "connection.test": "آزمایش اتصال",
    "webhook.rejected": "درخواست ردشده",
    "cdr.sync": "همگام‌سازی سوابق تماس",
    "ami.connection": "اتصال به مرکز تلفن",
}


def serialize_log(row):
    return {
        "id": row.pk,
        "integration": row.integration_id,
        "direction": row.direction,
        "direction_label": row.get_direction_display(),
        "event_type": row.event_type,
        "event_label": LOG_EVENT_LABELS.get(row.event_type, row.event_type),
        "status": row.status,
        "status_label": row.get_status_display(),
        "message": row.message,
        "created_at": row.created_at.isoformat(),
    }


class AdminAPIView(FeatureGatedAPIMixin, APIView):
    required_feature = "integrations"
    permission_classes = [IsPlatformAdmin]

    def get_throttles(self):
        if self.request.method not in {"GET", "HEAD", "OPTIONS"}:
            return [SensitiveRateThrottle()]
        return super().get_throttles()


class IntegrationWriteSerializer(serializers.Serializer):
    provider_key = serializers.CharField(max_length=40, required=False)
    name = serializers.CharField(max_length=120, required=False)
    enabled = serializers.BooleanField(required=False)
    config = serializers.DictField(required=False)
    secrets = serializers.DictField(required=False, write_only=True)


class ProvidersView(AdminAPIView):
    @extend_schema(responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        return Response({
            "secrets_available": secrets_available(),
            "providers": [
                provider.describe()
                for provider in providers()
                if not provider.required_feature or feature_enabled(provider.required_feature)
            ],
            "event_types": [{"key": key, "label": label} for key, label in EVENT_TYPES.items()],
        })


class IntegrationListView(AdminAPIView):
    @extend_schema(operation_id="api_v1_integrations_list", responses={200: {"type": "array", "items": {"type": "object"}}, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        return Response([serialize_integration(row) for row in Integration.objects.all()])

    @extend_schema(
        request=IntegrationWriteSerializer,
        responses={201: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Creates one connection. `secrets` is write-only; it is stored encrypted and never returned.",
    )
    def post(self, request):
        data = IntegrationWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        integration = services.create_integration(
            actor=request.user,
            provider_key=data.validated_data.get("provider_key", ""),
            name=data.validated_data.get("name", ""),
            config=data.validated_data.get("config"),
            secrets=data.validated_data.get("secrets"),
            enabled=data.validated_data.get("enabled", False),
        )
        return Response(serialize_integration(integration), status=status.HTTP_201_CREATED)


class IntegrationDetailView(AdminAPIView):
    def _get(self, pk):
        integration = Integration.objects.filter(pk=pk).first()
        if integration is None:
            raise Http404()
        return integration

    @extend_schema(responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None})
    def get(self, request, integration_id):
        return Response(serialize_integration(self._get(integration_id)))

    @extend_schema(
        request=IntegrationWriteSerializer,
        responses={200: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE},
        description="A secret left out or blank keeps the stored value; secrets are never returned.",
    )
    def patch(self, request, integration_id):
        data = IntegrationWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        if "provider_key" in data.validated_data:
            raise BusinessRuleError({"provider_key": "نوع اتصال پس از ساخت تغییر نمی‌کند."})
        integration = services.update_integration(
            actor=request.user,
            integration=self._get(integration_id),
            name=data.validated_data.get("name"),
            config=data.validated_data.get("config"),
            secrets=data.validated_data.get("secrets"),
            enabled=data.validated_data.get("enabled"),
        )
        return Response(serialize_integration(integration))

    @extend_schema(responses={204: None, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    def delete(self, request, integration_id):
        services.delete_integration(actor=request.user, integration=self._get(integration_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class IntegrationTestView(IntegrationDetailView):
    http_method_names = ["post", "options"]
    @extend_schema(request=None, responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE})
    def post(self, request, integration_id):
        integration = self._get(integration_id)
        result = services.test_integration(actor=request.user, integration=integration)
        return Response({"ok": result.ok, "message": result.message, "integration": serialize_integration(integration)})


class IntegrationLogView(AdminAPIView):
    @extend_schema(
        parameters=[OpenApiParameter("integration", int, description="Only this connection's rows.")],
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE},
    )
    def get(self, request):
        rows = IntegrationLog.objects.all()
        integration = request.query_params.get("integration")
        if integration:
            if not integration.isdigit():
                raise BusinessRuleError({"integration": "شناسه باید عدد باشد."})
            rows = rows.filter(integration_id=int(integration))
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response([serialize_log(row) for row in page])


class InboundWebhookView(APIView):
    """`POST integrations/<id>/webhook/` — a connected system reporting in.

    No session and no CSRF: the provider's own signature is the
    authentication (the generic provider: HMAC-SHA256 of the raw body).
    Idempotent on `Idempotency-Key`, else the payload's `id`, else the body's
    hash; a repeat answers 200 and does nothing.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_webhook"

    @extend_schema(
        request={"application/json": {"type": "object"}},
        responses={200: {"type": "object"}, 202: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: None, 404: None, 429: THROTTLED_RESPONSE},
    )
    def post(self, request, integration_id):
        if not feature_enabled("integrations"):
            raise Http404()
        integration = Integration.objects.filter(pk=integration_id, enabled=True).first()
        provider = provider_for(integration.provider_key) if integration else None
        if integration is None or provider is None or not provider.accepts_webhooks:
            raise Http404()
        body = request.body
        try:
            secret_values = services.secrets_of(integration)
        except SecretsUnavailable:
            return Response({"detail": "اتصال آمادهٔ دریافت نیست."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not provider.verify_inbound(integration, secret_values, request, body):
            services.log(
                integration, direction=IntegrationLog.Direction.INBOUND, event_type="webhook.rejected",
                status=IntegrationLog.Status.ERROR, message="امضای درخواست نامعتبر بود.",
            )
            return Response({"detail": "امضای درخواست نامعتبر است."}, status=status.HTTP_403_FORBIDDEN)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if not isinstance(payload, dict):
            raise BusinessRuleError({"body": "بدنهٔ درخواست باید یک شیء JSON باشد."})
        key = (
            request.headers.get("Idempotency-Key")
            or str(payload.get("id") or "")
            or hashlib.sha256(body).hexdigest()
        )[:128]
        try:
            with transaction.atomic():
                receipt = InboundWebhookReceipt.objects.create(
                    integration=integration, idempotency_key=key, payload=services.redact(payload)
                )
                result = provider.handle_inbound(integration, integration.config, payload)
                receipt.result = (result or "")[:200]
                receipt.save(update_fields=["result"])
        except IntegrityError:
            return Response({"status": "duplicate"}, status=status.HTTP_200_OK)
        services.log(
            integration, direction=IntegrationLog.Direction.INBOUND, event_type=str(payload.get("type") or "webhook")[:60],
            status=IntegrationLog.Status.OK, message=result, payload=payload,
        )
        services.record_health(integration, True)
        return Response({"status": "accepted", "result": result}, status=status.HTTP_202_ACCEPTED)


# --- Outbound webhooks ------------------------------------------------------------------


def serialize_subscription(subscription):
    return {
        "id": subscription.pk,
        "name": subscription.name,
        "url": subscription.url,
        "event_types": subscription.event_types,
        "secret_hint": subscription.secret_hint,
        "active": subscription.active,
        "created_at": subscription.created_at.isoformat(),
    }


class SubscriptionWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    url = serializers.CharField(max_length=500, required=False)
    event_types = serializers.ListField(child=serializers.CharField(max_length=60), required=False)
    active = serializers.BooleanField(required=False)


class SubscriptionListView(AdminAPIView):
    required_feature = "outbound_webhooks"

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        return Response([serialize_subscription(row) for row in WebhookSubscription.objects.all()])

    @extend_schema(
        request=SubscriptionWriteSerializer,
        responses={201: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Creates a subscriber. The response carries its signing `secret` this once; it is stored encrypted.",
    )
    def post(self, request):
        data = SubscriptionWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        subscription, secret = services.create_subscription(
            actor=request.user,
            name=data.validated_data.get("name", ""),
            url=data.validated_data.get("url", ""),
            event_types=data.validated_data.get("event_types", []),
        )
        return Response({**serialize_subscription(subscription), "secret": secret}, status=status.HTTP_201_CREATED)


class SubscriptionDetailView(AdminAPIView):
    required_feature = "outbound_webhooks"

    def _get(self, pk):
        subscription = WebhookSubscription.objects.filter(pk=pk).first()
        if subscription is None:
            raise Http404()
        return subscription

    @extend_schema(
        request=SubscriptionWriteSerializer,
        responses={200: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
    )
    def patch(self, request, subscription_id):
        data = SubscriptionWriteSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        subscription = services.update_subscription(
            actor=request.user, subscription=self._get(subscription_id), **data.validated_data
        )
        return Response(serialize_subscription(subscription))

    @extend_schema(responses={204: None, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE})
    def delete(self, request, subscription_id):
        services.delete_subscription(actor=request.user, subscription=self._get(subscription_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubscriptionPingView(SubscriptionDetailView):
    http_method_names = ["post", "options"]
    @extend_schema(request=None, responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE})
    def post(self, request, subscription_id):
        delivery = services.ping_subscription(actor=request.user, subscription=self._get(subscription_id))
        return Response({
            "delivered": delivery.status == WebhookDelivery.Status.DELIVERED,
            "response_status": delivery.response_status,
            "error": delivery.last_error,
        })


class SubscriptionDeliveriesView(SubscriptionDetailView):
    http_method_names = ["get", "head", "options"]
    @extend_schema(responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None})
    def get(self, request, subscription_id):
        rows = self._get(subscription_id).deliveries.select_related("event")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response([
            {
                "id": row.pk,
                "event_type": row.event.event_type,
                "event_label": EVENT_TYPES.get(row.event.event_type, row.event.event_type),
                "status": row.status,
                "status_label": row.get_status_display(),
                "attempts": row.attempts,
                "response_status": row.response_status,
                "last_error": row.last_error,
                "next_attempt_at": row.next_attempt_at.isoformat(),
                "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            }
            for row in page
        ])


# --- API tokens -----------------------------------------------------------------------------


def serialize_token(token):
    return {
        "id": token.pk,
        "name": token.name,
        "user": token.user_id,
        "user_display": token.user.get_full_name() or token.user.username,
        "prefix": token.prefix,
        "scopes": token.scopes,
        "created_at": token.created_at.isoformat(),
        "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "revoked_at": token.revoked_at.isoformat() if token.revoked_at else None,
    }


class TokenWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    user = serializers.IntegerField(min_value=1)
    scopes = serializers.ListField(child=serializers.CharField(max_length=10))
    expires_at = serializers.CharField(required=False, allow_blank=True)


class TokenListView(AdminAPIView):
    required_feature = "public_api"

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        return Response([serialize_token(row) for row in ApiToken.objects.select_related("user")])

    @extend_schema(
        request=TokenWriteSerializer,
        responses={201: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Creates a token bound to `user`. The plain `token` is in this response only; only its hash is kept.",
    )
    def post(self, request):
        data = TokenWriteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        expires_raw = data.validated_data.get("expires_at") or ""
        expires_at = parse_datetime(expires_raw) if expires_raw else None
        if expires_raw and expires_at is None:
            raise BusinessRuleError({"expires_at": "تاریخ انقضا نامعتبر است."})
        token, plain = services.create_api_token(
            actor=request.user,
            name=data.validated_data["name"],
            user=User.objects.filter(pk=data.validated_data["user"]).first(),
            scopes=data.validated_data["scopes"],
            expires_at=expires_at,
        )
        return Response({**serialize_token(token), "token": plain}, status=status.HTTP_201_CREATED)


class TokenRevokeView(AdminAPIView):
    required_feature = "public_api"

    @extend_schema(request=None, responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE, 404: None, 429: THROTTLED_RESPONSE})
    def post(self, request, token_id):
        token = ApiToken.objects.select_related("user").filter(pk=token_id).first()
        if token is None:
            raise Http404()
        return Response(serialize_token(services.revoke_api_token(actor=request.user, token=token)))
