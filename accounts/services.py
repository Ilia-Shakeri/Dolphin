from django.db import IntegrityError, transaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.models import User
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied, BusinessRuleError


ROLE_RANK = {
    User.Role.SALES_AGENT: 1,
    User.Role.SALES_MANAGER: 2,
    User.Role.COMPANY_IT: 3,
    User.Role.PLATFORM_ADMIN: 4,
}
USER_ADMINS = {User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
USER_MUTABLE_FIELDS = {"username", "first_name", "last_name", "email", "phone", "is_active"}
PROFILE_MUTABLE_FIELDS = {"first_name", "last_name", "email", "phone"}


def _locked_users(actor, target=None):
    identifiers = {actor.pk}
    if target is not None:
        identifiers.add(target.pk)
    users = {
        user.pk: user
        for user in User.objects.select_for_update().filter(pk__in=identifiers).order_by("pk")
    }
    locked_actor = users.get(actor.pk)
    locked_target = users.get(target.pk) if target is not None else None
    if locked_actor is None or not locked_actor.is_active or locked_actor.role not in USER_ADMINS:
        raise BusinessPermissionDenied("User administration is not allowed.")
    if target is not None and locked_target is None:
        raise BusinessRuleError({"user": "User does not exist."})
    if locked_actor.role == User.Role.COMPANY_IT and locked_target is not None and locked_target.role == User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("Company IT cannot manage Platform Admin access.")
    return locked_actor, locked_target


@transaction.atomic
def create_crm_user(*, actor, password, **data):
    actor, _ = _locked_users(actor)
    unknown = set(data) - USER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be set." for field in sorted(unknown)})
    try:
        validate_password(password, user=User(**data))
    except DjangoValidationError as exc:
        raise BusinessRuleError({"password": list(exc.messages)}) from exc
    try:
        target = User.objects.create_user(password=password, **data)
    except IntegrityError as exc:
        raise BusinessRuleError({"username": "Username already exists."}) from exc
    log_activity(
        actor=actor,
        operation="user.created",
        instance=target,
        changes={"fields": sorted(data), "password_set": True},
    )
    return target


@transaction.atomic
def update_crm_user(*, actor, target, **changes):
    actor, target = _locked_users(actor, target)
    password = changes.pop("password", None)
    unknown = set(changes) - USER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    changed_fields = []
    for field, value in changes.items():
        if getattr(target, field) != value:
            setattr(target, field, value)
            changed_fields.append(field)
    if password:
        try:
            validate_password(password, user=target)
        except DjangoValidationError as exc:
            raise BusinessRuleError({"password": list(exc.messages)}) from exc
        target.set_password(password)
        changed_fields.append("password")
    if changed_fields:
        try:
            target.save(update_fields=[*changed_fields, "updated_at"])
        except IntegrityError as exc:
            raise BusinessRuleError({"username": "Username already exists."}) from exc
        log_activity(
            actor=actor,
            operation="user.updated",
            instance=target,
            changes={"fields": sorted(field for field in changed_fields if field != "password"), "password_changed": "password" in changed_fields},
        )
    return target


@transaction.atomic
def update_own_profile(*, actor, **changes):
    actor = User.objects.select_for_update().filter(pk=actor.pk, is_active=True, role__in=ROLE_RANK).first()
    if actor is None:
        raise BusinessPermissionDenied("Active CRM user is required.")
    unknown = set(changes) - PROFILE_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    changed_fields = []
    for field, value in changes.items():
        if getattr(actor, field) != value:
            setattr(actor, field, value)
            changed_fields.append(field)
    if changed_fields:
        actor.save(update_fields=[*changed_fields, "updated_at"])
        log_activity(
            actor=actor,
            operation="user.profile_updated",
            instance=actor,
            changes={"fields": sorted(changed_fields)},
        )
    return actor


@transaction.atomic
def change_user_role(*, actor, target, role):
    actor, target = _locked_users(actor, target)
    if role not in ROLE_RANK:
        raise BusinessRuleError({"role": "Unknown CRM role."})
    if actor.role == User.Role.COMPANY_IT:
        if target.role == User.Role.PLATFORM_ADMIN or ROLE_RANK[role] > ROLE_RANK[User.Role.COMPANY_IT]:
            raise BusinessPermissionDenied("Company IT cannot manage Platform Admin access.")
    elif actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("Role change is not allowed.")
    previous = target.role
    target.role = role
    target.save(update_fields=["role", "updated_at"])
    log_activity(actor=actor, operation="user.role_changed", instance=target, changes={"from": previous, "to": role})
    return target
