"""Telephony writes that are not the listener's: mapping extensions (2.22.0)
and asking for a call to be placed (2.23.0)."""

from django.db import IntegrityError, transaction
from django.utils import timezone

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


# --- click-to-call (2.23.0) ------------------------------------------------------

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def originating_extension(user):
    """The extension `user` places calls from: their active extension on an
    enabled Asterisk connection, or `None`. Asked by the profile header and
    the popup on every page load, so memoised per request."""
    from common.request_context import request_memo

    if not feature_enabled("telephony") or not getattr(user, "pk", None):
        return None
    memo = request_memo()
    key = ("telephony.originating_extension", user.pk)
    if memo is not None and key in memo:
        return memo[key]
    extension = (
        Extension.objects.filter(
            user=user, active=True, integration__enabled=True, integration__provider_key="asterisk"
        )
        .select_related("integration")
        .order_by("integration_id")
        .first()
    )
    if memo is not None:
        memo[key] = extension
    return extension


def can_originate(user):
    from accounts.access import capabilities_for

    return (
        feature_enabled("telephony")
        and "calls.originate" in capabilities_for(user)
        and originating_extension(user) is not None
    )


def dial_string(integration, number):
    """What the PBX dials for `number`, or a `BusinessRuleError`.

    An internal extension is dialled as typed. An Iranian number — in any
    shape a person or a CRM record holds it (`+98912…`, `0098…`, `912…`) —
    is dialled the way a phone in Iran dials it (`0912…`); any other
    international number as `00…`. The connection's outbound prefix goes in
    front of every outside number.
    """
    from common.phones import normalized_or_blank

    config = integration.config or {}
    text = str(number or "").translate(_PERSIAN_DIGITS).strip()
    compact = "".join(ch for ch in text if ch not in " -()\t")
    if not compact or not all(ch.isdigit() for ch in compact.lstrip("+")) or compact.count("+") > 1:
        raise BusinessRuleError({"number": "شمارهٔ تلفن معتبر نیست."})
    max_internal = int(config.get("internal_extension_max_length") or 5)
    if not compact.startswith("+") and len(compact) <= max_internal:
        return compact, ""
    e164 = normalized_or_blank(compact)
    if e164:
        dial = "0" + e164[3:]
    elif compact.startswith("+"):
        dial = "00" + compact[1:]
    else:
        dial = compact
    if not 3 <= len(dial) <= 24:
        raise BusinessRuleError({"number": "شمارهٔ تلفن معتبر نیست."})
    return f"{config.get('outbound_prefix') or ''}{dial}", e164


@transaction.atomic
def request_originate(*, actor, number, person_type="", person_id=None):
    """Queue a call from `actor`'s own extension to `number`.

    Refused, in Persian, when the actor may not place calls, has no
    extension, the PBX is not connected, the number is not a number, the
    person is outside their scope, or their previous call is still being
    placed.
    """
    from accounts.access import capabilities_for
    from integrations.matching import best_match
    from profiles.registry import resolve_person
    from telephony.models import OriginateRequest

    if not feature_enabled("telephony") or "calls.originate" not in capabilities_for(actor):
        raise BusinessPermissionDenied("برقراری تماس از دلفین برای شما مجاز نیست.")
    extension = originating_extension(actor)
    if extension is None:
        raise BusinessRuleError({"extension": "برای شما داخلی تلفن تعریف نشده است؛ از مدیر پلتفرم بخواهید آن را تعریف کند."})
    integration = extension.integration
    if integration.status != Integration.Status.OK:
        raise BusinessConflictError({"detail": "مرکز تلفن الان در دسترس نیست؛ کمی بعد دوباره امتحان کنید."})
    dial, e164 = dial_string(integration, number)
    if person_type or person_id:
        _adapter, person = resolve_person(actor, str(person_type or ""), person_id)
        if person is None:
            raise BusinessRuleError({"person": "این شخص در محدودهٔ دسترسی شما نیست."})
        person_type, person_id = str(person_type), person.pk
    else:
        match = best_match(e164 or dial) if (e164 or len(dial) > 5) else None
        person_type, person_id = (match.person_type, match.person_id) if match else ("", None)
    now = timezone.now()
    busy = OriginateRequest.objects.select_for_update().filter(
        user=actor,
        status__in=[OriginateRequest.Status.PENDING, OriginateRequest.Status.SENDING],
        created_at__gte=now - OriginateRequest.TTL,
    )
    if busy.exists():
        raise BusinessConflictError({"detail": "تماس قبلی شما هنوز در حال برقراری است."})
    request = OriginateRequest.objects.create(
        integration=integration, user=actor, extension=extension.number, dial=dial,
        external_number=e164, person_type=person_type, person_id=person_id,
    )
    log_activity(
        actor=actor, operation="call.originate_requested", instance=request,
        changes={"extension": extension.number, "person_type": person_type, "person_id": person_id},
    )
    return request


def expire_stale_originates(*, now=None):
    """Fail every request nobody claimed in time; returns how many."""
    from telephony.models import OriginateRequest

    now = now or timezone.now()
    return OriginateRequest.objects.filter(
        status__in=[OriginateRequest.Status.PENDING, OriginateRequest.Status.SENDING],
        created_at__lt=now - OriginateRequest.TTL,
    ).update(status=OriginateRequest.Status.FAILED, error="مرکز تلفن درخواست را در زمان مقرر نپذیرفت.")
