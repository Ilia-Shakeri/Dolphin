"""Compute a PostgreSQL SCRAM-SHA-256 password verifier on the client.

psql's interactive ``\\password`` meta-command hashes a role password on the
client, so the plaintext never reaches the server, the wire, or the server log.
That meta-command reads the terminal device directly and therefore cannot be
driven from a pipe on every platform. This script performs exactly the same
client-side derivation (RFC 5802 / RFC 7677, as PostgreSQL stores it in
``pg_authid.rolpassword``) so a caller that cannot use ``\\password`` can issue
``ALTER ROLE ... PASSWORD '<verifier>'`` with the identical guarantee.

Only ``scripts/bootstrap-postgres.sh`` calls this, and only on its explicitly
opted-in, disposable proof path; the production bootstrap keeps ``\\password``.

The password is read from standard input, never from a command-line argument,
so it cannot appear in a process listing. Only printable ASCII passwords are
accepted: SASLprep normalisation is not implemented here, and hashing a
different byte string than the server would expect must never happen silently.
"""

import base64
import hashlib
import hmac
import secrets
import sys


DIGEST_NAME = "sha256"
DEFAULT_ITERATIONS = 4096
SALT_LENGTH = 16
MINIMUM_ITERATIONS = 4096


class UnsupportedPassword(ValueError):
    """The password cannot be hashed without guessing at normalisation."""


def validate_password(password):
    """Accept only passwords SASLprep would leave byte-identical.

    Every character must be printable ASCII other than space. On that subset
    SASLprep is the identity mapping, so the verifier computed here is exactly
    the verifier the server derives during authentication. Anything else is
    refused rather than hashed under an assumption.
    """
    if not password:
        raise UnsupportedPassword("The role password must not be empty.")
    for character in password:
        if not 0x21 <= ord(character) <= 0x7E:
            raise UnsupportedPassword(
                "The role password must use printable ASCII without spaces; "
                "SASLprep normalisation is deliberately not implemented here."
            )
    return password


def scram_sha_256_verifier(password, salt=None, iterations=DEFAULT_ITERATIONS):
    """Return the ``SCRAM-SHA-256$...`` verifier string for one password."""
    validate_password(password)
    if iterations < MINIMUM_ITERATIONS:
        raise ValueError("SCRAM-SHA-256 iteration count is below the safe minimum.")
    if salt is None:
        salt = secrets.token_bytes(SALT_LENGTH)
    if len(salt) < SALT_LENGTH:
        raise ValueError("SCRAM-SHA-256 salt is too short.")

    salted_password = hashlib.pbkdf2_hmac(
        DIGEST_NAME, password.encode("ascii"), salt, iterations
    )
    client_key = hmac.new(salted_password, b"Client Key", DIGEST_NAME).digest()
    stored_key = hashlib.new(DIGEST_NAME, client_key).digest()
    server_key = hmac.new(salted_password, b"Server Key", DIGEST_NAME).digest()

    return "SCRAM-SHA-256${}:{}${}:{}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(stored_key).decode("ascii"),
        base64.b64encode(server_key).decode("ascii"),
    )


def read_password(stream):
    """Read one password from a binary stream, dropping the line terminator."""
    raw = stream.read()
    if raw.endswith(b"\r\n"):
        raw = raw[:-2]
    elif raw.endswith(b"\n"):
        raw = raw[:-1]
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise UnsupportedPassword(
            "The role password must be printable ASCII."
        ) from error


def main(argv):
    if len(argv) > 1:
        # A password passed as an argument would be visible to every other
        # process on the host, so refuse rather than accept it.
        sys.stderr.write("This helper reads the password from standard input only.\n")
        return 2
    try:
        password = read_password(sys.stdin.buffer)
        verifier = scram_sha_256_verifier(password)
    except (UnsupportedPassword, ValueError) as error:
        sys.stderr.write("{}\n".format(error))
        return 2
    sys.stdout.write(verifier)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
