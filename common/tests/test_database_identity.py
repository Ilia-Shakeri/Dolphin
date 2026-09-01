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
    def test_the_preflight_accepts_any_safe_name(self):
        """The wrapper no longer gates on what the database is called.

        It used to refuse anything without a brand prefix, which protected
        nothing and stopped a staging deployment whose roles already existed.
        Identifier safety, role distinctness and password strength are all
        enforced in config/production_env.py before Django starts.
        """
        for values in (
            {"POSTGRES_DB": "dolphin", "POSTGRES_USER": "dolphin_init"},
            {"POSTGRES_DB": "dolphin", "POSTGRES_USER": "dolphin_init"},
            {"POSTGRES_DB": "dolphin", "POSTGRES_USER": "dolphin_init"},
            {"POSTGRES_DB": "crm", "POSTGRES_USER": "crm_init"},
        ):
            with self.subTest(values=values):
                result = subprocess.run(
                    [BASH, "scripts/postgres-entrypoint.sh", "--dolphin-preflight-only"],
                    cwd=ROOT,
                    env={**os.environ, **values},
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

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
            "POSTGRES_DB=frooshbin",
            "POSTGRES_DB=kariz",
            "test_frooshbin_",
            "contract_frooshbin_",
            "restore_frooshbin_",
            "frooshbin_test_",
            "frooshbin_migration_",
            "frooshbin_app_",
            '"kariz-pgtest-',
        )
        offenders = []
        for path in files:
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in source:
                    offenders.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(offenders, [])

    def test_new_backup_writer_uses_only_dolphin_name(self):
        shell = (ROOT / "scripts" / "backup-postgres.sh").read_text(encoding="utf-8")
        powershell = (ROOT / "scripts" / "backup-postgres.ps1").read_text(encoding="utf-8")
        self.assertIn('backup_name="dolphin-pg-', shell)
        self.assertIn('$backupName = "dolphin-pg-', powershell)
        self.assertNotIn('backup_name="frooshbin-pg-', shell)
        self.assertNotIn('$backupName = "frooshbin-pg-', powershell)

    def test_bootstrap_only_touches_roles_this_stack_manages(self):
        """The real guard: an existing role that is not ours is never taken over.

        The brand gate that sat beside it is gone — a role's name is the
        deployment's choice — but the management-comment check is what stops the
        script adopting somebody else's role, so it stays, and it still accepts
        the comment an earlier release wrote.
        """
        source = (ROOT / "scripts" / "bootstrap-postgres.sh").read_text(encoding="utf-8")
        for role in ("migration", "app", "backup"):
            self.assertIn(f":'{role}_is_legacy' = '0' AND NOT EXISTS", source)
            self.assertIn(
                f"Dolphin managed {role if role != 'app' else 'application'} role v1", source
            )
        self.assertIn("allow_legacy_comments", source)
        # No brand gate remains in the script.
        self.assertNotIn("require_role_identity", source)
        self.assertNotIn("require_database_identity", source)
        self.assertNotIn("ALLOW_LEGACY=", source)

    def test_the_noninteractive_password_path_needs_a_disposable_proof_database(self):
        """The one place a name still has to match an exact shape.

        Passwords may only be supplied non-interactively against a throwaway
        proof database whose name carries 32 hex characters — a production
        database can never match it, which is what keeps that path out of a real
        deployment. This is a safety rule about disposability, not about
        branding, so it survives the removal of the brand gate.
        """
        source = (ROOT / "scripts" / "bootstrap-postgres.sh").read_text(encoding="utf-8")
        database_pattern = "^(test|contract|restore)_dolphin_[0-9a-f]{32}$"
        role_pattern = "^dolphin_(migration|app|backup)_[0-9a-f]{32}$"
        self.assertIn(database_pattern, source)
        self.assertIn(role_pattern, source)
        # Defined once and actually applied, rather than merely present.
        self.assertIn('grep -Eq "$EPHEMERAL_DB_PATTERN"', source)
        self.assertIn('grep -Eq "$EPHEMERAL_ROLE_PATTERN"', source)
