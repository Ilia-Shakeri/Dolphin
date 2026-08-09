from rest_framework.exceptions import PermissionDenied, ValidationError


class BusinessRuleError(ValidationError):
    pass


class BusinessPermissionDenied(PermissionDenied):
    pass

