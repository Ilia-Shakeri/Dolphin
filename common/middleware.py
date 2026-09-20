from ipaddress import ip_address, ip_network
from time import perf_counter_ns
from uuid import uuid4

from django.conf import settings

from common.error_views import payload_too_large
from common.request_context import bind_request_context, clean_ip_address, clean_request_id, reset_request_context
from common.request_logging import write_request_log


class RequestBodyLimitMiddleware:
    """Refuse a request body larger than this deployment accepts.

    Three limits, not one, and each is sized by what its routes actually
    carry. The general limit comes from the largest JSON document the API
    advertises. A spreadsheet or an attachment is a different shape of
    request — a real file, not a document — so the few routes that take one
    get their own, still bounded, allowance. A database dump is a third
    order of size again, hundreds of megabytes against ten, and it reaches
    exactly one route (`common/backups.py`, 2.9.0).

    Without the split, the general limit would have to be the largest of the
    three for every endpoint — which is the opposite of what a body limit is
    for.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _limit_for(self, request):
        backup_paths = getattr(settings, "BACKUP_UPLOAD_PATHS", ())
        if any(request.path.startswith(path) for path in backup_paths):
            return settings.BACKUP_UPLOAD_MAX_BYTES
        upload_paths = getattr(settings, "FILE_UPLOAD_PATHS", ())
        if any(request.path.startswith(path) for path in upload_paths):
            return settings.FILE_UPLOAD_MAX_MEMORY_SIZE
        return settings.DATA_UPLOAD_MAX_MEMORY_SIZE

    def __call__(self, request):
        limit = self._limit_for(request)
        content_length = request.META.get("CONTENT_LENGTH", "")
        try:
            body_size = int(content_length) if content_length else 0
        except (TypeError, ValueError):
            body_size = limit + 1
        if body_size < 0 or body_size > limit:
            return payload_too_large(request)
        return self.get_response(request)


class RequestContextMiddleware:
    header_name = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response
        self.trusted_proxy_networks = tuple(
            ip_network(value, strict=False) for value in settings.AUDIT_TRUSTED_PROXY_CIDRS
        )

    def get_client_ip(self, request):
        peer = clean_ip_address(request.META.get("REMOTE_ADDR"))
        if peer is None:
            return None
        if any(ip_address(peer) in network for network in self.trusted_proxy_networks):
            return clean_ip_address(request.META.get("HTTP_X_REAL_IP")) or peer
        return peer

    def __call__(self, request):
        started_at = perf_counter_ns()
        request_id = clean_request_id(request.headers.get(self.header_name)) or uuid4().hex
        request.request_id = request_id
        token = bind_request_context(request_id=request_id, ip_address=self.get_client_ip(request))
        try:
            response = self.get_response(request)
            response[self.header_name] = request_id
            duration_ms = round((perf_counter_ns() - started_at) / 1_000_000, 3)
            try:
                write_request_log(
                    method=request.method,
                    path=request.path,
                    status=response.status_code,
                    duration_ms=duration_ms,
                )
            except Exception:
                # Access logging must never turn a successful response into a
                # server error; the response is already built and is returned.
                pass
            return response
        finally:
            reset_request_context(token)
