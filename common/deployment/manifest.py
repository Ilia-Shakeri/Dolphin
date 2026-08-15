"""Read and verify the signed deployment manifest (PROFILE-001, Option C).

The manifest is the sole source of truth for feature availability. It is an
external file, signed with the platform owner's Ed25519 private key, which never
leaves the platform owner. A deployment holds only the public key, so a customer
with Administrator rights on their own host can read the manifest but cannot
issue or alter one that verifies.

Every rejection path raises `ManifestError`. There is no partially-trusted
outcome and no default-open branch: a manifest that is missing, malformed,
unsigned, signed by an unknown key, signed with an unknown algorithm, tampered
with, issued for an unknown profile, naming an unknown feature, or naming a
feature whose dependencies are unmet is refused outright.
"""

import base64
import binascii
import hashlib
import json

from common.deployment import ed25519
from common.deployment.registry import (
    PROFILES,
    missing_dependencies,
    unknown_features,
)


SUPPORTED_MANIFEST_VERSION = 1
SUPPORTED_ALGORITHM = "ed25519"
MAX_MANIFEST_BYTES = 64 * 1024


class ManifestError(Exception):
    """The manifest cannot be trusted, for any reason."""


class VerifiedManifest:
    """A manifest whose signature and contents have both been accepted."""

    __slots__ = ("profile_id", "features", "key_id", "issued_at", "fingerprint")

    def __init__(self, *, profile_id, features, key_id, issued_at, fingerprint):
        self.profile_id = profile_id
        self.features = frozenset(features)
        self.key_id = key_id
        self.issued_at = issued_at
        self.fingerprint = fingerprint

    def __repr__(self):
        return (
            f"VerifiedManifest(profile_id={self.profile_id!r}, "
            f"features={sorted(self.features)!r}, key_id={self.key_id!r}, "
            f"fingerprint={self.fingerprint!r})"
        )


def _decode_base64(value, field):
    if not isinstance(value, str) or not value:
        raise ManifestError(f"Manifest field '{field}' must be a base64 string.")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ManifestError(f"Manifest field '{field}' is not valid base64.") from error


def _load_json(raw, what):
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestError(f"The manifest {what} is not valid UTF-8 JSON.") from error
    if not isinstance(document, dict):
        raise ManifestError(f"The manifest {what} must be a JSON object.")
    return document


def verify_manifest_bytes(raw, public_keys):
    """Verify a manifest envelope and return the trusted `VerifiedManifest`.

    `public_keys` maps a key id to that key's 32 raw Ed25519 public key bytes.
    An empty mapping can never verify anything, which is the correct fail-closed
    behaviour for a deployment with no trusted signer configured.
    """
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ManifestError("The deployment manifest is larger than the accepted limit.")

    envelope = _load_json(raw, "envelope")

    if envelope.get("manifest_version") != SUPPORTED_MANIFEST_VERSION:
        raise ManifestError("The deployment manifest version is not supported.")
    if envelope.get("algorithm") != SUPPORTED_ALGORITHM:
        raise ManifestError("The deployment manifest signature algorithm is not supported.")

    key_id = envelope.get("key_id")
    if not isinstance(key_id, str) or not key_id:
        raise ManifestError("The deployment manifest does not name a signing key.")
    public_key = public_keys.get(key_id) if public_keys else None
    if public_key is None:
        raise ManifestError("The deployment manifest is signed by an untrusted key.")

    payload_bytes = _decode_base64(envelope.get("payload"), "payload")
    signature = _decode_base64(envelope.get("signature"), "signature")

    # The signature covers the exact payload bytes, and those same bytes are
    # what gets parsed below, so no re-serialisation can change what was signed.
    if not ed25519.verify(public_key, payload_bytes, signature):
        raise ManifestError("The deployment manifest signature is not valid.")

    payload = _load_json(payload_bytes, "payload")

    if payload.get("manifest_version") != SUPPORTED_MANIFEST_VERSION:
        raise ManifestError("The signed manifest payload version is not supported.")

    profile_id = payload.get("profile_id")
    if not isinstance(profile_id, str) or profile_id not in PROFILES:
        raise ManifestError("The deployment manifest names an unknown profile.")

    features = payload.get("features")
    if not isinstance(features, list) or not all(isinstance(item, str) for item in features):
        raise ManifestError("The deployment manifest feature list is malformed.")
    if len(set(features)) != len(features):
        raise ManifestError("The deployment manifest repeats a feature.")

    absent = unknown_features(features)
    if absent:
        raise ManifestError(
            "The deployment manifest enables features this release does not ship: "
            + ", ".join(sorted(absent))
        )
    unmet = missing_dependencies(features)
    if unmet:
        detail = "; ".join(
            f"{feature} requires {', '.join(sorted(required))}"
            for feature, required in sorted(unmet.items())
        )
        raise ManifestError(f"The deployment manifest has unmet feature dependencies: {detail}")

    issued_at = payload.get("issued_at")
    if not isinstance(issued_at, str) or not issued_at:
        raise ManifestError("The deployment manifest does not record when it was issued.")

    return VerifiedManifest(
        profile_id=profile_id,
        features=frozenset(features),
        key_id=key_id,
        issued_at=issued_at,
        # Identifies exactly which manifest is active, for startup logging and
        # for detecting a stale database cache after a restore.
        fingerprint=hashlib.sha256(raw).hexdigest(),
    )


def read_manifest_file(path, public_keys):
    """Read a manifest from disk and verify it."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
    except OSError as error:
        raise ManifestError("The deployment manifest could not be read.") from error
    return verify_manifest_bytes(raw, public_keys)


def decode_public_keys(configured):
    """Turn the configured {key_id: base64 public key} mapping into raw bytes."""
    decoded = {}
    for key_id, value in (configured or {}).items():
        if not isinstance(key_id, str) or not key_id:
            raise ManifestError("A trusted manifest signing key has no usable id.")
        raw = _decode_base64(value, f"public key '{key_id}'")
        if len(raw) != ed25519.PUBLIC_KEY_LENGTH:
            raise ManifestError(f"Trusted manifest signing key '{key_id}' is not an Ed25519 public key.")
        decoded[key_id] = raw
    return decoded
