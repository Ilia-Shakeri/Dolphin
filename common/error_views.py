from django.http import JsonResponse
from django.shortcuts import render

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


def _ui_error(request, *, status, title, message):
    return render(
        request,
        "common/error.html",
        {"status": status, "title": title, "message": message},
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
    return _ui_error(
        request,
        status=400,
        title="درخواست نامعتبر",
        message="درخواست قابل پردازش نیست.",
    )


def permission_denied(request, exception):
    if _is_api_request(request):
        return _api_error(
            request,
            status=403,
            code="permission_denied",
            detail="Permission denied.",
        )
    return _ui_error(
        request,
        status=403,
        title="دسترسی مجاز نیست",
        message="شما اجازه دیدن این بخش را ندارید.",
    )


def csrf_failure(request, reason="", template_name="403_csrf.html"):
    if _is_api_request(request):
        return _api_error(
            request,
            status=403,
            code="csrf_failed",
            detail="CSRF check failed.",
        )
    return _ui_error(
        request,
        status=403,
        title="درخواست امن نبود",
        message="صفحه را تازه کنید و دوباره تلاش کنید.",
    )


def page_not_found(request, exception):
    if _is_api_request(request):
        return _api_error(
            request,
            status=404,
            code="not_found",
            detail="Not found.",
        )
    return _ui_error(
        request,
        status=404,
        title="صفحه پیدا نشد",
        message="نشانی واردشده در سامانه وجود ندارد.",
    )


def server_error(request):
    if _is_api_request(request):
        return _api_error(
            request,
            status=500,
            code="server_error",
            detail="Internal server error.",
        )
    return _ui_error(
        request,
        status=500,
        title="خطای سامانه",
        message="خطایی رخ داد. کمی بعد دوباره تلاش کنید.",
    )
