"""Secrets at rest for the integrations — the shared implementation lives in
`common.crypto` since 2.40.42 (two-factor keys use it too); these names stay
so the integrations code and its documentation keep reading the same."""

from common.crypto import (  # noqa: F401 - re-exported
    SecretsUnavailable,
    decrypt_json,
    encrypt_json,
    generate_key,
    secrets_available,
)
