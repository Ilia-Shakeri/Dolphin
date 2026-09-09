from rest_framework import serializers

from common.models import BrandSettings, DashboardSettings


class RejectServerFieldsMixin:
    server_fields = set()
    always_forbidden_fields = {"id", "is_staff", "is_superuser", "groups", "user_permissions", "password_hash"}

    def validate(self, attrs):
        supplied = set(getattr(self, "initial_data", {}))
        forbidden = supplied & (set(self.server_fields) | self.always_forbidden_fields)
        if forbidden:
            raise serializers.ValidationError({name: "این فیلد توسط سامانه کنترل می‌شود." for name in sorted(forbidden)})
        unknown = supplied - set(self.fields)
        if unknown:
            raise serializers.ValidationError({name: "فیلد نامعتبر است." for name in sorted(unknown)})
        return super().validate(attrs)


class BrandSettingsSerializer(serializers.ModelSerializer):
    """Read shape for the settings page — never `logo_content` itself, only
    whether one exists, same reasoning as `AttachmentDetailSerializer` never
    including `Attachment.content`.
    """

    has_logo = serializers.BooleanField(read_only=True)

    class Meta:
        model = BrandSettings
        fields = ("display_name", "accent_color", "has_logo", "logo_original_filename", "updated_at")
        read_only_fields = fields


class BrandSettingsUpdateSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """Multipart input: every field optional and independent — see
    `common.branding.update_brand_settings` for what "independent" means.
    """

    display_name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    # Shape checked again in `common.branding._clean_accent_color` — this is
    # the same "wrong type/length rejected here, wrong shape rejected there"
    # split every other field in this serializer already follows.
    accent_color = serializers.CharField(required=False, allow_blank=True, max_length=7)
    # Plain FileField, not ImageField: DRF's ImageField needs Pillow to open
    # and validate the file, and this codebase has never depended on Pillow —
    # `attachments.services._sniff_content_type` reads the same four magic
    # bytes by hand instead, for the same reason (see that function's own
    # docstring). `common.branding.update_brand_settings` does the same sniff.
    logo = serializers.FileField(required=False)
    remove_logo = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("remove_logo") and attrs.get("logo") is not None:
            raise serializers.ValidationError({"logo": "حذف و جایگزینی لوگو هم‌زمان ممکن نیست."})
        return attrs


class DashboardSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardSettings
        fields = ("hidden_widgets", "widget_order", "updated_at")
        read_only_fields = fields


class DashboardSettingsUpdateSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """Both fields optional and independent — see
    `common.dashboard_layout.update_dashboard_settings` for what
    "independent" means. Shape/membership checked again in
    `common.dashboard_layout._clean_keys`, the same two-layer split every
    other update serializer in this module already follows.
    """

    hidden_widgets = serializers.ListField(child=serializers.CharField(), required=False)
    widget_order = serializers.ListField(child=serializers.CharField(), required=False)
