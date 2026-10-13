"""`GET attachments/library/` — every file the reader may see, in one place (2.40.42).

Roadmap item 13: the UI kit's file manager, with real files. A file is visible
exactly when its record is (`views._visible_attachments`, the scope download
and delete already use); this adds no scoping of its own, only a search, two
filters and the name of the record each file belongs to.
"""

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView

from accounts.access import can_delete
from attachments.selectors import PARENT_DELETE_CAPABILITY, PARENT_FIELDS
from attachments.serializers import AttachmentDetailSerializer
from attachments.views import AttachmentAccessMixin, _visible_attachments
from common.openapi import ACCESS_DENIED_RESPONSE, THROTTLED_RESPONSE, VALIDATION_ERROR_RESPONSE

#: The record kinds, as the page names them.
PARENT_LABELS = {
    "customer": "مشتری",
    "lead": "سرنخ",
    "invoice": "فاکتور",
    "sales_document": "سند فروش",
    "after_sales_request": "پرونده پس از فروش",
}
PARENT_URLS = {
    "customer": "/customers/{}/",
    "lead": "/leads/{}/",
    "invoice": "/invoices/{}/",
    "sales_document": "/sales-documents/{}/",
    "after_sales_request": "/after-sales/{}/",
}
#: `?kind=` — the two families of file the panel accepts.
KINDS = {"image": Q(content_type__startswith="image/"), "pdf": Q(content_type="application/pdf")}


def _parent_name(attachment, field):
    record = getattr(attachment, field)
    if field == "customer":
        return record.full_name
    if field == "lead":
        campaign = getattr(record.campaign, "name", "") if record.campaign_id else ""
        return f"سرنخ {record.pk}" + (f" — {campaign}" if campaign else "")
    if field == "invoice":
        return record.number
    if field == "sales_document":
        return record.document_number
    return record.subject


class LibraryRowSerializer(AttachmentDetailSerializer):
    parent_type_display = serializers.SerializerMethodField()
    parent_name = serializers.SerializerMethodField()
    parent_url = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta(AttachmentDetailSerializer.Meta):
        fields = AttachmentDetailSerializer.Meta.fields + ("parent_type_display", "parent_name", "parent_url", "can_delete")
        read_only_fields = fields

    def get_parent_type_display(self, instance) -> str:
        return PARENT_LABELS.get(self.get_parent_field(instance), "")

    def get_parent_name(self, instance) -> str:
        return _parent_name(instance, self.get_parent_field(instance))

    def get_parent_url(self, instance) -> str:
        return PARENT_URLS[self.get_parent_field(instance)].format(self.get_parent_id(instance))

    def get_can_delete(self, instance) -> bool:
        return can_delete(self.context["request"].user, PARENT_DELETE_CAPABILITY[self.get_parent_field(instance)])


class AttachmentLibraryView(AttachmentAccessMixin, ListAPIView):
    serializer_class = LibraryRowSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("search", str, description="Part of a file name."),
            OpenApiParameter("parent", str, enum=list(PARENT_FIELDS), description="Only files on this kind of record."),
            OpenApiParameter("kind", str, enum=list(KINDS), description="Only images, or only PDFs."),
        ],
        responses={200: LibraryRowSerializer(many=True), 400: VALIDATION_ERROR_RESPONSE, 403: ACCESS_DENIED_RESPONSE, 429: THROTTLED_RESPONSE},
        description="Every attachment the caller may see, newest first, with the record each belongs to.",
    )
    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def get_queryset(self):
        params = self.request.query_params
        queryset = _visible_attachments(self.request.user).select_related(
            "uploaded_by", "customer", "lead__campaign", "invoice", "sales_document", "after_sales_request",
        ).defer("content")
        parent = params.get("parent")
        if parent:
            if parent not in PARENT_FIELDS:
                raise ValidationError({"parent": "نوع رکورد معتبر نیست."})
            queryset = queryset.filter(**{f"{parent}__isnull": False})
        kind = params.get("kind")
        if kind:
            if kind not in KINDS:
                raise ValidationError({"kind": "نوع فایل معتبر نیست."})
            queryset = queryset.filter(KINDS[kind])
        search = (params.get("search") or "").strip()
        if search:
            queryset = queryset.filter(original_filename__icontains=search[:100])
        return queryset.order_by("-uploaded_at", "-id")
