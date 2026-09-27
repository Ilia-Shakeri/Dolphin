"""Telephony writes that are not the listener's (2.22.0): mapping extensions."""

from django.db import IntegrityError, transaction

from accounts.access import crm_identities
from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from integrations.models import Integration
from telephony.models import Extension


def _require_admin(actor):
    if not feature_enabled("telephony"):
        raise BusinessPermissionDenied("تلفن در این استقرار فعال نیست.")
    if actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("تعریف داخلی‌ها فقط برای مدیر پلتفرم مجاز است.")


def _clean(integration_id, number, user_id):
    integration = Integration.objects.filter(pk=integration_id, provider_key="asterisk").first()
    if integration is None:
        raise BusinessRuleError({"integration": "مرکز تلفن را انتخاب کنید."})
    number = str(number or "").strip()
    if not number or not all(ch.isdigit() or ch in "*#" for ch in number) or len(number) > 20:
        raise BusinessRuleError({"number": "شمارهٔ داخلی فقط رقم است."})
    user = None
    if user_id:
        user = crm_identities(User.objects.filter(pk=user_id, is_active=True)).first()
        if user is None:
            raise BusinessRuleError({"user": "کاربر باید یک کاربر فعال سامانه باشد."})
    return integration, number, user


@transaction.atomic
def save_extension(*, actor, extension=None, integration_id, number, user_id=None, label="", active=True):
    _require_admin(actor)
    integration, number, user = _clean(integration_id, number, user_id)
    row = extension or Extension()
    row.integration, row.number, row.user = integration, number, user
    row.label, row.active = (label or "").strip()[:120], bool(active)
    try:
        with transaction.atomic():
            row.save()
    except IntegrityError as error:
        raise BusinessConflictError(
            {"number": "این داخلی قبلاً تعریف شده یا این کاربر داخلی فعال دیگری دارد."}
        ) from error
    log_activity(
        actor=actor, operation="extension.saved", instance=row,
        changes={"fields": ["number", "user", "active"]},
    )
    return row


@transaction.atomic
def delete_extension(*, actor, extension):
    _require_admin(actor)
    log_activity(actor=actor, operation="extension.deleted", instance=extension, changes={})
    extension.delete()
