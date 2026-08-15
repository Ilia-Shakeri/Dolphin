from rest_framework.permissions import BasePermission

from accounts.access import has_any_capability


class HasBillingCapability(BasePermission):
    """403 when the caller holds no capability for this billing module.

    Role permission only. Feature availability is checked separately by
    `FeatureGatedAPIMixin`, and object scope separately again in
    `billing/selectors.py`.
    """

    def has_permission(self, request, view):
        return has_any_capability(request.user, *view.required_capabilities)
