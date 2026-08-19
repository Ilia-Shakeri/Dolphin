"""The PostgreSQL restore proof must fail closed.

The harness creates and then drops a second database, so the guards that decide
which names are acceptable are safety-critical. These tests are vendor-neutral:
they exercise the guard logic itself, not a live PostgreSQL server.
"""

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.postgres_restore_guard import (
    build_postgres_restore_database,
    is_ephemeral_restore_database,
)


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "test-postgres.ps1"
TOKEN = "0123456789abcdef0123456789abcdef"


def valid_environment(**overrides):
    environment = {
        "KARIZ_PG_RESTORE": "1",
        "KARIZ_PG_RESTORE_TOKEN": TOKEN,
        "KARIZ_PG_RESTORE_HOST": "127.0.0.1",
        "KARIZ_PG_RESTORE_PORT": "54321",
        "KARIZ_PG_RESTORE_NAME": f"restore_frooshbin_{TOKEN}",
        "KARIZ_PG_RESTORE_USER": f"frooshbin_app_{TOKEN}",
        "KARIZ_PG_RESTORE_PASSWORD": "restore-proof-secret-value",
    }
    environment.update(overrides)
    return environment


class EphemeralRestoreNameTests(SimpleTestCase):
    def test_accepts_only_the_exact_ephemeral_pattern(self):
        self.assertTrue(is_ephemeral_restore_database(f"restore_frooshbin_{TOKEN}"))

    def test_rejects_non_ephemeral_names(self):
        for name in (
            "postgres",
            "template0",
            "template1",
            "kariz",
            "kariz_production",
            "restore_frooshbin_",
            "restore_frooshbin_short",
            f"restore_frooshbin_{TOKEN}x",
            f"x_restore_frooshbin_{TOKEN}",
            f"restore_frooshbin_{TOKEN.upper()}",
            f"restore_frooshbin_{TOKEN}; DROP DATABASE kariz",
            "",
            None,
        ):
            with self.subTest(name=name):
                self.assertFalse(is_ephemeral_restore_database(name))


class RestoreSettingsGuardTests(SimpleTestCase):
    def test_valid_environment_builds_the_expected_connection(self):
        database = build_postgres_restore_database(valid_environment())
        self.assertEqual(database["NAME"], f"restore_frooshbin_{TOKEN}")
        self.assertEqual(database["USER"], f"frooshbin_app_{TOKEN}")
        self.assertEqual(database["HOST"], "127.0.0.1")
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")

    def test_requires_the_explicit_flag(self):
        with self.assertRaises(ImproperlyConfigured):
            build_postgres_restore_database(valid_environment(KARIZ_PG_RESTORE="0"))

    def test_rejects_non_loopback_host(self):
        for host in ("localhost", "10.0.0.5", "0.0.0.0", ""):
            with self.subTest(host=host):
                with self.assertRaises(ImproperlyConfigured):
                    build_postgres_restore_database(valid_environment(KARIZ_PG_RESTORE_HOST=host))

    def test_rejects_default_and_privileged_ports(self):
        for value in ("5432", "80", "1024", "not-a-port", ""):
            with self.subTest(port=value):
                with self.assertRaises(ImproperlyConfigured):
                    build_postgres_restore_database(valid_environment(KARIZ_PG_RESTORE_PORT=value))

    def test_rejects_a_database_outside_the_run_token(self):
        for name in ("postgres", "kariz", f"restore_frooshbin_{'f' * 32}", "restore_frooshbin_x"):
            with self.subTest(name=name):
                with self.assertRaises(ImproperlyConfigured):
                    build_postgres_restore_database(valid_environment(KARIZ_PG_RESTORE_NAME=name))

    def test_rejects_elevated_logins(self):
        # The restore proof exists to show the ordinary runtime login works, so
        # an elevated login must not be able to stand in for it.
        for user in (
            f"frooshbin_migration_{TOKEN}",
            f"kariz_backup_{TOKEN}",
            "frooshbin_test_admin",
            "postgres",
        ):
            with self.subTest(user=user):
                with self.assertRaises(ImproperlyConfigured):
                    build_postgres_restore_database(valid_environment(KARIZ_PG_RESTORE_USER=user))

    def test_rejects_weak_or_absent_secret(self):
        for password in ("", "short", "x" * 15):
            with self.subTest(password_length=len(password)):
                with self.assertRaises(ImproperlyConfigured):
                    build_postgres_restore_database(
                        valid_environment(KARIZ_PG_RESTORE_PASSWORD=password)
                    )


class HarnessRestoreContractTests(SimpleTestCase):
    """Static contract checks on the harness itself."""

    def setUp(self):
        self.source = HARNESS.read_text(encoding="utf-8")

    def test_restore_uses_native_pg_restore(self):
        self.assertIn("$pgRestore", self.source)
        self.assertIn("--exit-on-error", self.source)
        self.assertIn("--single-transaction", self.source)

    def test_restore_target_is_a_separate_database(self):
        self.assertIn('$restoreDatabaseName = "restore_frooshbin_$runToken"', self.source)
        self.assertIn("Restore target must be a new, separate database.", self.source)

    def test_drop_is_guarded_by_the_ephemeral_name_check(self):
        self.assertIn("function Assert-EphemeralDatabaseName", self.source)
        # The only DROP DATABASE in the harness must be preceded by the guard.
        drop_index = self.source.index("DROP DATABASE")
        guard_index = self.source.rindex("Assert-EphemeralDatabaseName -Name $restoreDatabaseName", 0, drop_index)
        self.assertLess(guard_index, drop_index)
        self.assertEqual(self.source.count("DROP DATABASE"), 1)

    def test_guard_requires_the_run_token(self):
        self.assertIn("EndsWith($runToken", self.source)
        self.assertIn("^(test|contract|restore)_frooshbin_[a-f0-9]{32}$", self.source)

    def test_cleanup_runs_in_finally(self):
        # The outermost finally is the only one at column 0; nested helpers use
        # indented finally blocks.
        outer_finally = self.source.index("\n} finally {")
        self.assertLess(outer_finally, self.source.index("DROP DATABASE"))

    def test_restore_verifies_more_than_an_exit_status(self):
        for probe in (
            "Restored migration state does not match the source database",
            "Restored sentinel customer row is missing or altered",
            "Restored sentinel relationship across customer and phone is broken",
            "Application role gained cluster privileges through restore",
            "Restored database owner is not the migration role",
            "Application role inherited another role through restore",
        ):
            with self.subTest(probe=probe):
                self.assertIn(probe, self.source)
