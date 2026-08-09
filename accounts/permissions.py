from rest_framework.permissions import BasePermission

from accounts.models import User


class IsOperationalManager(BasePermission):
    allowed_roles = {User.Role.SALES_MANAGER, User.Role.PLATFORM_ADMIN}

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_active and request.user.role in self.allowed_roles)


class IsUserReader(BasePermission):
    allowed_roles = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}

    def has_permission(self, request, view):
        return bool(request.user.is_authenticated and request.user.is_active and request.user.role in self.allowed_roles)

