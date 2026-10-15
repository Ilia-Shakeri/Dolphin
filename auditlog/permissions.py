from rest_framework.permissions import BasePermission

from accounts.access import has_any_capability
from auditlog.selectors import AUDIT_READ_CAPABILITIES


class IsAuditReader(BasePermission):
    def has_permission(self, request, view):
        return has_any_capability(request.user, *AUDIT_READ_CAPABILITIES)
