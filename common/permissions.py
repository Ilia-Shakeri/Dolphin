from django.http import Http404
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from accounts.access import is_crm_identity
from common.deployment.profile import feature_enabled


class IsActiveAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return is_crm_identity(request.user)


class FeatureGatedAPIMixin:
    """Refuse a module this deployment's signed manifest does not enable.

    Feature availability is checked before role permission and object scope, and
    stays a separate control from both: a role that would otherwise be allowed
    is still refused when the deployment may not run the module at all, and no
    role gains anything from a feature being enabled.

    The answer is 404, not 403, so a module withheld from a deployment looks
    exactly like one that was never built and reveals nothing about what other
    deployments run.
    """

    required_feature = None

    def initial(self, request, *args, **kwargs):
        if self.required_feature is not None and not feature_enabled(self.required_feature):
            raise NotFound()
        super().initial(request, *args, **kwargs)


class FeatureGatedViewMixin:
    """The same gate for a server-rendered page."""

    required_feature = None

    def dispatch(self, request, *args, **kwargs):
        if self.required_feature is not None and not feature_enabled(self.required_feature):
            raise Http404()
        return super().dispatch(request, *args, **kwargs)
