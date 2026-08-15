import base64
import hashlib
import hmac
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "scripts" / "pg_scram_verifier.py"

_spec = importlib.util.spec_from_file_location("pg_scram_verifier", HELPER_PATH)
pg_scram_verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pg_scram_verifier)

VERIFIER_PATTERN = re.compile(
    r"^SCRAM-SHA-256\$(\d+):([A-Za-z0-9+/]+=*)\$([A-Za-z0-9+/]+=*):([A-Za-z0-9+/]+=*)$"
)


class ScramVerifierDerivationTests(SimpleTestCase):
    """The helper must reproduce psql `\\password`'s client-side derivation.

    Authoritative proof that the derivation matches PostgreSQL is the isolated
    harness run, where the server authenticates all three managed roles with
    passwords set through this helper. These tests pin the structure, the
    algorithm steps, and the fail-closed input handling.
    """

    password = "Migration!0123456789abcdef"
    salt = b"0123456789abcdef"

    def test_verifier_matches_the_postgresql_storage_format(self):
        verifier = pg_scram_verifier.scram_sha_256_verifier(self.password, salt=self.salt)
        match = VERIFIER_PATTERN.fullmatch(verifier)
        self.assertIsNotNone(match, verifier)
        self.assertEqual(int(match.group(1)), pg_scram_verifier.DEFAULT_ITERATIONS)
        self.assertEqual(base64.b64decode(match.group(2)), self.salt)
        self.assertEqual(len(base64.b64decode(match.group(3))), 32)
        self.assertEqual(len(base64.b64decode(match.group(4))), 32)

    def test_stored_and_server_keys_follow_rfc_5802(self):
        verifier = pg_scram_verifier.scram_sha_256_verifier(self.password, salt=self.salt)
        _, _, salt_b64, stored_b64, server_b64 = re.split(r"[$:]", verifier, maxsplit=4)

        salted = hashlib.pbkdf2_hmac(
            "sha256",
            self.password.encode("ascii"),
            base64.b64decode(salt_b64),
            pg_scram_verifier.DEFAULT_ITERATIONS,
        )
        client_key = hmac.new(salted, b"Client Key", "sha256").digest()
        self.assertEqual(
            base64.b64decode(stored_b64), hashlib.sha256(client_key).digest()
        )
        self.assertEqual(
            base64.b64decode(server_b64),
            hmac.new(salted, b"Server Key", "sha256").digest(),
        )

    def test_derivation_is_deterministic_for_a_fixed_salt_and_salted_otherwise(self):
        first = pg_scram_verifier.scram_sha_256_verifier(self.password, salt=self.salt)
        self.assertEqual(
            first, pg_scram_verifier.scram_sha_256_verifier(self.password, salt=self.salt)
        )
        self.assertNotEqual(
            pg_scram_verifier.scram_sha_256_verifier(self.password),
            pg_scram_verifier.scram_sha_256_verifier(self.password),
        )

    def test_a_different_password_yields_a_different_verifier(self):
        self.assertNotEqual(
            pg_scram_verifier.scram_sha_256_verifier(self.password, salt=self.salt),
            pg_scram_verifier.scram_sha_256_verifier(
                self.password + "x", salt=self.salt
            ),
        )

    def test_iteration_count_and_salt_length_stay_at_or_above_the_safe_minimum(self):
        self.assertGreaterEqual(
            pg_scram_verifier.DEFAULT_ITERATIONS, pg_scram_verifier.MINIMUM_ITERATIONS
        )
        self.assertGreaterEqual(pg_scram_verifier.SALT_LENGTH, 16)
        with self.assertRaises(ValueError):
            pg_scram_verifier.scram_sha_256_verifier(
                self.password, salt=self.salt, iterations=1000
            )
        with self.assertRaises(ValueError):
            pg_scram_verifier.scram_sha_256_verifier(self.password, salt=b"short")


class ScramVerifierInputRefusalTests(SimpleTestCase):
    def test_passwords_needing_saslprep_are_refused_rather_than_guessed(self):
        for rejected in ("", "with space", "کاریز", "tab\tchar", "new\nline", "\x7f"):
            with self.subTest(password=rejected):
                with self.assertRaises(pg_scram_verifier.UnsupportedPassword):
                    pg_scram_verifier.scram_sha_256_verifier(rejected)


class ScramVerifierCommandLineTests(SimpleTestCase):
    def _run(self, argv=(), stdin=b""):
        return subprocess.run(
            [sys.executable, str(HELPER_PATH), *argv],
            input=stdin,
            capture_output=True,
        )

    def test_password_is_read_from_stdin_and_the_verifier_is_printed(self):
        result = self._run(stdin=b"Migration!0123456789abcdef\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNotNone(
            VERIFIER_PATTERN.fullmatch(result.stdout.decode("ascii").strip())
        )

    def test_a_password_given_as_an_argument_is_refused(self):
        # An argument would be visible in the host process listing.
        result = self._run(argv=("Migration!0123456789abcdef",))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")

    def test_the_plaintext_is_never_echoed_back_on_any_stream(self):
        password = b"Migration!0123456789abcdef"
        for stdin_value in (password, password + b"\n", b"with space", b"\xd8\xa7"):
            with self.subTest(stdin=stdin_value):
                result = self._run(stdin=stdin_value)
                self.assertNotIn(b"Migration", result.stdout + result.stderr)

    def test_unsupported_input_exits_non_zero_without_output(self):
        for stdin_value in (b"", b"with space", b"\xd8\xa7\xd8\xb3"):
            with self.subTest(stdin=stdin_value):
                result = self._run(stdin=stdin_value)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b"")
                self.assertNotEqual(result.stderr, b"")
