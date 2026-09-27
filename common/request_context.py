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


#: Answers that cannot change inside one request but are asked for many times
#: while producing it — who the signed-in user is and what they may do
#: (`accounts.access.capabilities_for`, `is_crm_account`). Rendering one page
#: used to ask each of them eight to eleven times, and each asking was a
#: database query: about sixteen of a list page's twenty-four (2.18.9).
#:
#: `None` outside a request, so management commands, the shell and service
#: calls in tests behave exactly as before — nothing is ever memoised there.
#: A service that changes a user's role or permission overrides calls
#: `forget_request_memo()`, so a later question in the same request sees the
#: change.
_REQUEST_MEMO = ContextVar("request_memo", default=None)


def bind_request_memo():
    return _REQUEST_MEMO.set({})


def reset_request_memo(token):
    _REQUEST_MEMO.reset(token)


def request_memo():
    """This request's memo, or `None` when there is no request."""
    return _REQUEST_MEMO.get()


def forget_request_memo():
    memo = _REQUEST_MEMO.get()
    if memo is not None:
        memo.clear()
