import os
from pathlib import Path
import shutil
import subprocess
import unittest

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "scripts" / "postgres-entrypoint.sh"
BASH = shutil.which("bash")
if os.name == "nt" and BASH and "system32" in BASH.lower():
    BASH = None


class DatabaseIdentityContractTests(SimpleTestCase):
    @unittest.skipUnless(BASH, "A POSIX shell is not installed.")
    def test_preinit_gate_accepts_fresh_and_explicit_legacy_names(self):
        cases = (
            ({"POSTGRES_DB": "frooshbin", "POSTGRES_USER": "frooshbin_init"}, 0),
            ({"POSTGRES_DB": "kariz", "POSTGRES_USER": "kariz_init"}, 64),
            (
                {
                    "POSTGRES_DB": "kariz",
                    "POSTGRES_USER": "kariz_init",
                    "FROOSHBIN_ALLOW_LEGACY_DB_IDENTITIES": "true",
                },
                0,
            ),
            (
                {
                    "POSTGRES_DB": "forooshbin",
                    "POSTGRES_USER": "forooshbin_init",
                    "FROOSHBIN_ALLOW_LEGACY_DB_IDENTITIES": "true",
                },
                0,
            ),
        )
        for values, expected in cases:
            with self.subTest(values=values):
                result = subprocess.run(
                    [BASH, "scripts/postgres-entrypoint.sh", "--frooshbin-preflight-only"],
                    cwd=ROOT,
                    env={**os.environ, **values},
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_fresh_database_identity_constructors_have_no_old_prefix(self):
        files = (
            ROOT / ".env.example",
            ROOT / "config" / "settings.py",
            ROOT / "config" / "test_settings.py",
            ROOT / "config" / "postgres_test_guard.py",
            ROOT / "config" / "postgres_contract_guard.py",
            ROOT / "config" / "postgres_restore_guard.py",
            ROOT / "scripts" / "test-postgres.ps1",
        )
        forbidden = (
            "POSTGRES_DB=forooshbin",
            "POSTGRES_DB=kariz",
            "test_forooshbin_",
            "contract_forooshbin_",
            "restore_forooshbin_",
            "forooshbin_test_",
            "forooshbin_migration_",
            "forooshbin_app_",
            '"kariz-pgtest-',
        )
        offenders = []
        for path in files:
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    offenders.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(offenders, [])

    def test_new_backup_writer_uses_only_frooshbin_name(self):
        shell = (ROOT / "scripts" / "backup-postgres.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts" / "backup-postgres.ps1").read_text(encoding="utf-8")
        self.assertIn('backup_name="frooshbin-pg-', shell)
        self.assertIn('$backupName = "frooshbin-pg-', powershell)
        self.assertNotIn('backup_name="kariz-pg-', shell)
        self.assertNotIn('$backupName = "kariz-pg-', powershell)

    def test_legacy_bootstrap_requires_existing_roles_then_normalizes_comments(self):
        source = (ROOT / "scripts" / "bootstrap-postgres.sh").read_text(
            encoding="utf-8"
        )
        for role in ("migration", "app", "backup"):
            self.assertIn(f":'{role}_is_legacy' = '0' AND NOT EXISTS", source)
            self.assertIn(f"FrooshBin managed {role if role != 'app' else 'application'} role v1", source)
        self.assertIn("allow_legacy_comments", source)

    def test_bootstrap_accepts_only_exact_frooshbin_proof_database_shape(self):
        source = (ROOT / "scripts" / "bootstrap-postgres.sh").read_text(
            encoding="utf-8"
        )
        pattern = "^(test|contract|restore)_frooshbin_[0-9a-f]{32}$"
        self.assertGreaterEqual(source.count(pattern), 2)
