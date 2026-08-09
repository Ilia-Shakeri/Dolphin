import os
from pathlib import Path
import shutil
import subprocess
import unittest

from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "scripts" / "test-postgres.ps1"
PRIVILEGE_PROOF = ROOT / "scripts" / "verify-postgres-privileges.sql"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")


class PostgresHarnessContractTests(SimpleTestCase):
    def test_harness_is_bound_to_one_fresh_loopback_cluster(self):
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("kariz-pgtest-$runToken", source)
        self.assertIn("[Net.IPAddress]::Loopback", source)
        self.assertIn('$port -eq 5432', source)
        self.assertIn('-A trust --no-locale --encoding=UTF8', source)
        self.assertIn('-h 127.0.0.1', source)
        self.assertIn('config.postgres_test_settings', source)
        self.assertIn('config.postgres_contract_settings', source)
        self.assertNotIn("env_file", source)
        self.assertNotIn("docker compose", source.lower())
        self.assertNotIn("POSTGRES_DATA_VOLUME", source)
        self.assertNotIn("POSTGRES_BACKUP_VOLUME", source)

    def test_harness_runs_upgrade_races_acl_dump_and_rollback_proofs(self):
        source = HARNESS.read_text(encoding="utf-8")
        self.assertIn("manage.py test", source.replace("$managePath", "manage.py"))
        self.assertEqual(source.count("& $bash $bootstrapPath"), 3)
        self.assertIn("verify-postgres-schema.sql", source)
        self.assertIn("verify-postgres-privileges.sql", source)
        self.assertIn("UPDATE auditlog_activitylog", source)
        self.assertIn("DELETE FROM sales_interaction", source)
        self.assertIn("SELECT public.kariz_contract_probe()", source)
        self.assertIn("kariz_future_table", source)
        self.assertIn("--format=custom", source)
        self.assertIn("kariz_rollback_probe", source)
        self.assertIn("did not roll back after injected failure", source)

    def test_privilege_proof_checks_exact_runtime_and_backup_denials(self):
        proof = PRIVILEGE_PROOF.read_text(encoding="utf-8")
        for role in ("migration_user", "app_user", "backup_user"):
            self.assertIn(f":'{role}'", proof)
        for table in (
            "accounts_user",
            "django_session",
            "auditlog_activitylog",
            "sales_interaction",
            "sales_leadassignmenthistory",
            "django_admin_log",
            "django_migrations",
        ):
            self.assertIn(f"'{table}'", proof)
        self.assertIn("NOT has_schema_privilege(:'app_user', 'public', 'CREATE')", proof)
        self.assertIn("NOT has_function_privilege(:'app_user'", proof)
        self.assertIn("NOT has_function_privilege(:'backup_user'", proof)
        self.assertIn("NOT rolbypassrls", proof)
        self.assertIn("\\quit 5", proof)

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_harness_has_valid_powershell_syntax(self):
        escaped_path = str(HARNESS).replace("'", "''")
        parser_command = (
            "$tokens = $null; $errors = $null; "
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}', "
            "[ref]$tokens, [ref]$errors) | Out-Null; "
            "if ($errors.Count -gt 0) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
        )
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", parser_command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
