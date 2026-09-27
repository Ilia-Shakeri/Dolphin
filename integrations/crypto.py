"""Secrets at rest — encrypted with a key that lives only in the environment
(2.21.0, decision D9).

An integration's passwords and signing secrets are stored as one Fernet token
(AES-128-CBC with an HMAC-SHA256 tag, from the reviewed `cryptography`
package) under `DOLPHIN_SECRETS_KEY`. The key is never in the database, never
in a backup of it, and never in a log: someone with a copy of the database
alone cannot read a secret out of it.

`DOLPHIN_SECRETS_KEY` may hold several comma-separated keys for rotation: the
first encrypts, all of them decrypt. `manage.py generate_secrets_key` prints a
new one. Without a key the panel still runs; it only refuses to *store* a
secret, and says so.
"""

import json

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings


class SecretsUnavailable(Exception):
    """No usable key is configured, or a stored secret no longer decrypts."""


def _keys():
    raw = getattr(settings, "DOLPHIN_SECRETS_KEY", "") or ""
    return [part.strip() for part in raw.split(",") if part.strip()]


def secrets_available():
    try:
        _fernet()
    except SecretsUnavailable:
        return False
    return True


def _fernet():
    keys = _keys()
    if not keys:
        raise SecretsUnavailable("DOLPHIN_SECRETS_KEY is not set.")
    try:
        return MultiFernet([Fernet(key.encode("ascii")) for key in keys])
    except (ValueError, TypeError) as error:
        raise SecretsUnavailable("DOLPHIN_SECRETS_KEY is not a valid key.") from error


def encrypt_json(data):
    """`{name: value}` → one opaque token. An empty dict stores as ``""``."""
    if not data:
        return ""
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return _fernet().encrypt(payload).decode("ascii")


def decrypt_json(token):
    """The dict `encrypt_json` was given. Raises `SecretsUnavailable` when the
    key is missing or is not the one the token was made with."""
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode("ascii")).decode("utf-8"))
    except InvalidToken as error:
        raise SecretsUnavailable("A stored secret does not decrypt with the configured key.") from error


def generate_key():
    return Fernet.generate_key().decode("ascii")
