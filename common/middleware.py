from ipaddress import ip_address, ip_network
from uuid import uuid4

from django.conf import settings

from common.request_context import bind_request_context, clean_ip_address, clean_request_id, reset_request_context


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
        request_id = clean_request_id(request.headers.get(self.header_name)) or uuid4().hex
        request.request_id = request_id
        token = bind_request_context(request_id=request_id, ip_address=self.get_client_ip(request))
        try:
            response = self.get_response(request)
            response[self.header_name] = request_id
            return response
        finally:
            reset_request_context(token)
