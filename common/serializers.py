from rest_framework import serializers


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
