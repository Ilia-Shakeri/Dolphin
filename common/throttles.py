from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class SensitiveRateThrottle(UserRateThrottle):
    """Writes on `sensitive` (30/min); reads of the same endpoints on a budget
    of their own, `sensitive_read` (2.40.31).

    Until then a read shared the writes' budget, and one budget across every
    report, list chart, activity log and SMS page: a manager moving between
    reports, or changing a report's range a few times, was refused (429)
    inside a minute — measured: «درخواست‌ها بیش از حد مجاز است» on five pages
    of one walk through the panel. Reads stay bounded, generously; writes keep
    the tight budget they always had.
    """

    scope = "sensitive"
    read_scope = "sensitive_read"

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            self.scope = self.read_scope
            self.rate = self.get_rate()
            self.num_requests, self.duration = self.parse_rate(self.rate)
        return super().allow_request(request, view)


class ChatReadThrottle(UserRateThrottle):
    """Internal chat's reads and read-marks, on a budget of their own.

    Until 2.18.5 every chat endpoint carried `SensitiveRateThrottle`, and a
    DRF rate is per user per *scope*: the drawer's own polling — messages
    every three seconds, threads every eight, the badge every twenty — came
    to roughly thirty requests a minute on its own, the whole `sensitive`
    budget. An open chat was throttled (429) within the minute, which is
    what made older messages take so long to appear; and because the scope
    is shared, it throttled every other sensitive action of that user too —
    saving a dashboard layout, a preference, an invoice. Polling is not a
    sensitive action; it is bounded here generously enough for several open
    tabs, and still bounded.
    """

    scope = "chat"


class ChatSendThrottle(UserRateThrottle):
    """Sending a message or starting a thread — a write, rate-limited as one,
    but on chat's own budget rather than the one every other module's
    writes share."""

    scope = "chat_send"


class SensitiveActionThrottleMixin:
    sensitive_actions = frozenset()

    def get_throttles(self):
        throttles = super().get_throttles()
        if getattr(self, "action", None) in self.sensitive_actions:
            throttles.append(SensitiveRateThrottle())
        return throttles
