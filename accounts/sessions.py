"""Listing and revoking a user's active sessions.

Requirement 1.8. Deliberately built on Django's own session store rather than a
new model: the session table already *is* the record of who is signed in, and a
parallel table would be a second source of truth that could disagree with the
one that actually grants access.

Revoking deletes the session row, so the next request from that browser is
unauthenticated. It does not disable the account — that is a separate control on
the same page, and conflating them would make "sign this person out" silently
mean "lock them out".

**A session key never leaves the server.** It is the bearer credential itself:
anyone holding one can set the cookie and be that user. Every session is
identified outward by `session_reference()` — a keyed digest that is stable for
one deployment, useless anywhere else, and cannot be turned back into the key.
Revocation takes that reference and matches it by re-deriving the digest, so the
client never needs the real value to end a session.
"""

import hashlib
import hmac

from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from accounts.services import USER_ADMINS
from auditlog.services import log_activity
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.request_context import current_request_context


#: Sessions scanned per page. Every row must be decoded to learn whose it is, so
#: the work per request is bounded. Scanning resumes from the last row seen, so
#: "end every session" walks the whole table however large it grows.
SESSION_SCAN_BATCH = 1000
#: Metadata the login view records on the session so a user can recognise their
#: own devices. Never anything that could re-authenticate.
DEVICE_SESSION_KEY = "_device"
REFERENCE_LENGTH = 32


def session_reference(session_key):
    """A stable, non-reversible handle for one session.

    Keyed with `SECRET_KEY`, so the same session has one reference within a
    deployment and no reference that means anything outside it. Truncation is
    safe: this identifies a row the caller already proved they may administer,
    it authenticates nothing.
    """
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"session-reference:{session_key}".encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()[:REFERENCE_LENGTH]


def record_session_device(request):
    """Store the bounded facts that let a user recognise their own devices.

    Written once at login, into the session itself, so no new table is needed
    and the record disappears exactly when the session does. Deliberately three
    short strings: enough to tell "my laptop" from "someone else's browser", and
    nothing that could help re-authenticate.
    """
    started_at = timezone.now().isoformat(timespec="seconds")
    request.session[DEVICE_SESSION_KEY] = {
        "user_agent": str(request.headers.get("User-Agent", ""))[:200],
        "ip_address": str(current_request_context().ip_address or "")[:45],
        "started_at": started_at,
    }


def _require_user_admin(actor):
    if not getattr(actor, "is_authenticated", False) or actor.role not in USER_ADMINS:
        raise BusinessPermissionDenied("مدیریت نشست‌ها مجاز نیست.")
    return actor


def _require_self_or_admin(actor, target):
    """Anyone may administer their own sessions; only an admin may touch another's."""
    if not getattr(actor, "is_authenticated", False):
        raise BusinessPermissionDenied("مدیریت نشست‌ها مجاز نیست.")
    if actor.pk == target.pk:
        return actor
    return _require_user_admin(actor)


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


def _decoded_device(session):
    """The device facts recorded at login, bounded and safe to display."""
    try:
        stored = session.get_decoded().get(DEVICE_SESSION_KEY) or {}
    except Exception:  # noqa: BLE001 - as above
        return {}
    if not isinstance(stored, dict):
        return {}
    return {
        "user_agent": str(stored.get("user_agent", ""))[:200],
        "ip_address": str(stored.get("ip_address", ""))[:45],
        "started_at": str(stored.get("started_at", ""))[:32],
    }


def _sessions_of(target):
    """Every unexpired session belonging to `target`, in a bounded walk.

    Ordered by primary key and resumed from the last row seen, so the scan is
    deterministic and covers the whole table however many rows it holds. An
    unordered `LIMIT` used to decide which sessions were visible, which made
    "end every session" quietly incomplete once the table grew.
    """
    now = timezone.now()
    target_id = str(target.pk)
    after = ""
    while True:
        batch = list(
            Session.objects.filter(expire_date__gt=now, session_key__gt=after)
            .order_by("session_key")[:SESSION_SCAN_BATCH]
        )
        if not batch:
            return
        for session in batch:
            if _decoded_user_id(session) == target_id:
                yield session
        after = batch[-1].session_key


def active_sessions_for(*, actor, target, current_session_key=""):
    """Every unexpired session belonging to `target`, newest expiry first.

    Each row carries a `reference`, never the session key. `is_current` marks
    the caller's own session so the interface can keep them from ending the
    session they are working in without meaning to.
    """
    _require_self_or_admin(actor, target)
    current_reference = session_reference(current_session_key) if current_session_key else ""
    sessions = [
        {
            "reference": session_reference(session.session_key),
            "expires_at": session.expire_date,
            "is_current": bool(
                current_reference and session_reference(session.session_key) == current_reference
            ),
            **_decoded_device(session),
        }
        for session in _sessions_of(target)
    ]
    sessions.sort(key=lambda row: row["expires_at"], reverse=True)
    return sessions


@transaction.atomic
def revoke_sessions(*, actor, target, reference=None, keep_session_key=""):
    """End one session, or all of `target`'s, and record what happened.

    `reference` is the handle from `active_sessions_for`, never a session key.
    `keep_session_key` spares the caller's own session, which is what "end every
    other session" means. Returns the number of sessions ended.
    """
    actor = _require_self_or_admin(actor, target)
    if reference is not None and not isinstance(reference, str):
        raise BusinessRuleError({"reference": "شناسه نشست معتبر وارد کنید."})

    keep_reference = session_reference(keep_session_key) if keep_session_key else ""
    keys = []
    for session in _sessions_of(target):
        session_handle = session_reference(session.session_key)
        if reference and session_handle != reference:
            continue
        if keep_reference and session_handle == keep_reference:
            continue
        keys.append(session.session_key)

    if reference and not keys:
        raise BusinessRuleError({"reference": "این نشست دیگر فعال نیست."})

    ended = Session.objects.filter(session_key__in=keys).delete()[0] if keys else 0
    log_activity(
        actor=actor,
        operation="user.sessions_revoked",
        instance=target,
        changes={
            "target": target.pk,
            # Neither the session key nor its reference reaches the audit row.
            "scope": "one" if reference else "all",
            "ended": ended,
        },
    )
    return ended
