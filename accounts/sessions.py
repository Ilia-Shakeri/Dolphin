"""Listing and revoking a user's active sessions.

Requirement 1.8. Deliberately built on Django's own session store rather than a
new model: the session table already *is* the record of who is signed in, and a
parallel table would be a second source of truth that could disagree with the
one that actually grants access.

Revoking deletes the session row, so the next request from that browser is
unauthenticated. It does not disable the account — that is a separate control on
the same page, and conflating them would make "sign this person out" silently
mean "lock them out".
"""

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.services import USER_ADMINS
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied


#: Sessions scanned per request. Every row must be decoded to learn whose it is,
#: so the work is bounded rather than growing with the table forever.
MAX_SCANNED_SESSIONS = 5000


def _require_user_admin(actor):
    if not getattr(actor, "is_authenticated", False) or actor.role not in USER_ADMINS:
        raise BusinessPermissionDenied("Session administration is not allowed.")
    return actor


def _decoded_user_id(session):
    """The user id inside a session, or None when it holds no login.

    A session whose data cannot be decoded — a rotated secret key, a truncated
    row — is treated as belonging to nobody rather than raising, so one bad row
    cannot break the page for every user.
    """
    try:
        return session.get_decoded().get(SESSION_KEY)
    except Exception:  # noqa: BLE001 - any decode failure means "not this user's"
        return None


def active_sessions_for(*, actor, target):
    """Every unexpired session belonging to `target`, newest expiry first."""
    _require_user_admin(actor)
    now = timezone.now()
    rows = (
        Session.objects.filter(expire_date__gt=now)
        .order_by("-expire_date")[:MAX_SCANNED_SESSIONS]
    )
    target_id = str(target.pk)
    sessions = []
    for session in rows:
        if _decoded_user_id(session) != target_id:
            continue
        sessions.append({
            # The key itself is a bearer credential, so only a short prefix is
            # ever shown; revoking uses the full key supplied by the caller.
            "session_key": session.session_key,
            "expires_at": session.expire_date,
        })
    return sessions


@transaction.atomic
def revoke_sessions(*, actor, target, session_key=None):
    """End one session, or all of `target`'s, and record what happened.

    Returns the number of sessions ended.
    """
    actor = _require_user_admin(actor)
    now = timezone.now()
    keys = []
    for session in Session.objects.filter(expire_date__gt=now)[:MAX_SCANNED_SESSIONS]:
        if _decoded_user_id(session) != str(target.pk):
            continue
        if session_key and session.session_key != session_key:
            continue
        keys.append(session.session_key)

    ended = Session.objects.filter(session_key__in=keys).delete()[0] if keys else 0
    log_activity(
        actor=actor,
        operation="user.sessions_revoked",
        instance=target,
        changes={
            "target": target.pk,
            # The session key is a credential and never reaches the audit row.
            "scope": "one" if session_key else "all",
            "ended": ended,
        },
    )
    return ended
