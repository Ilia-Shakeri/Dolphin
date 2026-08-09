from rest_framework.throttling import UserRateThrottle


class SensitiveRateThrottle(UserRateThrottle):
    scope = "sensitive"


class SensitiveActionThrottleMixin:
    sensitive_actions = frozenset()

    def get_throttles(self):
        throttles = super().get_throttles()
        if getattr(self, "action", None) in self.sensitive_actions:
            throttles.append(SensitiveRateThrottle())
        return throttles
