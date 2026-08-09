from rest_framework.permissions import BasePermission

from accounts.access import is_crm_identity


class IsActiveAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return is_crm_identity(request.user)
