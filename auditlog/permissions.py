from rest_framework.permissions import BasePermission

from accounts.access import has_any_capability


class IsAuditReader(BasePermission):
    def has_permission(self, request, view):
        return has_any_capability(request.user, "audit.non_platform", "audit.all")
