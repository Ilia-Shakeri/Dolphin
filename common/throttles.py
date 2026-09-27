from rest_framework.throttling import UserRateThrottle


class SensitiveRateThrottle(UserRateThrottle):
    scope = "sensitive"


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
