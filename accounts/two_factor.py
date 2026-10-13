"""Two-factor sign-in: an authenticator code after the password (2.40.42).

Roadmap item 12 («ورود دومرحله‌ای (TOTP) برای مدیران»). Feature `two_factor`,
off by default. Any user may turn it on for their own account; it is
recommended for administrators, and the Platform Admin can take it off an
account whose phone is lost (`reset_two_factor`). A host command does the same
for the Platform Admin's own account (`manage.py reset_two_factor`).

* TOTP as RFC 6238 specifies it: HMAC-SHA1, six digits, 30-second steps, one
  step of clock drift either way. Every common authenticator app speaks it.
* The shared key is stored as a `common.crypto` token: without
  `DOLPHIN_SECRETS_KEY` it can be neither turned on nor checked, and a copy of
  the database alone cannot produce codes. Recovery codes are hashes and keep
  working when the key is gone.
* A code is accepted once: the step it belongs to is remembered and a code
  from that step or an earlier one is refused, so an overheard code cannot be
  replayed.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.utils import timezone

from accounts.models import TwoFactorDevice, TwoFactorRecoveryCode, User
from auditlog.services import log_activity
from common import crypto
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10
#: Uppercase letters and digits without the ones that read alike (0/O, 1/I/L).
RECOVERY_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
RECOVERY_ITERATIONS = 120_000
ISSUER = "Dolphin"

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class TwoFactorUnavailable(Exception):
    """The deployment has no usable `DOLPHIN_SECRETS_KEY`."""


# --- TOTP -----------------------------------------------------------------------

def new_secret():
    """A fresh 160-bit key, as the base32 text an authenticator app is given."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret):
    padded = secret + "=" * (-len(secret) % 8)
    return base64.b32decode(padded.upper())


def code_at(secret, step):
    """The six-digit code for one 30-second step (RFC 6238 / RFC 4226)."""
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** DIGITS)).zfill(DIGITS)


def current_step(now=None):
    return int((now if now is not None else time.time()) // STEP_SECONDS)


def _matching_step(secret, code, *, after_step, now=None):
    """The step `code` belongs to, within the allowed drift and newer than
    `after_step`, or None."""
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if candidate > after_step and hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def clean_code(value):
    """What the reader typed, as plain ASCII: Persian digits read as digits,
    spaces and hyphens dropped, letters upper-cased."""
    text = str(value or "").translate(_PERSIAN_DIGITS)
    return "".join(character for character in text if character.isalnum()).upper()


def provisioning_uri(secret, username, issuer=ISSUER):
    """The `otpauth://` address an authenticator app reads from the QR code."""
    label = quote(f"{issuer}:{username}")
    query = urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"


def qr_data_uri(text):
    """The address as an SVG QR code, as a `data:` URI an `<img>` can show."""
    import segno

    return segno.make(text, error="m").svg_data_uri(scale=5, border=2, dark="#000", light="#fff")


# --- storage --------------------------------------------------------------------

def _store(secret):
    try:
        return crypto.encrypt_json({"secret": secret})
    except crypto.SecretsUnavailable as exc:
        raise TwoFactorUnavailable from exc


def _secret_of(device):
    try:
        return crypto.decrypt_json(device.secret_token)["secret"]
    except (crypto.SecretsUnavailable, KeyError) as exc:
        raise TwoFactorUnavailable from exc


def available():
    return crypto.secrets_available()


def enabled_for(user):
    return TwoFactorDevice.objects.filter(user=user, confirmed_at__isnull=False).exists()


def status_for(user):
    device = TwoFactorDevice.objects.filter(user=user).first()
    confirmed = device is not None and device.confirmed_at is not None
    return {
        "available": available(),
        "enabled": confirmed,
        "enabled_at": device.confirmed_at if confirmed else None,
        "recovery_codes_left": user.two_factor_recovery_codes.filter(used_at__isnull=True).count() if confirmed else 0,
    }


def _hash_code(code, salt=None):
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode("ascii"), salt.encode("ascii"), RECOVERY_ITERATIONS)
    return f"{salt}${digest.hex()}"


def _code_matches(code, stored):
    salt, _, _digest = stored.partition("$")
    return hmac.compare_digest(_hash_code(code, salt), stored)


def _issue_recovery_codes(user):
    user.two_factor_recovery_codes.all().delete()
    codes = ["".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10)) for _ in range(RECOVERY_CODE_COUNT)]
    TwoFactorRecoveryCode.objects.bulk_create(
        TwoFactorRecoveryCode(user=user, code_hash=_hash_code(code)) for code in codes
    )
    return [f"{code[:5]}-{code[5:]}" for code in codes]


def _require_password(user, password):
    if not password or not check_password(password, user.password):
        raise BusinessRuleError({"password": "گذرواژه درست نیست."})


# --- the reader's own account -----------------------------------------------------

@transaction.atomic
def begin_enrolment(*, user, password):
    """Start turning two-factor sign-in on: a new key, not yet in force.

    Asks for the password first, so a session left open on someone else's
    screen cannot bind a stranger's phone to the account.
    """
    _require_password(user, password)
    if enabled_for(user):
        raise BusinessConflictError({"detail": "ورود دومرحله‌ای همین حالا روشن است."})
    if not available():
        raise TwoFactorUnavailable
    secret = new_secret()
    TwoFactorDevice.objects.update_or_create(user=user, defaults={
        "secret_token": _store(secret), "confirmed_at": None, "last_used_step": 0,
    })
    uri = provisioning_uri(secret, user.username)
    return {"secret": secret, "otpauth_uri": uri, "qr": qr_data_uri(uri)}


@transaction.atomic
def confirm_enrolment(*, user, code):
    """Prove the app shows the right code; from now on sign-in asks for one.
    Returns the recovery codes, shown once."""
    device = TwoFactorDevice.objects.select_for_update().filter(user=user, confirmed_at__isnull=True).first()
    if device is None:
        raise BusinessConflictError({"detail": "اول کلید تازه بسازید."})
    step = _matching_step(_secret_of(device), clean_code(code), after_step=device.last_used_step)
    if step is None:
        raise BusinessRuleError({"code": "کد درست نیست؛ کد تازهٔ برنامه را وارد کنید."})
    device.confirmed_at = timezone.now()
    device.last_used_step = step
    device.save(update_fields=["confirmed_at", "last_used_step", "updated_at"])
    codes = _issue_recovery_codes(user)
    log_activity(actor=user, operation="two_factor.enabled", instance=user)
    return codes


def _check_second_factor(user, device, code):
    """True when `code` is a fresh authenticator code or an unused recovery
    code of this user; spends whichever it was."""
    cleaned = clean_code(code)
    if len(cleaned) == DIGITS and cleaned.isdigit():
        step = _matching_step(_secret_of(device), cleaned, after_step=device.last_used_step)
        if step is None:
            return False
        device.last_used_step = step
        device.save(update_fields=["last_used_step", "updated_at"])
        return True
    if len(cleaned) == 10:
        for row in user.two_factor_recovery_codes.select_for_update().filter(used_at__isnull=True):
            if _code_matches(cleaned, row.code_hash):
                row.used_at = timezone.now()
                row.save(update_fields=["used_at"])
                log_activity(actor=user, operation="two_factor.recovery_code_used", instance=user)
                return True
    return False


@transaction.atomic
def disable(*, user, password, code):
    """Turn it off: the password and a current code (or a recovery code)."""
    _require_password(user, password)
    device = TwoFactorDevice.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        raise BusinessConflictError({"detail": "ورود دومرحله‌ای روشن نیست."})
    if not _check_second_factor(user, device, code):
        raise BusinessRuleError({"code": "کد درست نیست."})
    device.delete()
    user.two_factor_recovery_codes.all().delete()
    log_activity(actor=user, operation="two_factor.disabled", instance=user)


@transaction.atomic
def renew_recovery_codes(*, user, password, code):
    _require_password(user, password)
    device = TwoFactorDevice.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        raise BusinessConflictError({"detail": "ورود دومرحله‌ای روشن نیست."})
    if not _check_second_factor(user, device, code):
        raise BusinessRuleError({"code": "کد درست نیست."})
    codes = _issue_recovery_codes(user)
    log_activity(actor=user, operation="two_factor.recovery_codes_renewed", instance=user)
    return codes


# --- sign-in ----------------------------------------------------------------------

@transaction.atomic
def verify_sign_in(*, user, code):
    """The second step of signing in. True when `code` is accepted."""
    device = TwoFactorDevice.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
    if device is None:
        return True
    return _check_second_factor(user, device, code)


# --- administration ---------------------------------------------------------------

@transaction.atomic
def reset_two_factor(*, actor, target):
    """Take two-factor sign-in off someone else's account — a lost phone.

    The Platform Admin only, and never their own account from here: that is
    the host command's job, so losing one phone cannot be fixed by whoever
    holds the session it protects.
    """
    if actor is None or actor.role != User.Role.PLATFORM_ADMIN or not actor.is_active:
        raise BusinessPermissionDenied("بازنشانی ورود دومرحله‌ای فقط با مدیر پلتفرم است.")
    if actor.pk == target.pk:
        raise BusinessRuleError({"detail": "ورود دومرحله‌ای خودتان را از صفحهٔ «امنیت» خاموش کنید."})
    deleted, _ = TwoFactorDevice.objects.filter(user=target).delete()
    target.two_factor_recovery_codes.all().delete()
    if not deleted:
        raise BusinessConflictError({"detail": "ورود دومرحله‌ای این کاربر روشن نیست."})
    log_activity(actor=actor, operation="two_factor.reset", instance=target)
