"""The telephony API (2.22.0): calls within the reader's scope, their
recordings, and extension mapping (Platform Admin)."""

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.access import capabilities_for
from auditlog.services import log_activity
from common.exceptions import BusinessRuleError
from common.openapi import ACCESS_DENIED_RESPONSE, CONFLICT_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated, IsPlatformAdmin
from common.throttles import SensitiveRateThrottle
from integrations.crypto import SecretsUnavailable
from telephony import services
from telephony.models import Call, Extension
from telephony.recordings import RecordingUnavailable, recording_response
from telephony.selectors import calls_for

PERSON_URLS = {"customer": "/customers/{}/", "user": "/users/{}/"}


def serialize_call(call, *, may_hear):
    pattern = PERSON_URLS.get(call.person_type)
    return {
        "id": call.pk,
        "direction": call.direction,
        "direction_label": call.get_direction_display(),
        "status": call.status,
        "status_label": call.get_status_display(),
        "external_number": call.external_number,
        "caller": call.caller_raw,
        "callee": call.callee_raw,
        "extension": call.extension,
        "user": call.user_id,
        "user_display": (call.user.get_full_name() or call.user.username) if call.user_id else "",
        "person_type": call.person_type,
        "person_id": call.person_id,
        "person_url": pattern.format(call.person_id) if pattern and call.person_id else "",
        "started_at": call.started_at.isoformat(),
        "answered_at": call.answered_at.isoformat() if call.answered_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration": call.duration,
        "billsec": call.billsec,
        "has_recording": bool(call.recording) and may_hear,
    }


class CallListView(FeatureGatedAPIMixin, APIView):
    required_feature = "telephony"
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("person_type", str), OpenApiParameter("person_id", int),
            OpenApiParameter("user", int), OpenApiParameter("status", str), OpenApiParameter("direction", str),
        ],
        responses={200: {"type": "object"}, 403: ACCESS_DENIED_RESPONSE},
        description="Calls within the caller's scope (`calls.own`: calls they handled; `calls.company`: all), newest first.",
    )
    def get(self, request):
        capabilities = capabilities_for(request.user)
        if not capabilities & {"calls.own", "calls.company"}:
            return Response({"detail": "دسترسی به تماس‌ها ندارید."}, status=status.HTTP_403_FORBIDDEN)
        rows = calls_for(request.user).select_related("user")
        params = request.query_params
        if params.get("person_type"):
            rows = rows.filter(person_type=params["person_type"])
        for name in ("person_id", "user"):
            value = params.get(name)
            if value:
                if not value.isdigit():
                    raise BusinessRuleError({name: "شناسه باید عدد باشد."})
                rows = rows.filter(**{name if name == "person_id" else "user_id": int(value)})
        if params.get("status"):
            if params["status"] not in Call.Status.values:
                raise BusinessRuleError({"status": "وضعیت نامعتبر است."})
            rows = rows.filter(status=params["status"])
        if params.get("direction"):
            if params["direction"] not in Call.Direction.values:
                raise BusinessRuleError({"direction": "جهت نامعتبر است."})
            rows = rows.filter(direction=params["direction"])
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        may_hear = "calls.recordings" in capabilities
        return paginator.get_paginated_response([serialize_call(call, may_hear=may_hear) for call in page])


class CallRecordingView(FeatureGatedAPIMixin, APIView):
    """`GET calls/<id>/recording/` — the audio, streamed, with `Range`."""

    required_feature = "telephony"
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(responses={200: None, 206: None, 403: ACCESS_DENIED_RESPONSE, 404: None, 416: None})
    def get(self, request, call_id):
        from integrations.services import secrets_of

        if "calls.recordings" not in capabilities_for(request.user):
            return Response({"detail": "شنیدن ضبط مکالمه برای شما مجاز نیست."}, status=status.HTTP_403_FORBIDDEN)
        call = calls_for(request.user).select_related("integration").filter(pk=call_id).first()
        if call is None:
            raise Http404()
        range_header = request.headers.get("Range", "")
        try:
            response = recording_response(
                call.integration, call.integration.config, secrets_of(call.integration), call, range_header
            )
        except (RecordingUnavailable, SecretsUnavailable) as error:
            return Response({"detail": str(error)}, status=status.HTTP_404_NOT_FOUND)
        # One audit row per listening, not per seek: a player's follow-up
        # range requests start past the first byte.
        if not range_header or range_header.strip() in ("bytes=0-", "bytes=0-1"):
            log_activity(actor=request.user, operation="call.recording_played", instance=call, changes={})
        response["Cache-Control"] = "private, no-store"
        return response


class ExtensionSerializer(serializers.Serializer):
    integration = serializers.IntegerField(min_value=1)
    number = serializers.CharField(max_length=20)
    user = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    label = serializers.CharField(max_length=120, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False, default=True)


def serialize_extension(row):
    return {
        "id": row.pk,
        "integration": row.integration_id,
        "number": row.number,
        "user": row.user_id,
        "user_display": (row.user.get_full_name() or row.user.username) if row.user_id else "",
        "label": row.label,
        "active": row.active,
    }


class ExtensionListView(FeatureGatedAPIMixin, APIView):
    required_feature = "telephony"
    permission_classes = [IsPlatformAdmin]

    def get_throttles(self):
        return [SensitiveRateThrottle()] if self.request.method == "POST" else super().get_throttles()

    @extend_schema(responses={200: {"type": "array", "items": {"type": "object"}}, 403: ACCESS_DENIED_RESPONSE})
    def get(self, request):
        return Response([serialize_extension(row) for row in Extension.objects.select_related("user")])

    @extend_schema(request=ExtensionSerializer, responses={201: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    def post(self, request):
        data = ExtensionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        row = services.save_extension(
            actor=request.user,
            integration_id=data.validated_data["integration"],
            number=data.validated_data["number"],
            user_id=data.validated_data.get("user"),
            label=data.validated_data.get("label", ""),
            active=data.validated_data.get("active", True),
        )
        return Response(serialize_extension(row), status=status.HTTP_201_CREATED)


class ExtensionDetailView(FeatureGatedAPIMixin, APIView):
    required_feature = "telephony"
    permission_classes = [IsPlatformAdmin]
    throttle_classes = [SensitiveRateThrottle]

    def _get(self, pk):
        row = Extension.objects.select_related("user").filter(pk=pk).first()
        if row is None:
            raise Http404()
        return row

    @extend_schema(request=ExtensionSerializer, responses={200: {"type": "object"}, 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 409: CONFLICT_RESPONSE, 429: THROTTLED_RESPONSE})
    def patch(self, request, extension_id):
        row = self._get(extension_id)
        data = ExtensionSerializer(data={
            "integration": row.integration_id, "number": row.number, "user": row.user_id,
            "label": row.label, "active": row.active, **request.data,
        })
        data.is_valid(raise_exception=True)
        row = services.save_extension(
            actor=request.user, extension=row,
            integration_id=data.validated_data["integration"],
            number=data.validated_data["number"],
            user_id=data.validated_data.get("user"),
            label=data.validated_data.get("label", ""),
            active=data.validated_data.get("active", True),
        )
        return Response(serialize_extension(row))

    @extend_schema(responses={204: None, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE})
    def delete(self, request, extension_id):
        services.delete_extension(actor=request.user, extension=self._get(extension_id))
        return Response(status=status.HTTP_204_NO_CONTENT)
