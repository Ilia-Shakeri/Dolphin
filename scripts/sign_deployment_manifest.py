"""Issue a signed deployment manifest (PROFILE-001, Option C).

This tool belongs to the platform owner and is excluded from the shipped image
by `.dockerignore`, so neither it nor a signing key ever reaches a customer
host. The application can only verify.

Generate a signing key once, with OpenSSL rather than with this file:

    openssl genpkey -algorithm ed25519 -out dolphin-manifest-signing.pem
    openssl pkey -in dolphin-manifest-signing.pem -pubout -outform DER \\
        | tail -c 32 | base64

Keep the private key off every customer host and out of this repository. The
base64 public key goes into `DEPLOYMENT_MANIFEST_PUBLIC_KEYS` for the
deployments that must trust it.

Usage:

    python scripts/sign_deployment_manifest.py \\
        --private-key dolphin-manifest-signing.pem \\
        --key-id dolphin-2026 \\
        --profile-id client-1 \\
        --feature customers --feature leads ... \\
        --output manifest.json
"""

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from common.deployment import ed25519  # noqa: E402
from common.deployment.registry import (  # noqa: E402
    missing_dependencies,
    unknown_features,
    valid_profile_id,
)


def derive_public_key(private_scalar_seed):
    """The 32-byte Ed25519 public key for a private key seed.

    Split out of `sign()` so a caller who only wants to *display* the public
    key — to paste into `DOLPHIN_DEPLOYMENT_MANIFEST_KEYS` — never has to sign an
    arbitrary throwaway message to get one.
    """
    if len(private_scalar_seed) != 32:
        raise ValueError("An Ed25519 private key seed is 32 bytes.")
    digest = hashlib.sha512(private_scalar_seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return _compress(ed25519._point_multiply(scalar, ed25519.BASE_POINT))


def sign(private_scalar_seed, message):
    """Produce an Ed25519 signature (RFC 8032 section 5.1.6) for `message`."""
    if len(private_scalar_seed) != 32:
        raise ValueError("An Ed25519 private key seed is 32 bytes.")
    digest = hashlib.sha512(private_scalar_seed).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    prefix = digest[32:]

    public_key = derive_public_key(private_scalar_seed)

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
    if not valid_profile_id(profile_id):
        raise ValueError(f"Malformed profile id: {profile_id!r}")
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


def format_public_key(key_id, public_key):
    """The exact `key_id:base64` line `DOLPHIN_DEPLOYMENT_MANIFEST_KEYS` expects.

    Validated here rather than left to whoever pastes it: a public key that
    decodes to anything but 32 bytes cannot be a real Ed25519 key, and
    `production_env.py` finding out at container start — after a `sed` wrote
    an empty or truncated value because the key it read from did not exist —
    is exactly the failure this exists to catch earlier.
    """
    if len(public_key) != 32:
        raise ValueError("An Ed25519 public key is 32 bytes.")
    encoded = base64.b64encode(public_key).decode("ascii")
    if len(encoded) != 44:
        raise ValueError(f"Encoded public key is {len(encoded)} characters, expected 44.")
    return f"{key_id}:{encoded}"


def generate_key(path):
    """Generate a new Ed25519 private key with OpenSSL, refusing to overwrite.

    Shells out to the same `openssl genpkey` this script's own docstring told
    an operator to run by hand — the file format `read_private_seed` parses is
    exactly OpenSSL's, so generating any other way risks a mismatch this
    script cannot read back.
    """
    destination = Path(path)
    if destination.exists():
        raise ProvisioningLikeError(
            f"{destination} already exists. Generating would replace a key "
            "that may already have signed a manifest in use. Move it aside "
            "first if you truly mean to replace it."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(destination)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ProvisioningLikeError(
            f"openssl genpkey failed: {result.stderr.strip() or 'no output'}"
        )
    destination.chmod(0o600)


class ProvisioningLikeError(Exception):
    """Something the operator must fix; reported without a traceback."""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--generate-key", metavar="PATH",
        help="generate a new Ed25519 private key at PATH and exit; every other option is ignored",
    )
    parser.add_argument(
        "--print-public-key", action="store_true",
        help="print 'key_id:base64publickey' for --private-key/--key-id and exit, signing nothing",
    )
    parser.add_argument("--private-key")
    parser.add_argument("--key-id")
    # No `choices=` restriction: a profile id this release has never seen
    # before is exactly how a new customer is onboarded (see the 2026-09-05
    # comment above `PROFILES` in common/deployment/registry.py). Malformed
    # is still refused, by `build_manifest`'s own `valid_profile_id` check
    # below, with the same clean CLI error every other validation here uses.
    parser.add_argument("--profile-id")
    parser.add_argument("--feature", action="append", default=[], dest="features")
    parser.add_argument("--issued-at", default=None)
    parser.add_argument("--output")
    arguments = parser.parse_args(argv)

    try:
        if arguments.generate_key:
            generate_key(arguments.generate_key)
            read_private_seed(arguments.generate_key)  # proves it reads back before reporting success
            sys.stdout.write(
                f"Generated {arguments.generate_key} (mode 0600).\n\n"
                "Next, get its public key with a key id:\n\n"
                f"    python {sys.argv[0]} --print-public-key "
                f"--private-key {arguments.generate_key} --key-id <id>\n"
            )
            return 0

        if arguments.print_public_key:
            if not arguments.private_key or not arguments.key_id:
                sys.stderr.write("--print-public-key needs --private-key and --key-id.\n")
                return 2
            public_key = derive_public_key(read_private_seed(arguments.private_key))
            line = format_public_key(arguments.key_id, public_key)
            sys.stdout.write(f"{line}\n")
            sys.stdout.write(
                "\nPaste the line above, unmodified, as one value in "
                "DOLPHIN_DEPLOYMENT_MANIFEST_KEYS.\n"
            )
            return 0

        for name in ("private_key", "key_id", "profile_id", "output"):
            if not getattr(arguments, name):
                sys.stderr.write(f"--{name.replace('_', '-')} is required to sign a manifest.\n")
                return 2

        issued_at = arguments.issued_at or datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ).replace("+00:00", "Z")
        manifest = build_manifest(
            seed=read_private_seed(arguments.private_key),
            key_id=arguments.key_id,
            profile_id=arguments.profile_id,
            features=arguments.features,
            issued_at=issued_at,
        )
    except (ValueError, ProvisioningLikeError) as error:
        sys.stderr.write(f"{error}\n")
        return 2
    # 0644, not the private key's 0600: this file is signed, not secret, and
    # the application container reads it as a non-root user. Setting the mode
    # here means it is correct from the moment it is written, on the signing
    # machine, before a copy to the customer host has any chance to lose it.
    Path(arguments.output).write_bytes(manifest)
    Path(arguments.output).chmod(0o644)
    sys.stdout.write(
        f"Wrote {arguments.output} (mode 0644) for profile {arguments.profile_id} "
        f"({len(arguments.features)} features).\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
