from django.http import JsonResponse
from django.views import defaults
from django.views.csrf import csrf_failure as django_csrf_failure

from common.request_context import current_request_context


def _is_api_request(request):
    return request.path.startswith("/api/")


def _api_error(request, *, status, code, detail):
    request_id = getattr(request, "request_id", "") or current_request_context().request_id
    return JsonResponse(
        {
            "detail": detail,
            "error": {
                "code": code,
                "request_id": request_id,
            },
        },
        status=status,
    )


def payload_too_large(request):
    if _is_api_request(request):
        return _api_error(
            request,
            status=413,
            code="payload_too_large",
            detail="Request body is too large.",
        )
    return JsonResponse({"detail": "Request body is too large."}, status=413)


def bad_request(request, exception):
    if _is_api_request(request):
        return _api_error(
            request,
            status=400,
            code="bad_request",
            detail="Bad request.",
        )
    return defaults.bad_request(request, exception)


def permission_denied(request, exception):
    if _is_api_request(request):
        return _api_error(
            request,
            status=403,
            code="permission_denied",
            detail="Permission denied.",
        )
    return defaults.permission_denied(request, exception)


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    if _is_api_request(request):
        return _api_error(
            request,
            status=403,
            code="csrf_failed",
            detail="CSRF check failed.",
        )
    return django_csrf_failure(request, reason=reason, template_name=template_name)


def page_not_found(request, exception):
    if _is_api_request(request):
        return _api_error(
            request,
            status=404,
            code="not_found",
            detail="Not found.",
        )
    return defaults.page_not_found(request, exception)


def server_error(request):
    if _is_api_request(request):
        return _api_error(
            request,
            status=500,
            code="server_error",
            detail="Internal server error.",
        )
    return defaults.server_error(request)
