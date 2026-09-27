"""`Authorization: Bearer dol_…` — the public API's authentication (2.21.0).

A token is bound to one CRM user (decision D17): the request runs as that
user, so every role, capability, per-user override and object-scope rule in
the product applies to it unchanged. The token's own scopes only narrow it
further — a `read` token may use safe methods and nothing else.

Only the SHA-256 of a token is stored. A revoked, expired or unknown token,
or one whose user is no longer an active CRM identity, is refused; with the
`public_api` feature off the header is ignored altogether, so the request is
simply unauthenticated.
"""

from django.utils import timezone
from rest_framework import authentication, exceptions

from accounts.access import is_crm_identity
from common.deployment.profile import feature_enabled

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
#: `last_used_at` is written at most this often per token.
TOUCH_INTERVAL_SECONDS = 300


class ApiTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        parts = header.split()
        if len(parts) != 2 or parts[0] != self.keyword or not parts[1].startswith("dol_"):
            return None
        if not feature_enabled("public_api"):
            return None
        from integrations.models import ApiToken
        from integrations.services import hash_token

        token = ApiToken.objects.select_related("user").filter(token_hash=hash_token(parts[1])).first()
        now = timezone.now()
        if token is None or token.revoked_at is not None or (token.expires_at and token.expires_at <= now):
            raise exceptions.AuthenticationFailed("توکن نامعتبر یا منقضی است.")
        if not is_crm_identity(token.user):
            raise exceptions.AuthenticationFailed("کاربرِ این توکن فعال نیست.")
        if request.method not in SAFE_METHODS and "write" not in token.scopes:
            raise exceptions.PermissionDenied("این توکن فقط اجازهٔ خواندن دارد.")
        if token.last_used_at is None or (now - token.last_used_at).total_seconds() > TOUCH_INTERVAL_SECONDS:
            ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
        return token.user, token

    def authenticate_header(self, request):
        return self.keyword
