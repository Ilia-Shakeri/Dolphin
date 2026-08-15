"""Ed25519 signature verification, following RFC 8032.

The deployment manifest (PROFILE-001, Option C) is signed by the platform owner
and verified by every deployment. Only the *public* key ships: this module can
check a signature and can never produce one, so a customer host never holds
material that could forge a manifest.

Why an in-repository implementation rather than a library: the production
dependency set is hash-pinned and must be resolved in a clean Linux CPython 3.13
image (`docs/ops/DEPENDENCIES.md`), which is not possible from the current
development host. This module keeps the phase unblocked with no new dependency.
It is deliberately the RFC 8032 reference algorithm, and
`common/tests/test_deployment_profile.py` checks it against the official RFC
8032 section 7.1 test vectors and against OpenSSL-produced signatures.

There is no secret input to any function here, so the ordinary constant-time
concern for signing code does not apply to this verification path.
"""

import hashlib


# Curve constants, RFC 8032 section 5.1.
P = 2**255 - 19
Q = 2**252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
SQRT_MINUS_ONE = pow(2, (P - 1) // 4, P)

PUBLIC_KEY_LENGTH = 32
SIGNATURE_LENGTH = 64


def _modp_inv(value):
    return pow(value, P - 2, P)


def _recover_x(y, sign):
    """Recover the x coordinate of a compressed point, or None if invalid."""
    if y >= P:
        return None
    x2 = (y * y - 1) * _modp_inv(D * y * y + 1) % P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P != 0:
        x = x * SQRT_MINUS_ONE % P
    if (x * x - x2) % P != 0:
        return None
    if (x & 1) != sign:
        x = P - x
    return x


_G_Y = 4 * _modp_inv(5) % P
_G_X = _recover_x(_G_Y, 0)
BASE_POINT = (_G_X, _G_Y, 1, _G_X * _G_Y % P)


def _point_add(first, second):
    a = (first[1] - first[0]) * (second[1] - second[0]) % P
    b = (first[1] + first[0]) * (second[1] + second[0]) % P
    c = 2 * first[3] * second[3] * D % P
    d = 2 * first[2] * second[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _point_multiply(scalar, point):
    result = (0, 1, 1, 0)
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
        scalar >>= 1
    return result


def _point_equal(first, second):
    if (first[0] * second[2] - second[0] * first[2]) % P != 0:
        return False
    return (first[1] * second[2] - second[1] * first[2]) % P == 0


def _point_decompress(compressed):
    if len(compressed) != PUBLIC_KEY_LENGTH:
        return None
    value = int.from_bytes(compressed, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % P)


def _sha512_modq(data):
    return int.from_bytes(hashlib.sha512(data).digest(), "little") % Q


def verify(public_key, message, signature):
    """Return True only for a valid Ed25519 signature over ``message``.

    Every malformed input — wrong length, a non-canonical point, or a scalar at
    or above the group order — returns False rather than raising, so a caller
    can treat any falsy result as "reject this manifest".
    """
    if not isinstance(public_key, (bytes, bytearray)) or len(public_key) != PUBLIC_KEY_LENGTH:
        return False
    if not isinstance(signature, (bytes, bytearray)) or len(signature) != SIGNATURE_LENGTH:
        return False

    point_a = _point_decompress(bytes(public_key))
    if point_a is None:
        return False
    encoded_r = bytes(signature[:32])
    point_r = _point_decompress(encoded_r)
    if point_r is None:
        return False
    scalar_s = int.from_bytes(signature[32:], "little")
    if scalar_s >= Q:
        return False

    challenge = _sha512_modq(encoded_r + bytes(public_key) + bytes(message))
    checked = _point_multiply(scalar_s, BASE_POINT)
    combined = _point_add(point_r, _point_multiply(challenge, point_a))
    return _point_equal(checked, combined)
