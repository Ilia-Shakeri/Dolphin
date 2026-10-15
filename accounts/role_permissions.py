"""Role-level permission defaults (2.40.48, owner decision 2026-10-14, BIZ-005).

The Platform Admin narrows — or widens — what one role grants for everyone who
holds it: «مدیر فروش هم دسترسی‌هاش باید از ادمین محدودتر باشه». It is the same
Read/Edit/Delete matrix the per-user screen edits, applied one level up:

* the baseline is the code's own role set (`accounts.access.ROLE_CAPABILITIES`),
  so «پیش‌فرض» on this screen always means what the release ships;
* a person's own overrides still apply on top, and their screen marks a row
  custom against the role's *configured* set;
* the protected capabilities (`users.*`, `audit.*` but `audit.team`) are never
  written here, and the Platform Admin's own role is not configurable.

Only the Platform Admin edits these (`accounts.services.USER_ADMINS`).
"""

from django.db import transaction

from accounts.access import (
    GRANTABLE_ONLY_TO,
    _is_protected_capability,
    base_role_capabilities,
    configured_role_capabilities,
    is_crm_identity,
)
from accounts.models import RoleCapabilityOverride, RolePermissionProfile, User
from accounts.module_permissions import (
    governed_capabilities,
    matrix_for_capabilities,
    overrides_needed_for_matrix,
    validate_matrix,
)
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.request_context import forget_request_memo

#: Each configurable profile: the role and workstream a person holding it has.
PROFILES = {
    "sales_agent": (User.Role.SALES_AGENT, User.Workstream.SALES),
    "after_sales_agent": (User.Role.SALES_AGENT, User.Workstream.AFTER_SALES),
    "sales_manager": (User.Role.SALES_MANAGER, User.Workstream.SALES),
    "company_it": (User.Role.COMPANY_IT, User.Workstream.SALES),
}
PROFILE_LABELS = dict(RolePermissionProfile.Key.choices)


def _require_admin(actor):
    if actor is None or not actor.is_active or not is_crm_identity(actor) or actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("فقط مدیر پلتفرم مجوزهای نقش‌ها را تغییر می‌دهد.")


def _profile(key):
    if key not in PROFILES:
        raise BusinessRuleError({"role": "این نقش قابل تنظیم نیست."})
    return PROFILES[key]


def role_permissions_for(*, actor, key):
    """The matrix screen's payload for one role: what it grants today, and
    which rows differ from what the release ships."""
    _require_admin(actor)
    role, workstream = _profile(key)
    held = configured_role_capabilities(role, workstream)
    matrix = matrix_for_capabilities(held, role=role, baseline=base_role_capabilities(role, workstream))
    return {
        "key": key,
        "label": PROFILE_LABELS[key],
        "role": role,
        "workstream": workstream,
        "matrix": matrix,
        "has_custom_permissions": any(row["is_custom"] for row in matrix.values()),
    }


def role_profiles_for(*, actor):
    """Every configurable role, for the list the admin picks from."""
    _require_admin(actor)
    customised = set(RoleCapabilityOverride.objects.values_list("profile__key", flat=True).distinct())
    return [{"key": key, "label": PROFILE_LABELS[key], "has_custom_permissions": key in customised} for key in PROFILES]


@transaction.atomic
def set_role_permission_overrides(*, actor, key, matrix):
    """Replace one role's configured changes with exactly what `matrix` needs."""
    _require_admin(actor)
    role, workstream = _profile(key)
    try:
        normalised = validate_matrix(matrix)
    except ValueError as exc:
        raise BusinessRuleError({"matrix": str(exc)}) from exc
    needed = overrides_needed_for_matrix(
        normalised, role=role, workstream=workstream, baseline=base_role_capabilities(role, workstream)
    )
    if not set(needed).issubset(governed_capabilities()) or any(_is_protected_capability(c) for c in needed):
        raise BusinessPermissionDenied("این مجوز از این صفحه قابل تغییر نیست.")
    for capability, granted in needed.items():
        allowed_roles = GRANTABLE_ONLY_TO.get(capability)
        if granted and allowed_roles is not None and role not in allowed_roles:
            raise BusinessRuleError({"matrix": "دیدن رویدادهای تیم فروش فقط به مدیر فروشگاه داده می‌شود."})
    profile, _ = RolePermissionProfile.objects.select_for_update().get_or_create(key=key)
    existing = {row.capability: row for row in RoleCapabilityOverride.objects.select_for_update().filter(profile=profile)}
    to_delete = [row.pk for capability, row in existing.items() if capability not in needed]
    to_create, to_update = [], []
    for capability, granted in needed.items():
        row = existing.get(capability)
        if row is None:
            to_create.append(RoleCapabilityOverride(profile=profile, capability=capability, granted=granted))
        elif row.granted != granted:
            row.granted = granted
            to_update.append(row)
    if to_delete:
        RoleCapabilityOverride.objects.filter(pk__in=to_delete).delete()
    if to_update:
        RoleCapabilityOverride.objects.bulk_update(to_update, ["granted", "updated_at"])
    if to_create:
        RoleCapabilityOverride.objects.bulk_create(to_create)
    forget_request_memo()
    if to_create or to_update or to_delete:
        profile.updated_by = actor
        profile.save(update_fields=["updated_by", "updated_at"])
        log_activity(
            actor=actor,
            operation="role.permissions_overridden",
            instance=profile,
            changes={
                "granted": sorted([c.capability for c in to_create if c.granted] + [r.capability for r in to_update if r.granted]),
                "revoked": sorted([c.capability for c in to_create if not c.granted] + [r.capability for r in to_update if not r.granted]),
                "cleared": sorted(capability for capability, row in existing.items() if row.pk in to_delete),
            },
        )
    return role_permissions_for(actor=actor, key=key)


@transaction.atomic
def reset_role_permissions(*, actor, key):
    """Back to what the release ships for this role."""
    _require_admin(actor)
    _profile(key)
    profile = RolePermissionProfile.objects.select_for_update().filter(key=key).first()
    if profile is not None:
        removed, _ = RoleCapabilityOverride.objects.filter(profile=profile).delete()
        forget_request_memo()
        if removed:
            profile.updated_by = actor
            profile.save(update_fields=["updated_by", "updated_at"])
            log_activity(actor=actor, operation="role.permissions_reset", instance=profile, changes={"removed_overrides": removed})
    return role_permissions_for(actor=actor, key=key)
