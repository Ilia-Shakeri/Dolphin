from ipaddress import ip_address, ip_network
from time import perf_counter_ns
from uuid import uuid4

from django.conf import settings

from common.error_views import payload_too_large
from common.request_context import bind_request_context, clean_ip_address, clean_request_id, reset_request_context
from common.request_logging import write_request_log


class RequestBodyLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        content_length = request.META.get("CONTENT_LENGTH", "")
        try:
            body_size = int(content_length) if content_length else 0
        except (TypeError, ValueError):
            body_size = settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1
        if body_size < 0 or body_size > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
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
