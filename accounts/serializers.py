from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import User
from accounts.services import change_user_role, create_crm_user, update_crm_user, update_own_profile
from common.serializers import RejectServerFieldsMixin


class LoginSerializer(RejectServerFieldsMixin, serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(request=self.context.get("request"), username=attrs["username"], password=attrs["password"])
        if user is None or not user.is_active:
            raise serializers.ValidationError("Invalid credentials.")
        attrs["user"] = user
        return attrs


class MeSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"username", "role", "is_active", "last_login", "created_at", "updated_at"}

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "role", "is_active", "last_login", "created_at", "updated_at"]
        read_only_fields = ["id", "username", "role", "is_active", "last_login", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        return update_own_profile(actor=self.context["request"].user, **validated_data)


class UserSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"role", "last_login", "created_at", "updated_at"}
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "password", "first_name", "last_name", "email", "phone", "role", "is_active", "last_login", "created_at", "updated_at"]
        read_only_fields = ["id", "role", "last_login", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        password = attrs.get("password")
        if password:
            candidate = User()
            for field in ("username", "first_name", "last_name", "email"):
                value = attrs.get(field, getattr(self.instance, field, "") if self.instance else "")
                setattr(candidate, field, value)
            try:
                validate_password(password, user=candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Password is required."})
        return create_crm_user(actor=self.context["request"].user, password=password, **validated_data)

    def update(self, instance, validated_data):
        return update_crm_user(actor=self.context["request"].user, target=instance, **validated_data)


class RoleChangeSerializer(RejectServerFieldsMixin, serializers.Serializer):
    role = serializers.ChoiceField(choices=User.Role.choices)

    def save(self, **kwargs):
        return change_user_role(actor=self.context["request"].user, target=self.context["target"], role=self.validated_data["role"])
