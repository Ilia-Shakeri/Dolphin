import logging
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone

from accounts.models import User

logger = logging.getLogger("dolphin.accounts.presence")

#: How stale `User.last_seen_at` may get before a request refreshes it. Two
#: minutes keeps presence at one small UPDATE per person per two minutes,
#: however many requests their open tabs make — the badge and chat polls
#: alone are several a minute.
PRESENCE_WRITE_INTERVAL = timedelta(minutes=2)
#: Seen within this window reads as «آنلاین» on the profile (2.19.0, D8).
ONLINE_WINDOW = timedelta(minutes=5)


def is_online(user, *, now=None):
    seen = getattr(user, "last_seen_at", None)
    if seen is None:
        return False
    return (now or timezone.now()) - seen <= ONLINE_WINDOW


class PresenceMiddleware:
    """Record when each signed-in person was last active.

    Runs after the response is built, and only for a request that carries a
    session cookie — so an anonymous request (health checks, the login page)
    never costs a query, and a signed-in one reuses the user row the view
    already loaded. The write is a filtered `UPDATE` of one column, not a
    `save()`: it must not bump `updated_at` (that stamps a profile edit), and
    it must not race a concurrent edit of the same row.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if settings.SESSION_COOKIE_NAME in request.COOKIES:
            self._touch(request)
        return response

    def _touch(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.is_active:
            return
        now = timezone.now()
        seen = user.last_seen_at
        if seen is not None and now - seen < PRESENCE_WRITE_INTERVAL:
            return
        try:
            User.objects.filter(pk=user.pk).update(last_seen_at=now)
        except DatabaseError:
            # Presence is a convenience; a failed write must never turn a
            # served page into an error. Logged so a persistent failure is
            # still visible to whoever reads the logs.
            logger.warning("presence write failed", extra={"user_id": user.pk})
            return
        user.last_seen_at = now
