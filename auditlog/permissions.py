from rest_framework.permissions import BasePermission

from accounts.access import is_crm_identity
from accounts.models import User


class IsAuditReader(BasePermission):
    allowed_roles = {User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}

    def has_permission(self, request, view):
        return bool(
            is_crm_identity(request.user)
            and request.user.role in self.allowed_roles
        )
