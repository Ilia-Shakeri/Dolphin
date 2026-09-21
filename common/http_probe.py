"""Running one outbound HTTP request and reporting what happened, safely.

Extracted 2026-09-21 from `communications/sms.py`'s own private `_execute` —
the post-carrier settings page (`sales/postal_provider.py`) needed the exact
same "call this URL, tell me the status and a safe text snippet, never
raise" behaviour for its own «تست اتصال» button, and a second private copy
of it is exactly the kind of duplication CLAUDE.md's repository constitution
asks to be shared instead («هر چیزی که چند جا تکرار می‌شود ... باید یک
کامپوننت مشترک شود»). `communications/sms.py` now imports this rather than
defining its own.

Deliberately tiny: this is not an HTTP client abstraction, a retry policy or
a connection pool — just the one thing both callers needed, moved to where
both can reach it without one importing the other's module for an unrelated
reason.
"""

import urllib.error
import urllib.request

#: How much of a response body is worth keeping — enough to recognise an
#: error message, not enough to store or log anything resembling the
#: response's own payload wholesale.
MAX_RESPONSE_DETAIL = 200


def run_http_probe(request, *, timeout):
    """Runs one `urllib.request.Request` and returns
    `(status, response_text, error_detail)`.

    Exactly one of `(status, response_text)` and `error_detail` is
    meaningful: a connection failure never raises past this point, which is
    the whole point of a "test connection" button — the failure itself is
    the useful answer, not an exception the view would have to catch.
    """
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (
                response.status,
                response.read(MAX_RESPONSE_DETAIL).decode("utf-8", errors="replace"),
                None,
            )
    except urllib.error.HTTPError as error:
        text = error.read(MAX_RESPONSE_DETAIL).decode("utf-8", errors="replace") if error.fp else ""
        return error.code, text, None
    except (urllib.error.URLError, OSError, ValueError) as error:
        return None, "", f"connection error: {error.__class__.__name__}"
