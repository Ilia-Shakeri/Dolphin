import re

from django.db import IntegrityError, transaction
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.access import (
    PROTECTED_CAPABILITY_PREFIXES,
    assignable_roles,
    crm_identities,
    is_crm_account,
    is_crm_identity,
)
from accounts.models import User, UserCapabilityOverride
from accounts.module_permissions import (
    effective_matrix_for_user,
    governed_capabilities,
    overrides_needed_for_matrix,
    validate_matrix,
)
from accounts.platform_admin_guard import lock_platform_admin_guard
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError


#: Django's own `fa` translation catalog covers every stock password
#: validator message except `MinimumLengthValidator`'s, so that one is
#: translated by hand here rather than left to leak English into the panel.
_MIN_LENGTH_MESSAGE = re.compile(
    r"^This password is too short\. It must contain at least (\d+) characters?\.$"
)


def persian_password_messages(exc):
    translated = []
    for message in exc.messages:
        match = _MIN_LENGTH_MESSAGE.match(message)
        if match:
            translated.append(f"رمز عبور بسیار کوتاه است. باید حداقل {match.group(1)} نویسه داشته باشد.")
        else:
            translated.append(message)
    return translated


ROLE_RANK = {
    User.Role.SALES_AGENT: 1,
    User.Role.SALES_MANAGER: 2,
    User.Role.COMPANY_IT: 3,
    User.Role.PLATFORM_ADMIN: 4,
}
# Only `platform_admin` may administer CRM users. This service-layer gate is the
# authoritative boundary: it holds for every caller, including management
# commands and future code paths that do not pass through the REST permission
# class. The per-role target scoping further down stays in place so that a
# future deployment-profile grant remains correctly bounded.
USER_ADMINS = {User.Role.PLATFORM_ADMIN}
USER_MUTABLE_FIELDS = {"username", "first_name", "last_name", "email", "phone", "workstream", "is_active"}
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
        raise BusinessConflictError({field: "حداقل یک مدیر پلتفرم فعال باید باقی بماند."})


def _locked_users(actor, target=None, *, for_update=True):
    identifiers = {actor.pk}
    if target is not None:
        identifiers.add(target.pk)
    base_queryset = User.objects.select_for_update() if for_update else User.objects
    users = {
        user.pk: user
        for user in base_queryset.filter(pk__in=identifiers).order_by("pk")
    }
    locked_actor = users.get(actor.pk)
    locked_target = users.get(target.pk) if target is not None else None
    if locked_actor is None or not is_crm_identity(locked_actor) or locked_actor.role not in USER_ADMINS:
        raise BusinessPermissionDenied("مدیریت کاربران مجاز نیست.")
    if target is not None and locked_target is None:
        raise BusinessRuleError({"user": "کاربر وجود ندارد."})
    if locked_target is not None and not is_crm_account(locked_target):
        raise BusinessPermissionDenied("مدیریت کاربران مجاز نیست.")
    if locked_actor.role == User.Role.SALES_MANAGER and locked_target is not None and locked_target.role != User.Role.SALES_AGENT:
        raise BusinessPermissionDenied("مدیر فروشگاه فقط می‌تواند حساب‌های بازاریاب را مدیریت کند.")
    if locked_actor.role == User.Role.COMPANY_IT and locked_target is not None and locked_target.role == User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("مدیر فنی مشتری نمی‌تواند دسترسی مدیر پلتفرم را مدیریت کند.")
    return locked_actor, locked_target


def _validate_creatable_role(actor, role):
    """Refuse a role the Create User form should never have offered `actor`.

    Reuses `assignable_roles` rather than restating its rules — the role a
    Platform Admin may hand a *new* account is exactly the role they may move
    an *existing* one to (feature-gated `company_it`, `platform_admin` only
    from another `platform_admin`), so the two pickers can never disagree
    about what is on offer.
    """
    if role not in ROLE_RANK:
        raise BusinessRuleError({"role": "نقش نامعتبر است."})
    if role not in {value for value, _ in assignable_roles(actor)}:
        raise BusinessPermissionDenied("این نقش برای شما در دسترس نیست.")


@transaction.atomic
def create_crm_user(*, actor, password, role, **data):
    actor, _ = _locked_users(actor)
    unknown = set(data) - USER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تنظیم نیست." for field in sorted(unknown)})
    _validate_creatable_role(actor, role)
    workstream = data.get("workstream", User.Workstream.SALES)
    if workstream not in User.Workstream.values:
        raise BusinessRuleError({"workstream": "جریان کاری نامعتبر است."})
    if role != User.Role.SALES_AGENT and workstream != User.Workstream.SALES:
        raise BusinessRuleError({"workstream": "فقط حساب‌های بازاریاب می‌توانند از جریان کاری خدمات پس از فروش استفاده کنند."})
    try:
        validate_password(password, user=User(role=role, **data))
    except DjangoValidationError as exc:
        raise BusinessRuleError({"password": persian_password_messages(exc)}) from exc
    try:
        target = User.objects.create_user(password=password, role=role, **data)
    except IntegrityError as exc:
        raise BusinessConflictError({"username": "این نام کاربری قبلاً استفاده شده است."}) from exc
    log_activity(
        actor=actor,
        operation="user.created",
        instance=target,
        changes={"fields": sorted({*data, "role"}), "password_set": True, "role": role},
    )
    return target


@transaction.atomic
def update_crm_user(*, actor, target, **changes):
    lock_platform_admin_guard()
    actor, target = _locked_users(actor, target)
    password = changes.pop("password", None)
    unknown = set(changes) - USER_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
    if "workstream" in changes:
        if changes["workstream"] not in User.Workstream.values:
            raise BusinessRuleError({"workstream": "جریان کاری نامعتبر است."})
        if target.role != User.Role.SALES_AGENT and changes["workstream"] != User.Workstream.SALES:
            raise BusinessRuleError({"workstream": "فقط حساب‌های بازاریاب می‌توانند از جریان کاری خدمات پس از فروش استفاده کنند."})
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
            raise BusinessRuleError({"password": persian_password_messages(exc)}) from exc
        target.set_password(password)
        changed_fields.append("password")
    if changed_fields:
        try:
            target.save(update_fields=[*changed_fields, "updated_at"])
        except IntegrityError as exc:
            raise BusinessConflictError({"username": "این نام کاربری قبلاً استفاده شده است."}) from exc
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
        raise BusinessPermissionDenied("کاربر فعال سامانه لازم است.")
    unknown = set(changes) - PROFILE_MUTABLE_FIELDS
    if unknown:
        raise BusinessRuleError({field: "این فیلد قابل تغییر نیست." for field in sorted(unknown)})
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
def change_user_role(*, actor, target, role, keep_custom_permissions=True):
    lock_platform_admin_guard()
    actor, target = _locked_users(actor, target)
    actor_role_at_action = actor.role
    if role not in ROLE_RANK:
        raise BusinessRuleError({"role": "نقش نامعتبر است."})
    if role == User.Role.COMPANY_IT and not feature_enabled("internal_it_role"):
        # Feature availability is checked before role permission on purpose: a
        # deployment that does not run this role must refuse it even for a
        # Platform Admin, and refuse it at the API rather than only hiding the
        # option in the page.
        raise BusinessPermissionDenied("این استقرار از نقش مدیر فنی مشتری استفاده نمی‌کند.")
    if actor.role == User.Role.SALES_MANAGER:
        raise BusinessPermissionDenied("مدیر فروشگاه نمی‌تواند نقش کاربران را تغییر دهد.")
    if actor.role == User.Role.COMPANY_IT:
        if target.role == User.Role.PLATFORM_ADMIN or ROLE_RANK[role] > ROLE_RANK[User.Role.COMPANY_IT]:
            raise BusinessPermissionDenied("مدیر فنی مشتری نمی‌تواند دسترسی مدیر پلتفرم را مدیریت کند.")
    elif actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("تغییر نقش مجاز نیست.")
    _protect_last_active_platform_admin(target=target, next_role=role)
    previous = target.role
    if previous == role:
        raise BusinessConflictError({"role": "کاربر هم‌اکنون همین نقش را دارد."})
    target.role = role
    update_fields = ["role", "updated_at"]
    if role != User.Role.SALES_AGENT and target.workstream != User.Workstream.SALES:
        target.workstream = User.Workstream.SALES
        update_fields.append("workstream")
    target.save(update_fields=update_fields)
    # A role change never silently destroys a customised permission matrix.
    # `keep_custom_permissions` defaults to True — preserving is the choice
    # that cannot surprise anyone — and the caller only sends False after the
    # admin has explicitly said, in the role-change dialog, to reset instead.
    if not keep_custom_permissions:
        removed, _ = UserCapabilityOverride.objects.filter(user=target).delete()
        if removed:
            log_activity(
                actor=actor,
                operation="user.permissions_reset",
                instance=target,
                changes={"reason": "role_changed", "removed_overrides": removed},
            )
    log_activity(
        actor=actor,
        operation="user.role_changed",
        instance=target,
        changes={"from": previous, "to": role},
        actor_role_snapshot=actor_role_at_action,
        object_role_snapshot=previous,
    )
    return target


def user_permissions_for(*, actor, target):
    """The Read/Edit matrix screen's whole payload for one user: their role,
    their effective matrix, and whether any row is a personal override.

    Read-only, so `target` is fetched without `_locked_users`'s row lock —
    the same admin-only authorization applies, just without holding a lock a
    GET has no reason to take.
    """
    actor, target = _locked_users(actor, target, for_update=False)
    matrix = effective_matrix_for_user(target)
    return {
        "role": target.role,
        "workstream": target.workstream,
        "matrix": matrix,
        "has_custom_permissions": any(row["is_custom"] for row in matrix.values()),
    }


@transaction.atomic
def set_user_permission_overrides(*, actor, target, matrix):
    """Replace `target`'s personal overrides with exactly what `matrix` needs.

    Only ever writes a row for a capability that actually disagrees with the
    role's own default (`overrides_needed_for_matrix`), and removes any row
    that no longer needs to exist — resaving a matrix that matches the role
    exactly is indistinguishable from `reset_user_permissions`, on purpose.
    """
    actor, target = _locked_users(actor, target)
    try:
        normalised = validate_matrix(matrix)
    except ValueError as exc:
        raise BusinessRuleError({"matrix": str(exc)}) from exc
    needed = overrides_needed_for_matrix(normalised, role=target.role, workstream=target.workstream)
    if not set(needed).issubset(governed_capabilities()) or any(
        capability.startswith(PROTECTED_CAPABILITY_PREFIXES) for capability in needed
    ):
        # Unreachable through `accounts.module_permissions.MODULES` as written
        # — kept as a hard stop rather than a comment, so a future module
        # naming a `users.*`/`audit.*` capability fails loudly here instead of
        # quietly granting it.
        raise BusinessPermissionDenied("این مجوز از این صفحه قابل تغییر نیست.")

    existing = {
        row.capability: row
        for row in UserCapabilityOverride.objects.select_for_update().filter(user=target)
    }
    to_create, to_update, to_delete = [], [], []
    for capability, row in existing.items():
        if capability not in needed:
            to_delete.append(row.pk)
    for capability, granted in needed.items():
        row = existing.get(capability)
        if row is None:
            to_create.append(UserCapabilityOverride(user=target, capability=capability, granted=granted))
        elif row.granted != granted:
            row.granted = granted
            to_update.append(row)

    if to_delete:
        UserCapabilityOverride.objects.filter(pk__in=to_delete).delete()
    if to_update:
        UserCapabilityOverride.objects.bulk_update(to_update, ["granted", "updated_at"])
    if to_create:
        UserCapabilityOverride.objects.bulk_create(to_create)

    if to_create or to_update or to_delete:
        log_activity(
            actor=actor,
            operation="user.permissions_overridden",
            instance=target,
            changes={
                "granted": sorted(c.capability for c in to_create if c.granted) + sorted(r.capability for r in to_update if r.granted),
                "revoked": sorted(c.capability for c in to_create if not c.granted) + sorted(r.capability for r in to_update if not r.granted),
                "cleared": sorted(capability for capability, row in existing.items() if row.pk in to_delete),
            },
        )
    return user_permissions_for(actor=actor, target=target)


@transaction.atomic
def reset_user_permissions(*, actor, target):
    """Delete every personal override `target` has, restoring their role's
    plain defaults. Never touches the role itself, and never touches any
    other user — see the model docstring for why absence of a row already
    means "use the role default".
    """
    actor, target = _locked_users(actor, target)
    removed, _ = UserCapabilityOverride.objects.filter(user=target).delete()
    if removed:
        log_activity(
            actor=actor,
            operation="user.permissions_reset",
            instance=target,
            changes={"reason": "manual", "removed_overrides": removed},
        )
    return user_permissions_for(actor=actor, target=target)
