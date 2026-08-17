from django.core.exceptions import PermissionDenied as DjangoPermissionDenied, RequestDataTooBig
from django.http import Http404
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response

from common.request_context import current_request_context
from common.request_logging import write_server_fault_log


class BusinessRuleError(ValidationError):
    pass


class BusinessConflictError(BusinessRuleError):
    status_code = 409
    default_code = "conflict"


class BusinessPermissionDenied(PermissionDenied):
    pass


def _stable_error_code(exc):
    if isinstance(exc, RequestDataTooBig):
        return "payload_too_large"
    if isinstance(exc, BusinessConflictError):
        return "conflict"
    if isinstance(exc, Throttled):
        return "throttled"
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        return "authentication_failed"
    if isinstance(exc, (PermissionDenied, DjangoPermissionDenied)):
        return "permission_denied"
    if isinstance(exc, (NotFound, Http404)):
        return "not_found"
    if isinstance(exc, MethodNotAllowed):
        return "method_not_allowed"
    if isinstance(exc, NotAcceptable):
        return "not_acceptable"
    if isinstance(exc, UnsupportedMediaType):
        return "unsupported_media_type"
    if isinstance(exc, ParseError):
        return "parse_error"
    if isinstance(exc, ValidationError):
        return "validation_error"
    return "api_error"


def api_exception_handler(exc, context):
    if isinstance(exc, RequestDataTooBig):
        return Response(
            {
                "detail": "Request body is too large.",
                "error": {
                    "code": "payload_too_large",
                    "request_id": current_request_context().request_id,
                },
            },
            status=413,
        )
    response = drf_exception_handler(exc, context)
    if response is None:
        request = context.get("request")
        if request is None or not request.path.startswith("/api/"):
            return None
        try:
            write_server_fault_log(exc=exc, request=request)
        except Exception:
            # A logging failure must not replace the handled error with a
            # different one. The client still gets the stable 500 envelope.
            pass
        return Response(
            {
                "detail": "Internal server error.",
                "error": {
                    "code": "server_error",
                    "request_id": current_request_context().request_id,
                },
            },
            status=500,
        )
    if isinstance(response.data, dict):
        payload = dict(response.data)
    else:
        payload = {"detail": response.data}
    payload["error"] = {
        "code": _stable_error_code(exc),
        "request_id": current_request_context().request_id,
    }
    response.data = payload
    return response
