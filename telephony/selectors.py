from django.db.models import Q

from accounts.access import capabilities_for
from common.deployment.profile import feature_enabled
from telephony.models import Call


def calls_for(user):
    """Which calls a person may see (feature `telephony`).

    `calls.company` — every call. `calls.own` — the calls they handled (their
    extension rang or placed it). Nothing otherwise.
    """
    if not feature_enabled("telephony"):
        return Call.objects.none()
    capabilities = capabilities_for(user)
    if "calls.company" in capabilities:
        return Call.objects.all()
    if "calls.own" in capabilities:
        return Call.objects.filter(Q(user=user))
    return Call.objects.none()


def calls_about(user, person_type, person_id):
    return calls_for(user).filter(person_type=person_type, person_id=person_id)
