from rest_framework import serializers

from attachments.models import Attachment
from attachments.selectors import PARENT_FIELDS
from common.serializers import RejectServerFieldsMixin


class AttachmentUploadSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """Multipart input: a real file, and exactly one parent id.

    The parent ids are plain integers, not `PrimaryKeyRelatedField` — object
    scope for *which* parent a caller may attach to is enforced once, in
    `attachments.services.upload_attachment` (`parent_is_visible`), not
    duplicated here as a second, easier-to-forget check.
    """

    file = serializers.FileField()
    customer = serializers.IntegerField(required=False, min_value=1)
    lead = serializers.IntegerField(required=False, min_value=1)
    invoice = serializers.IntegerField(required=False, min_value=1)
    sales_document = serializers.IntegerField(required=False, min_value=1)
    after_sales_request = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        named = [name for name in PARENT_FIELDS if attrs.get(name)]
        if len(named) != 1:
            raise serializers.ValidationError(
                {"parent": "دقیقاً یکی از مشتری، سرنخ، فاکتور، سند فروش یا درخواست پس‌ازفروش را مشخص کنید."}
            )
        attrs["field_name"] = named[0]
        attrs["parent_id"] = attrs[named[0]]
        return attrs


class AttachmentListQuerySerializer(RejectServerFieldsMixin, serializers.Serializer):
    """`?customer=5` (or lead=/invoice=/sales_document=/after_sales_request=) — exactly one."""

    customer = serializers.IntegerField(required=False, min_value=1)
    lead = serializers.IntegerField(required=False, min_value=1)
    invoice = serializers.IntegerField(required=False, min_value=1)
    sales_document = serializers.IntegerField(required=False, min_value=1)
    after_sales_request = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        named = [name for name in PARENT_FIELDS if attrs.get(name)]
        if len(named) != 1:
            raise serializers.ValidationError(
                {"parent": "دقیقاً یکی از مشتری، سرنخ، فاکتور، سند فروش یا درخواست پس‌ازفروش را مشخص کنید."}
            )
        attrs["field_name"] = named[0]
        attrs["parent_id"] = attrs[named[0]]
        return attrs


class AttachmentDetailSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    parent_field = serializers.SerializerMethodField()
    parent_id = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = (
            "id",
            "original_filename",
            "content_type",
            "size_bytes",
            "uploaded_at",
            "uploaded_by_name",
            "parent_field",
            "parent_id",
        )
        read_only_fields = fields

    def get_uploaded_by_name(self, instance) -> str:
        if not instance.uploaded_by:
            return ""
        return instance.uploaded_by.get_full_name() or instance.uploaded_by.username

    def get_parent_field(self, instance) -> str:
        for name in PARENT_FIELDS:
            if getattr(instance, f"{name}_id"):
                return name
        return ""

    def get_parent_id(self, instance) -> int | None:
        for name in PARENT_FIELDS:
            value = getattr(instance, f"{name}_id")
            if value:
                return value
        return None
