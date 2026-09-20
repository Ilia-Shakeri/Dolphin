from rest_framework import serializers

from common.models import (
    PANEL_FONT_FAMILIES,
    PANEL_FONT_SCALES,
    BrandSettings,
    UserDashboardLayout,
    UserPreference,
)


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


class UserDashboardLayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserDashboardLayout
        fields = ("hidden_widgets", "widget_order", "widget_sizes", "updated_at")
        read_only_fields = fields


class UserDashboardLayoutUpdateSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """All three fields optional and independent — see
    `common.dashboard_layout.update_user_dashboard_layout` for what
    "independent" means. Membership of the widget and size vocabularies is
    checked again in `common.dashboard_layout._clean_keys` and
    `_clean_sizes`, the same two-layer split every other update serializer
    in this module already follows.
    """

    hidden_widgets = serializers.ListField(child=serializers.CharField(), required=False)
    widget_order = serializers.ListField(child=serializers.CharField(), required=False)
    widget_sizes = serializers.DictField(child=serializers.CharField(), required=False)


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = ("font_family", "font_scale", "currency_unit", "theme", "updated_at")
        read_only_fields = fields


class UserPreferenceUpdateSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """Every field optional and independent, so the settings page can save
    one control at a time without re-sending the rest.

    `ChoiceField` against the model's own tuples rather than a free string.
    The chosen typeface ends up inside a `<style>` element on every page,
    and a value that reached that element unchecked would be a
    stylesheet-injection hole. Two guards stand between the request and the
    markup and both matter: this one refuses any value that is not a known
    token, and `common.preferences.preference_css` emits only the stack it
    looked up from `PANEL_FONT_FAMILY_STACKS` — never anything the client
    sent.
    """

    font_family = serializers.ChoiceField(
        choices=[value for value, _label, _stack in PANEL_FONT_FAMILIES], required=False,
    )
    font_scale = serializers.ChoiceField(
        choices=[value for value, _label, _size in PANEL_FONT_SCALES], required=False,
    )
    currency_unit = serializers.ChoiceField(choices=UserPreference.CurrencyUnit.values, required=False)
    theme = serializers.ChoiceField(choices=UserPreference.Theme.values, required=False)
