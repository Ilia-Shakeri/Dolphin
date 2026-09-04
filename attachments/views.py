from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from attachments import services
from attachments.models import Attachment
from attachments.selectors import PARENT_SELECTORS, attachments_for
from attachments.serializers import (
    AttachmentDetailSerializer,
    AttachmentListQuerySerializer,
    AttachmentUploadSerializer,
)
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE
from common.permissions import FeatureGatedAPIMixin, IsActiveAuthenticated
from common.throttles import SensitiveRateThrottle


class AttachmentAccessMixin(FeatureGatedAPIMixin):
    required_feature = "attachments"
    permission_classes = [IsActiveAuthenticated]
    throttle_classes = [SensitiveRateThrottle]


def _visible_attachments(user):
    """Every attachment across all five parent types this user may see at all.

    Used only to resolve a direct `attachment_id` (download, delete) to a row
    without leaking whether it exists outside scope — `get_object_or_404`
    against this is a 404, not a 403, exactly like every other direct-id read
    in this codebase.
    """
    scope = Q()
    for field, selector in PARENT_SELECTORS.items():
        scope |= Q(**{f"{field}__in": selector(user).values_list("pk", flat=True)})
    return Attachment.objects.filter(scope)


class AttachmentListUploadView(AttachmentAccessMixin, APIView):
    # The project-wide default parser (common.parsers.BoundedJSONParser)
    # accepts JSON only; a file upload needs MultiPartParser explicitly, the
    # same override sales/views.py's own import-xlsx actions use.
    parser_classes = [MultiPartParser]

    @extend_schema(
        parameters=[AttachmentListQuerySerializer],
        responses={
            200: AttachmentDetailSerializer(many=True),
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description="Attachments on exactly one parent record, within the caller's object scope for that record.",
    )
    def get(self, request):
        query = AttachmentListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        queryset = attachments_for(
            request.user, field_name=query.validated_data["field_name"], parent_id=query.validated_data["parent_id"],
        )
        response = Response(AttachmentDetailSerializer(queryset, many=True).data)
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        request=AttachmentUploadSerializer,
        responses={
            200: AttachmentDetailSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            403: ACCESS_DENIED_RESPONSE,
            429: THROTTLED_RESPONSE,
        },
        description=(
            "Uploads one file against exactly one parent record. The stored content type is sniffed from the "
            "file's own bytes, never taken from the client's declared Content-Type or the filename."
        ),
    )
    def post(self, request):
        serializer = AttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        attachment = services.upload_attachment(
            actor=request.user,
            field_name=serializer.validated_data["field_name"],
            parent_id=serializer.validated_data["parent_id"],
            original_filename=upload.name,
            content=upload.read(),
        )
        response = Response(AttachmentDetailSerializer(attachment).data)
        response["Cache-Control"] = "private, no-store"
        return response


class AttachmentDownloadView(AttachmentAccessMixin, APIView):
    @extend_schema(
        responses={200: bytes, 403: ACCESS_DENIED_RESPONSE, 404: None, 429: THROTTLED_RESPONSE},
        description="Streams the stored file. 404 for anything outside the caller's object scope, same as a direct-id read elsewhere.",
    )
    def get(self, request, attachment_id):
        attachment = get_object_or_404(_visible_attachments(request.user), pk=attachment_id)
        response = HttpResponse(bytes(attachment.content), content_type=attachment.content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        safe_name = attachment.original_filename.replace('"', "")
        response["Content-Disposition"] = f'attachment; filename="{safe_name}"'
        return response


class AttachmentDeleteView(AttachmentAccessMixin, APIView):
    """POST, not the HTTP DELETE verb — every mutation in this codebase's API
    goes through POST (see the bulk-delete actions elsewhere in dolphin-app.js),
    a convention `common/tests/test_commercial_shell.py` checks by scanning
    the whole shared script for a literal HTTP DELETE call.
    """

    @extend_schema(
        # The attachment is named by the URL and there is no body to send.
        # Said explicitly because the schema generator otherwise tries to
        # guess a request serializer for a write method, finds none on a
        # plain `APIView`, and fails generation — the same reason every
        # other bodyless POST in this codebase declares it.
        request=None,
        responses={204: None, 403: ACCESS_DENIED_RESPONSE, 404: None, 429: THROTTLED_RESPONSE},
        description="Permanently deletes one attachment. Elevated roles only (sales_manager, company_it, platform_admin).",
    )
    def post(self, request, attachment_id):
        attachment = get_object_or_404(_visible_attachments(request.user), pk=attachment_id)
        services.delete_attachment(actor=request.user, attachment=attachment)
        return Response(status=204)
