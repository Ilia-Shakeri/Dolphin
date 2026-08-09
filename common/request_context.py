import re
from contextvars import ContextVar
from dataclasses import dataclass
from ipaddress import ip_address


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True)
class RequestContext:
    request_id: str = ""
    ip_address: str | None = None


_REQUEST_CONTEXT = ContextVar("request_context", default=RequestContext())


def clean_request_id(value):
    if isinstance(value, str) and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return ""


def clean_ip_address(value):
    try:
        return str(ip_address(value))
    except ValueError:
        return None


def bind_request_context(*, request_id, ip_address=None):
    return _REQUEST_CONTEXT.set(
        RequestContext(
            request_id=clean_request_id(request_id),
            ip_address=clean_ip_address(ip_address),
        )
    )


def reset_request_context(token):
    _REQUEST_CONTEXT.reset(token)


def current_request_context():
    return _REQUEST_CONTEXT.get()
