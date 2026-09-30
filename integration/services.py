"""PRELIMINARY, UNCOMMITTED — see integration/apps.py.

Pairing settings, outbox enqueueing, and hand-off user resolution — the
CRM-side mirror of Dolphin Accounting's own `integration/services.py`.
"""

import unicodedata
import uuid

from django.db import transaction
from django.utils import timezone

from accounts.access import is_crm_identity
from accounts.models import User
from common.exceptions import BusinessRuleError
from integration.models import OutboundEvent, PairingSettings

SECRET_MAX_LENGTH = 255


def get_pairing_settings():
    row, _ = PairingSettings.objects.get_or_create(singleton=PairingSettings.SINGLETON)
    return row


@transaction.atomic
def update_pairing_settings(*, actor, **changes):
    row = PairingSettings.objects.select_for_update().get_or_create(singleton=PairingSettings.SINGLETON)[0]
    if "shared_secret" in changes:
        secret = unicodedata.normalize("NFKC", str(changes["shared_secret"] or "")).strip()
        if len(secret) > SECRET_MAX_LENGTH:
            raise BusinessRuleError({"shared_secret": f"حداکثر {SECRET_MAX_LENGTH} نویسه مجاز است."})
        row.shared_secret = secret
    if "is_enabled" in changes:
        row.is_enabled = bool(changes["is_enabled"])
    if row.is_enabled and not row.shared_secret:
        raise BusinessRuleError({"shared_secret": "برای فعال‌سازی، کلید مشترک الزامی است."})
    row.updated_by = actor
    row.save()
    return row


def enqueue_event(*, event_type, payload, occurred_at=None):
    """Append one outbox row. **Must always be called from inside the same
    `@transaction.atomic` block as the real event it describes** — that is
    the entire durability guarantee this mechanism provides (see
    integration/models.py's OutboundEvent docstring). Silently does nothing
    when pairing is not configured/enabled, so every call site stays a
    no-op on a deployment that never set this up — genuinely additive.
    """
    pairing = get_pairing_settings()
    if not pairing.is_enabled or not pairing.shared_secret:
        return None
    return OutboundEvent.objects.create(
        idempotency_key=str(uuid.uuid4()),
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_at or timezone.now(),
    )


@transaction.atomic
def provision_or_get_handoff_user(*, username, email=""):
    """Find-or-create the local CRM account a verified hand-off token (minted
    by Dolphin Accounting) maps to. Mirrors that repo's own function.

    **Conservative default, flagged for review**: role defaults to
    `sales_agent` — the narrowest real operational role this codebase has —
    rather than anything with elevated capability, for the same reasoning
    Accounting's own HANDOFF_DEFAULT_ROLE comment gives.
    """
    if not username:
        raise BusinessRuleError({"username": "شناسهٔ کاربر در توکن ورود یکپارچه یافت نشد."})
    local_username = f"accounting:{username}"[:150]
    user, created = User.objects.get_or_create(
        username=local_username,
        defaults={"email": email, "role": User.Role.SALES_AGENT, "is_active": True},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    if not is_crm_identity(user):
        raise BusinessRuleError({"username": "این حساب دیگر یک هویت معتبر CRM نیست."})
    return user
