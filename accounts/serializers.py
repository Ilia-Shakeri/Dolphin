from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.access import capabilities_for, is_crm_identity
from accounts.models import User
from accounts.services import change_user_role, create_crm_user, update_crm_user, update_own_profile
from common.serializers import RejectServerFieldsMixin


class LoginSerializer(RejectServerFieldsMixin, serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = authenticate(request=self.context.get("request"), username=attrs["username"], password=attrs["password"])
        if not is_crm_identity(user):
            raise serializers.ValidationError("Invalid credentials.")
        attrs["user"] = user
        return attrs


class MeSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    server_fields = {"username", "role", "workstream", "capabilities", "is_active", "last_login", "created_at", "updated_at"}
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "phone", "role", "workstream", "capabilities", "is_active", "last_login", "created_at", "updated_at"]
        read_only_fields = ["id", "username", "role", "workstream", "capabilities", "is_active", "last_login", "created_at", "updated_at"]

    def get_capabilities(self, obj) -> list[str]:
        return sorted(capabilities_for(obj))

    def update(self, instance, validated_data):
        return update_own_profile(actor=self.context["request"].user, **validated_data)


class UserSerializer(RejectServerFieldsMixin, serializers.ModelSerializer):
    """Create and edit a CRM account.

    A password is set **once, when the account is created**, and this API offers
    no way to change one afterwards: no interface exposes it for any role, and
    accepting it here would be a control that exists only over the wire.
    Recovering a forgotten password is a host operation
    (`manage.py changepassword`), deliberately outside the application.
    """

    server_fields = {"role", "last_login", "created_at", "updated_at"}
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ["id", "username", "password", "first_name", "last_name", "email", "phone", "role", "workstream", "is_active", "last_login", "created_at", "updated_at"]
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
        if "password" in validated_data:
            raise serializers.ValidationError(
                {"password": "A password cannot be changed through this API."}
            )
        return update_crm_user(actor=self.context["request"].user, target=instance, **validated_data)


class SessionSerializer(serializers.Serializer):
    """One active session, identified by a reference and never by its key.

    `reference` is the keyed digest from `accounts.sessions`; it identifies the
    row for revocation and can neither be reversed into the session key nor used
    to authenticate anything.
    """

    reference = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
    is_current = serializers.BooleanField(read_only=True)
    user_agent = serializers.CharField(read_only=True, allow_blank=True, default="")
    ip_address = serializers.CharField(read_only=True, allow_blank=True, default="")
    started_at = serializers.CharField(read_only=True, allow_blank=True, default="")


class SessionListSerializer(serializers.Serializer):
    count = serializers.IntegerField(read_only=True)
    results = SessionSerializer(many=True, read_only=True)


class SessionRevokeSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """Ends one session when given its reference, or all of them when not."""

    reference = serializers.CharField(
        max_length=64, required=False, allow_blank=True, trim_whitespace=True
    )


class SessionRevokeResultSerializer(serializers.Serializer):
    ended = serializers.IntegerField(read_only=True)


class RoleChangeSerializer(RejectServerFieldsMixin, serializers.Serializer):
    role = serializers.ChoiceField(choices=User.Role.choices)

    def save(self, **kwargs):
        return change_user_role(actor=self.context["request"].user, target=self.context["target"], role=self.validated_data["role"])
