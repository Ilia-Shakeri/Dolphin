from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.access import capabilities_for, is_crm_identity
from accounts.models import User
from accounts.services import (
    change_user_role,
    create_crm_user,
    persian_password_messages,
    update_crm_user,
    update_own_profile,
)
from common.serializers import RejectServerFieldsMixin


class LoginSerializer(RejectServerFieldsMixin, serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = authenticate(request=self.context.get("request"), username=attrs["username"], password=attrs["password"])
        if not is_crm_identity(user):
            raise serializers.ValidationError("نام کاربری یا رمز عبور نادرست است.")
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

    #: `role` is deliberately absent here: unlike a real server-controlled
    #: field (`last_login`, the timestamps), it is a legitimate creation
    #: input now — required on `POST`, refused again on update by
    #: `update_crm_user` itself (`role` is not in `USER_MUTABLE_FIELDS`), so a
    #: role change still only ever happens through `change-role`'s own rules.
    server_fields = {"last_login", "created_at", "updated_at"}
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    role = serializers.ChoiceField(choices=User.Role.choices)
    has_custom_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "password", "first_name", "last_name", "email", "phone", "role", "workstream", "is_active", "has_custom_permissions", "last_login", "created_at", "updated_at"]
        read_only_fields = ["id", "last_login", "created_at", "updated_at"]

    def get_has_custom_permissions(self, obj) -> bool:
        # `UserViewSet.get_queryset` annotates this for list/retrieve so a
        # page of users costs one subquery, not one per row. A freshly
        # created instance (never queried back) has no overrides yet by
        # construction, so the fallback only ever runs for that one case.
        annotated = getattr(obj, "_has_capability_overrides", None)
        if annotated is not None:
            return annotated
        if obj.pk is None:
            return False
        return obj.capability_overrides.exists()

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
                raise serializers.ValidationError({"password": persian_password_messages(exc)}) from exc
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "رمز عبور الزامی است."})
        return create_crm_user(actor=self.context["request"].user, password=password, **validated_data)

    def update(self, instance, validated_data):
        if "password" in validated_data:
            raise serializers.ValidationError(
                {"password": "رمز عبور از این مسیر قابل تغییر نیست."}
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
    #: Whether to keep the target's personal permission overrides, if any,
    #: after the role changes. Defaults to keeping them — the safe choice
    #: that cannot destroy a customisation nobody asked to discard — so an
    #: older client that never sends this field behaves exactly as one that
    #: explicitly chose "keep".
    keep_custom_permissions = serializers.BooleanField(required=False, default=True)

    def save(self, **kwargs):
        return change_user_role(
            actor=self.context["request"].user,
            target=self.context["target"],
            role=self.validated_data["role"],
            keep_custom_permissions=self.validated_data["keep_custom_permissions"],
        )


class PermissionMatrixEntrySerializer(serializers.Serializer):
    read = serializers.BooleanField()
    write = serializers.BooleanField(required=False, default=False)
    is_custom = serializers.BooleanField(read_only=True, required=False)


class UserPermissionsSerializer(serializers.Serializer):
    """One user's Read/Edit matrix screen: role, effective matrix, and
    whether any row is a personal override — everything the permissions
    modal needs in one request, and everything `set_user_permission_overrides`
    hands back after a save so the screen never has to re-fetch to confirm.
    """

    role = serializers.ChoiceField(choices=User.Role.choices, read_only=True)
    workstream = serializers.ChoiceField(choices=User.Workstream.choices, read_only=True)
    matrix = serializers.DictField(child=PermissionMatrixEntrySerializer(), read_only=True)
    has_custom_permissions = serializers.BooleanField(read_only=True)


class PermissionMatrixUpdateSerializer(RejectServerFieldsMixin, serializers.Serializer):
    """The write side: a module key mapped to the read/write flags the admin
    wants for one user. Shape checking only — `set_user_permission_overrides`
    (via `accounts.module_permissions.validate_matrix`) is what actually knows
    which module keys exist and enforces edit-implies-read, so the two can
    never validate a matrix differently.
    """

    matrix = serializers.DictField(child=serializers.DictField())
