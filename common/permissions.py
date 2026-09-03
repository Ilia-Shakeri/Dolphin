from django.http import Http404
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from accounts.access import has_any_capability, is_crm_identity
from accounts.models import User
from common.deployment.profile import feature_enabled


class IsActiveAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return is_crm_identity(request.user)


class IsPlatformAdmin(BasePermission):
    """This deployment's own top role — never "Dolphin the company"'s.

    Each deployment has a separate database, so a Platform Admin here is
    simply whoever administers *this* customer's install. Used for settings
    a lower role must not touch even though it costs the deployment nothing
    to display — `common.branding` (white-label name/logo) is the first.
    """

    def has_permission(self, request, view):
        return is_crm_identity(request.user) and request.user.role == User.Role.PLATFORM_ADMIN


#: HTTP methods that only ever read. Everything else — POST, PUT, PATCH, and
#: DELETE — is a write for the purpose of `HasCapabilityForMethod` below.
#: DELETE additionally needs a Platform Admin actor, checked inside
#: `common.viewsets.HardDeleteMixin` itself rather than here.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class HasCapabilityForMethod(BasePermission):
    """`has_any_capability`, aware of whether the request reads or writes.

    `sales.permissions.HasSalesCapability`, `billing.permissions.
    HasBillingCapability`, and `inventory.permissions.HasInventoryCapability`
    all subclass this rather than reimplementing it, so the one rule lives in
    one place: `view.required_capabilities` gates every method, same as
    before this existed — a viewset that never sets
    `required_write_capabilities` behaves exactly as it always has, holding
    any listed capability is enough for both reading and writing.

    A viewset that *does* set `required_write_capabilities` gets a genuine
    second gate: an unsafe method additionally needs one of those. This is
    what lets a per-user override make someone's access to a module
    read-only — the override changes which capability `has_any_capability`
    finds, not this check itself.
    """

    def has_permission(self, request, view):
        if not has_any_capability(request.user, *getattr(view, "required_capabilities", ())):
            return False
        write_capabilities = getattr(view, "required_write_capabilities", None)
        if write_capabilities is None or request.method in SAFE_METHODS:
            return True
        return has_any_capability(request.user, *write_capabilities)


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
