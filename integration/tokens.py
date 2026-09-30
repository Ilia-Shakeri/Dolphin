"""PRELIMINARY, UNCOMMITTED — see integration/apps.py.

The cross-product hand-off token — identical module to Dolphin Accounting's
own `integration/tokens.py`; kept byte-for-byte the same on both sides
deliberately, since a HMAC scheme where the two ends disagree about the
wire format is a scheme that does not work.

**Conservative-default decision, flagged for review** (per this goal's own
"what to do when you hit an unanswered decision" rule): the goal text says
"a short-lived, signed hand-off token" without naming an algorithm. This
uses HMAC-SHA256 over a shared secret rather than the Ed25519 keypair the
deployment *manifest* itself uses. Reasoning: the manifest's asymmetric
signature exists so a manifest can be verified by many deployments against
one widely-distributed public key with no shared secret at all — the
opposite of this token, which is only ever exchanged between exactly two
paired deployments that already had to agree on a secret out of band for
the webhook anyway (Group C/Q11 answer: provisioned once, manually, through
the extended `scripts/manifest_builder.py` console). HMAC-SHA256 is a
standard, secure choice for exactly this shape (the same primitive behind a
JWT "HS256" token) and needs no new asymmetric-signing code beyond the
verification-only `common/deployment/ed25519.py` this project already
carries. If a future round decides the manifest's own asymmetric keys
should be reused instead, only this file changes.
"""

import base64
import hashlib
import hmac
import json
import time


class TokenError(Exception):
    """The token is malformed, expired, or does not verify. Never partially
    trusted — every caller must treat this as "deny", not "deny softly"."""


def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text):
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def mint_handoff_token(*, secret, issuer, audience, claims, ttl_seconds):
    if not secret:
        raise TokenError("No shared secret is configured for this pairing.")
    now = int(time.time())
    payload = {
        **claims,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(signature)}"


def verify_handoff_token(*, secret, token, expected_audience):
    """Return the verified claims dict, or raise `TokenError`.

    Signature is checked in constant time (`hmac.compare_digest`). Every
    failure mode — bad shape, bad signature, expired, wrong audience — is
    the same `TokenError`, so a caller cannot accidentally branch into a
    partially-trusted path for one failure kind but not another.
    """
    if not secret:
        raise TokenError("No shared secret is configured for this pairing.")
    if not token or "." not in token:
        raise TokenError("Malformed hand-off token.")
    body, _, signature_part = token.partition(".")
    try:
        expected = hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
        actual = _b64url_decode(signature_part)
    except (ValueError, UnicodeDecodeError) as error:
        raise TokenError("Malformed hand-off token.") from error
    if not hmac.compare_digest(expected, actual):
        raise TokenError("Hand-off token signature does not verify.")
    try:
        claims = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise TokenError("Malformed hand-off token payload.") from error
    if not isinstance(claims, dict):
        raise TokenError("Malformed hand-off token payload.")
    if claims.get("aud") != expected_audience:
        raise TokenError("Hand-off token was not issued for this product.")
    if int(claims.get("exp", 0)) < int(time.time()):
        raise TokenError("Hand-off token has expired.")
    return claims
