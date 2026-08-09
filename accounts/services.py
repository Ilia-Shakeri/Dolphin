from django.db import IntegrityError, transaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.access import crm_identities, is_crm_account, is_crm_identity
from accounts.models import User
from accounts.platform_admin_guard import lock_platform_admin_guard
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError


ROLE_RANK = {
    User.Role.SALES_AGENT: 1,
    User.Role.SALES_MANAGER: 2,
    User.Role.COMPANY_IT: 3,
    User.Role.PLATFORM_ADMIN: 4,
}
USER_ADMINS = {User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}
USER_MUTABLE_FIELDS = {"username", "first_name", "last_name", "email", "phone", "is_active"}
PROFILE_MUTABLE_FIELDS = {"first_name", "last_name", "email", "phone"}


def _protect_last_active_platform_admin(*, target, next_role=None, next_is_active=None):
    if target.role != User.Role.PLATFORM_ADMIN or not target.is_active:
        return
    effective_role = target.role if next_role is None else next_role
    effective_is_active = target.is_active if next_is_active is None else next_is_active
    if effective_role == User.Role.PLATFORM_ADMIN and effective_is_active:
        return
    if not crm_identities(
        User.objects.filter(
            role=User.Role.PLATFORM_ADMIN,
            is_active=True,
        ).exclude(pk=target.pk)
    ).exists():
        field = "role" if effective_role != User.Role.PLATFORM_ADMIN else "is_active"
        raise BusinessConflictError({field: "At least one active Platform Admin must remain."})


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
    if locked_actor is None or not is_crm_identity(locked_actor) or locked_actor.role not in USER_ADMINS:
        raise BusinessPermissionDenied("User administration is not allowed.")
    if target is not None and locked_target is None:
        raise BusinessRuleError({"user": "User does not exist."})
    if locked_target is not None and not is_crm_account(locked_target):
        raise BusinessPermissionDenied("User administration is not allowed.")
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
        raise BusinessConflictError({"username": "Username already exists."}) from exc
    log_activity(
        actor=actor,
        operation="user.created",
        instance=target,
        changes={"fields": sorted(data), "password_set": True},
    )
    return target


@transaction.atomic
def update_crm_user(*, actor, target, **changes):
    lock_platform_admin_guard()
    actor, target = _locked_users(actor, target)
    password = changes.pop("password", None)
    unknown = set(changes) - USER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "Field cannot be changed." for field in sorted(unknown)})
    _protect_last_active_platform_admin(
        target=target,
        next_is_active=changes.get("is_active", target.is_active),
    )
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
            raise BusinessConflictError({"username": "Username already exists."}) from exc
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
    if actor is None or not is_crm_identity(actor):
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
    lock_platform_admin_guard()
    actor, target = _locked_users(actor, target)
    actor_role_at_action = actor.role
    if role not in ROLE_RANK:
        raise BusinessRuleError({"role": "Unknown CRM role."})
    if actor.role == User.Role.COMPANY_IT:
        if target.role == User.Role.PLATFORM_ADMIN or ROLE_RANK[role] > ROLE_RANK[User.Role.COMPANY_IT]:
            raise BusinessPermissionDenied("Company IT cannot manage Platform Admin access.")
    elif actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("Role change is not allowed.")
    _protect_last_active_platform_admin(target=target, next_role=role)
    previous = target.role
    if previous == role:
        raise BusinessConflictError({"role": "User already has this role."})
    target.role = role
    target.save(update_fields=["role", "updated_at"])
    log_activity(
        actor=actor,
        operation="user.role_changed",
        instance=target,
        changes={"from": previous, "to": role},
        actor_role_snapshot=actor_role_at_action,
        object_role_snapshot=previous,
    )
    return target
