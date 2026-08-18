"""Issue a signed deployment manifest (PROFILE-001, Option C).

This tool belongs to the platform owner and is excluded from the shipped image
by `.dockerignore`, so neither it nor a signing key ever reaches a customer
host. The application can only verify.

Generate a signing key once, with OpenSSL rather than with this file:

    openssl genpkey -algorithm ed25519 -out forooshbin-manifest-signing.pem
    openssl pkey -in forooshbin-manifest-signing.pem -pubout -outform DER \\
        | tail -c 32 | base64

Keep the private key off every customer host and out of this repository. The
base64 public key goes into `DEPLOYMENT_MANIFEST_PUBLIC_KEYS` for the
deployments that must trust it.

Usage:

    python scripts/sign_deployment_manifest.py \\
        --private-key forooshbin-manifest-signing.pem \\
        --key-id kariz-2026 \\
        --profile-id client-1 \\
        --feature customers --feature leads ... \\
        --output manifest.json
"""

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from common.deployment import ed25519  # noqa: E402
from common.deployment.registry import (  # noqa: E402
    PROFILES,
    missing_dependencies,
    unknown_features,
)


def sign(private_scalar_seed, message):
    """Produce an Ed25519 signature (RFC 8032 section 5.1.6) for `message`."""
    if len(private_scalar_seed) != 32:
        raise ValueError("An Ed25519 private key seed is 32 bytes.")
    digest = hashlib.sha512(private_scalar_seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    prefix = digest[32:]

    public_point = ed25519._point_multiply(scalar, ed25519.BASE_POINT)
    public_key = _compress(public_point)

    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % ed25519.Q
    nonce_point = _compress(ed25519._point_multiply(nonce, ed25519.BASE_POINT))
    challenge = int.from_bytes(
        hashlib.sha512(nonce_point + public_key + message).digest(), "little"
    ) % ed25519.Q
    proof = (nonce + challenge * scalar) % ed25519.Q
    return public_key, nonce_point + proof.to_bytes(32, "little")


def _compress(point):
    inverse_z = pow(point[2], ed25519.P - 2, ed25519.P)
    x = point[0] * inverse_z % ed25519.P
    y = point[1] * inverse_z % ed25519.P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def read_private_seed(path):
    """Read the 32-byte seed from an OpenSSL PKCS#8 Ed25519 private key."""
    text = Path(path).read_text(encoding="ascii")
    body = "".join(
        line for line in text.splitlines() if line and not line.startswith("-----")
    )
    der = base64.b64decode(body)
    # An unencrypted PKCS#8 Ed25519 private key is a fixed 48-byte structure:
    # a 16-byte header naming the algorithm, then the 32-byte seed.
    header = bytes.fromhex("302e020100300506032b657004220420")
    if len(der) != 48 or der[:16] != header:
        raise ValueError("The private key file is not an unencrypted Ed25519 PKCS#8 key.")
    return der[16:]


def build_manifest(*, seed, key_id, profile_id, features, issued_at):
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown profile id: {profile_id}")
    absent = unknown_features(features)
    if absent:
        raise ValueError(f"Unknown features: {', '.join(sorted(absent))}")
    unmet = missing_dependencies(features)
    if unmet:
        detail = "; ".join(
            f"{feature} requires {', '.join(sorted(required))}"
            for feature, required in sorted(unmet.items())
        )
        raise ValueError(f"Unmet feature dependencies: {detail}")

    payload = json.dumps(
        {
            "manifest_version": 1,
            "profile_id": profile_id,
            "issued_at": issued_at,
            "features": sorted(features),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    _, signature = sign(seed, payload)
    return json.dumps(
        {
            "manifest_version": 1,
            "algorithm": "ed25519",
            "key_id": key_id,
            "payload": base64.b64encode(payload).decode("ascii"),
            "signature": base64.b64encode(signature).decode("ascii"),
        },
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--profile-id", required=True, choices=sorted(PROFILES))
    parser.add_argument("--feature", action="append", default=[], dest="features")
    parser.add_argument("--issued-at", default=None)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args(argv)

    issued_at = arguments.issued_at or datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    try:
        manifest = build_manifest(
            seed=read_private_seed(arguments.private_key),
            key_id=arguments.key_id,
            profile_id=arguments.profile_id,
            features=arguments.features,
            issued_at=issued_at,
        )
    except ValueError as error:
        sys.stderr.write(f"{error}\n")
        return 2
    Path(arguments.output).write_bytes(manifest)
    sys.stdout.write(
        f"Wrote {arguments.output} for profile {arguments.profile_id} "
        f"({len(arguments.features)} features).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
