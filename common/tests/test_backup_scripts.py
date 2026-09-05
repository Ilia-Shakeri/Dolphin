import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from django.test import SimpleTestCase
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup-postgres.ps1"
CONTAINER_BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup-postgres.sh"
RESTORE_SCRIPT = REPO_ROOT / "scripts" / "verify-postgres-restore.ps1"
CONTAINER_RESTORE_SCRIPT = REPO_ROOT / "scripts" / "verify-postgres-restore.sh"
RESTORE_SCHEMA = REPO_ROOT / "scripts" / "verify-postgres-schema.sql"
RESTORE_COMPOSE = REPO_ROOT / "compose.restore-verify.yml"
DEPLOYMENT_RUNBOOK = REPO_ROOT / "docs" / "ops" / "DOLPHIN_DEPLOYMENT_RUNBOOK.md"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")


def runbook_section(former_filename):
    """One former ops doc's own content, isolated from the merged runbook.

    DEPLOYMENT.md, ROLLBACK.md, RELEASE_CHECKLIST.md, BACKUP_RESTORE.md and
    TLS.md were merged into this one file (2026-09-01); each still occupies
    one contiguous block, marked by the `*(from `docs/ops/<name>`)*` note this
    merge inserted under its heading. Slicing that block back out keeps every
    `.index()`-based ordering assertion below meaningful — searching the whole
    5000-line file instead would find the *first* match anywhere in it, not
    the one inside the section a check actually means to test.
    """
    text = DEPLOYMENT_RUNBOOK.read_text(encoding="utf-8")
    marker = f"*(from `docs/ops/{former_filename}`)*"
    start = text.index(marker) + len(marker)
    next_marker = text.find("*(from `docs/ops/", start)
    end = next_marker if next_marker != -1 else len(text)
    return text[start:end]


class BackupScriptTests(SimpleTestCase):
    def _run_script(self, script, *arguments):
        command = [POWERSHELL, "-NoProfile", "-NonInteractive"]
        if os.name == "nt":
            command.extend(["-ExecutionPolicy", "Bypass"])
        command.extend(["-File", str(script), *map(str, arguments)])
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_scripts_have_guarded_file_and_database_targets(self):
        backup = BACKUP_SCRIPT.read_text(encoding="utf-8")
        restore = RESTORE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("DOLPHIN_BACKUP_ROOT_V1", backup)
        # 2026-09-05 — `$sentinel.Path` was the multi-sentinel loop variable
        # this simplified to a single `$sentinelPath` when the Kariz/FrooshBin
        # fallback sentinels were removed (see the CHANGELOG `[2.0.0]` entry).
        self.assertIn("Get-Content -LiteralPath $sentinelPath -Raw", backup)
        self.assertIn("pg_restore", backup)
        self.assertIn("Get-FileHash -LiteralPath $tempDumpPath -Algorithm SHA256", backup)
        self.assertIn("Move-Item -LiteralPath $tempDumpPath", backup)
        self.assertIn("Get-ChildItem -LiteralPath $Root -File", backup)
        self.assertIn("Get-FileHash -LiteralPath $candidate.FullName -Algorithm SHA256", backup)
        self.assertIn("$candidateHash -cne $expectedHash", backup)
        self.assertIn("Remove-Item -LiteralPath $candidate.FullName", backup)
        self.assertIn("Get-Command $Name -CommandType Application", backup)
        self.assertNotIn("Remove-Item -Recurse", backup)
        self.assertNotIn("[string]$Password", backup)
        self.assertIn("DatabaseName must be a plain database name", backup)
        self.assertIn("BackupRoot cannot be a link or reparse point.", backup)

        self.assertIn("[Net.IPAddress]::IsLoopback", restore)
        self.assertIn("$TargetPort -le 1024 -or $TargetPort -eq 5432", restore)
        self.assertIn('"dolphin_restore_verify_$runToken"', restore)
        self.assertIn("Backup checksum verification failed.", restore)
        self.assertIn("Disposable target database already exists.", restore)
        self.assertIn("} finally {", restore)
        self.assertIn('Get-PostgresTool -Name "dropdb"', restore)
        self.assertIn("Get-Command $Name -CommandType Application", restore)
        self.assertIn("[IO.FileAttributes]::ReparsePoint", restore)
        self.assertNotIn("Remove-Item -Recurse", restore)
        self.assertNotIn("[string]$Password", restore)
        self.assertIn("BackupRoot cannot be a link or reparse point.", restore)

    def test_container_backup_is_guarded_and_secret_safe(self):
        backup = CONTAINER_BACKUP_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('POSTGRES_BACKUP_ROOT must be the fixed /backups mount.', backup)
        self.assertIn("DOLPHIN_BACKUP_ROOT_V1", backup)
        self.assertIn("umask 077", backup)
        self.assertIn('export PGPASSWORD="$POSTGRES_BACKUP_PASSWORD"', backup)
        self.assertIn("pg_dump", backup)
        self.assertIn("pg_restore --list", backup)
        self.assertIn("sha256sum", backup)
        self.assertIn("--no-password", backup)
        self.assertIn("-mindepth 1", backup)
        self.assertIn("-maxdepth 1", backup)
        self.assertIn("candidate_hash", backup)
        self.assertIn('rm -f -- "$candidate"', backup)
        self.assertIn('rm -f -- "$checksum_path"', backup)
        self.assertIn('lock_dir="$POSTGRES_BACKUP_ROOT/.dolphin-backup.lock"', backup)
        self.assertIn('mkdir -m 0700 "$lock_dir"', backup)
        self.assertIn('rmdir "$lock_dir"', backup)
        self.assertIn("Another backup run or a stale exact backup lock exists.", backup)
        self.assertNotIn("rm -r", backup)
        self.assertNotIn("rm -rf", backup)
        self.assertNotIn("eval ", backup)
        self.assertNotIn("POSTGRES_INIT_PASSWORD", backup)
        self.assertNotIn("POSTGRES_MIGRATION_PASSWORD", backup)
        self.assertNotIn("POSTGRES_APP_PASSWORD", backup)

    def test_container_restore_is_isolated_and_has_no_business_target(self):
        restore = CONTAINER_RESTORE_SCRIPT.read_text(encoding="utf-8")
        compose = yaml.safe_load(RESTORE_COMPOSE.read_text(encoding="utf-8"))
        self.assertEqual(set(compose["services"]), {"restore-verify"})
        service = compose["services"]["restore-verify"]
        self.assertEqual(service["profiles"], ["restore-verify"])
        self.assertEqual(service["network_mode"], "none")
        self.assertNotIn("networks", service)
        self.assertNotIn("depends_on", service)
        self.assertNotIn("ports", service)
        self.assertNotIn("expose", service)
        self.assertEqual(service["environment"], {"HOME": "/tmp"})
        self.assertEqual(service["user"], "postgres")
        self.assertTrue(service["read_only"])
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", service["security_opt"])
        self.assertEqual(
            service["entrypoint"], ["sh", "/ops/verify-postgres-restore.sh"]
        )
        self.assertIn("backup_data:/backups:ro", service["volumes"])
        self.assertFalse(any("postgres_data" in str(item) for item in service["volumes"]))
        self.assertIn("POSTGRES_RESTORE_TMPFS_SIZE_BYTES", service["tmpfs"][0])
        self.assertTrue(compose["volumes"]["backup_data"]["external"])

        self.assertIn("Pass one exact Dolphin archive name.", restore)
        self.assertIn("DOLPHIN_BACKUP_ROOT_V1", restore)
        self.assertIn("sha256sum", restore)
        self.assertIn("pg_restore --list", restore)
        self.assertIn("--auth-local=trust", restore)
        self.assertIn("--auth-host=reject", restore)
        self.assertIn("listen_addresses=''", restore)
        self.assertIn("--single-transaction", restore)
        self.assertIn("--file=\"$verification_sql\"", restore)
        self.assertNotIn("POSTGRES_HOST", restore)
        self.assertNotIn("PGPASSWORD", restore)
        self.assertNotIn("rm -r", restore)
        self.assertNotIn("rm -rf", restore)
        self.assertNotIn("dropdb", restore)

    def test_script_filename_contract_is_exact(self):
        """2026-09-05 — the `frooshbin`/`kariz` alternation this test used to
        require is gone on purpose (product-owner decision to remove every
        remaining trace of the two earlier project names): a backup archive
        or checksum file still named under either old prefix needs a
        one-time manual rename before this script's next run — see the
        migration note in docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md."""
        backup = BACKUP_SCRIPT.read_text(encoding="utf-8")
        restore = RESTORE_SCRIPT.read_text(encoding="utf-8")
        for script in (backup, restore):
            self.assertIn("dolphin", script)
            self.assertNotIn("frooshbin", script)
            self.assertNotIn("kariz", script)
            self.assertIn("[0-9]{8}T[0-9]{6}Z-", script)
            self.assertIn("[0-9a-f]{32}", script)
        self.assertIn('"$hash  $backupName`n"', backup)
        self.assertIn('"$resolvedBackupFile.sha256"', restore)

    def test_restore_verifies_core_schema_in_one_boolean_query(self):
        restore = RESTORE_SCRIPT.read_text(encoding="utf-8")
        container_restore = CONTAINER_RESTORE_SCRIPT.read_text(encoding="utf-8")
        schema = RESTORE_SCHEMA.read_text(encoding="utf-8")
        self.assertIn('"verify-postgres-schema.sql"', restore)
        self.assertIn("/ops/verify-postgres-schema.sql", container_restore)
        for table in (
            "accounts_user",
            "auditlog_activitylog",
            "sales_customer",
            "sales_customerphone",
            "sales_lead",
            "sales_leadassignmenthistory",
            "sales_interaction",
            "sales_product",
            "sales_productcategory",
            "sales_sale",
            "sales_salesdocument",
            "sales_postalstatushistory",
            "aftersales_aftersalesrequest",
            "aftersales_aftersaleshistory",
            "communications_inboundsms",
        ):
            with self.subTest(table=table):
                self.assertIn(f"to_regclass('public.{table}') IS NOT NULL", schema)

        for migration in (
            "0003_after_sales_foundation",
            "0002_activitylog_role_snapshots",
            "0013_product_barcode_product_brand_productcategory_and_more",
            "0001_after_sales_foundation",
            "0001_initial",
        ):
            with self.subTest(migration=migration):
                self.assertIn(migration, schema)

        for constraint in (
            "accounts_user_role_valid",
            "accounts_user_workstream_valid",
            "accounts_user_elevated_workstream_sales",
            "after_sales_subject_nonblank",
            "after_sales_description_nonblank",
            "after_sales_status_nonblank",
            "after_sales_history_event_valid",
            "customer_phone_normalized_shape",
            "interaction_direction_valid",
            "interaction_outcome_nonblank",
            "lead_assignment_fields_consistent",
            "product_price_positive",
            "product_barcode_shape",
            "product_category_code_shape",
            "product_category_name_nonblank",
            "product_category_normalized_name_nonblank",
            "sale_quantity_positive",
            "sale_total_non_negative",
            "sale_unit_price_non_negative",
            "sale_status_valid",
            "sale_product_snapshot_pair",
            "sale_product_total_matches_snapshot",
        ):
            with self.subTest(constraint=constraint):
                self.assertIn(constraint, schema)

        for index_name, column, predicate in (
            ("uniq_active_normalized_phone", "normalized_phone", "is_active"),
            (
                "uniq_active_primary_phone",
                "customer_id",
                "is_activeANDis_primary",
            ),
            ("uniq_product_nonblank_barcode", "barcode", ""),
        ):
            with self.subTest(index=index_name):
                self.assertIn(index_name, schema)
                self.assertIn(f"= '{column}'", schema)
                if predicate:
                    self.assertIn(f"= '{predicate}'", schema)
        self.assertIn("regexp_replace(", schema)
        self.assertIn("IN ('code', 'normalized_name')", schema)
        self.assertEqual(schema.count("AS schema_contract_ok \\gset"), 1)
        self.assertEqual(restore.count("$verificationOutput = & $psql"), 1)
        self.assertIn("\\if :schema_contract_ok", schema)
        self.assertIn("SELECT 1;", schema)
        # `\quit 6` used to stand here, but psql's `\quit` takes no argument and
        # exits 0, so the verifier announced a failed schema contract and then
        # reported success. Raising is what actually fails the restore check.
        self.assertIn("RAISE EXCEPTION 'PostgreSQL schema contract failed.'", schema)
        self.assertNotIn("THEN 1 ELSE 0 END;", schema)
        self.assertIn("FROM pg_constraint", schema)
        self.assertIn("JOIN pg_index", schema)
        self.assertIn("index_info.indisunique", schema)
        self.assertNotIn("SELECT *", schema.upper())

    def test_ops_order_and_rollback_contracts_match_the_stack(self):
        # DEPLOYMENT.md, ROLLBACK.md, RELEASE_CHECKLIST.md, BACKUP_RESTORE.md and
        # TLS.md were merged into DOLPHIN_DEPLOYMENT_RUNBOOK.md (2026-09-01, one
        # ops doc per direct product-owner decision); runbook_section() isolates
        # each former file's own text so every `.index()`-based ordering check
        # below still proves the same thing it always did.
        deployment = runbook_section("DEPLOYMENT.md")
        rollback = runbook_section("ROLLBACK.md")
        checklist = runbook_section("RELEASE_CHECKLIST.md")
        backup_restore = runbook_section("BACKUP_RESTORE.md")
        tls = runbook_section("TLS.md")

        current_recovery = deployment.index("## Current-compatible write-stop and recovery point")
        target_preflight = deployment.index("## Target preflight")
        candidate_pull = deployment.index("docker compose pull")
        self.assertLess(current_recovery, target_preflight)
        self.assertLess(
            deployment.index(
                "--profile backup run --rm -e POSTGRES_BACKUP_RETENTION_DAYS=0"
            ),
            candidate_pull,
        )
        recovery_gate = deployment.index("## Recovery point gate")
        bootstrap_command = deployment.index("docker compose run --rm db-bootstrap")
        self.assertLess(recovery_gate, bootstrap_command)
        self.assertIn("--profile backup run --rm -e POSTGRES_BACKUP_RETENTION_DAYS=0", deployment)
        self.assertIn("compose.restore-verify.yml", deployment)
        self.assertIn("all four database secrets", deployment)
        self.assertIn("All seven base Compose services", deployment)
        self.assertIn("spectacular --validate --fail-on-warn", deployment)
        self.assertIn("spectacular --validate --fail-on-warn", checklist)
        self.assertIn("Current-compatible write-stop, backup, and disposable restore", checklist)
        self.assertIn("DOLPHIN_COMPOSE_PROJECT_NAME", deployment)
        self.assertIn("DOLPHIN_COMPOSE_PROJECT_NAME", rollback)
        self.assertIn("DOLPHIN_COMPOSE_PROJECT_NAME", checklist)
        self.assertIn(
            "docker compose -f compose.yml -f compose.write-stop.yml up -d --no-build",
            deployment,
        )

        safe_stop = deployment.index("## Safe full-stack stop and same-release restart")
        stop_nginx = deployment.index("stop --timeout 30 nginx", safe_stop)
        stop_web = deployment.index("stop --timeout 60 web", safe_stop)
        stop_db = deployment.index("stop --timeout 120 db", safe_stop)
        start_db = deployment.index("--wait db", stop_db)
        start_web = deployment.index("--wait web", start_db)
        start_nginx = deployment.index("--wait nginx", start_web)
        self.assertLess(stop_nginx, stop_web)
        self.assertLess(stop_web, stop_db)
        self.assertLess(stop_db, start_db)
        self.assertLess(start_db, start_web)
        self.assertLess(start_web, start_nginx)
        safe_stop_text = deployment[safe_stop:]
        self.assertIn("$restoreProjectName", safe_stop_text)
        self.assertIn(
            "ps --all db-bootstrap migrate db-finalize backup",
            safe_stop_text,
        )
        self.assertIn("restore-verify $approvedArchive", safe_stop_text)
        self.assertNotIn("docker compose down", safe_stop_text)

        static_refresh = rollback.index("collectstatic --clear --noinput")
        web_recreate = rollback.index("--force-recreate --wait web")
        web_health_failure = rollback.index("Prior application failed its health gate.")
        nginx_recreate = rollback.index(
            "--force-recreate nginx", web_health_failure
        )
        self.assertLess(static_refresh, web_recreate)
        self.assertLess(web_recreate, web_health_failure)
        self.assertLess(web_health_failure, nginx_recreate)
        self.assertIn("--force-recreate --wait web", rollback)
        self.assertIn("durable deployment input", rollback)
        self.assertIn("--project-name $approvedProjectName", rollback)
        self.assertIn("--env-file $approvedProtectedEnv", rollback)
        self.assertIn("stop --timeout 30 nginx", rollback)
        self.assertIn("### Edge/config-only rollback", rollback)
        edge_rollback = rollback[rollback.index("### Edge/config-only rollback"):]
        self.assertIn("$priorCompose", edge_rollback)
        self.assertIn("$priorWriteStop", edge_rollback)
        self.assertIn("--no-deps --force-recreate nginx", edge_rollback)
        self.assertIn("recreate only `nginx`", edge_rollback)
        self.assertIn("# dolphin-write-stop: on", edge_rollback)
        self.assertNotIn("migrate python manage.py migrate", edge_rollback)
        self.assertIn("/backups/.dolphin-backup.lock", backup_restore)
        self.assertIn("ps --all backup", backup_restore)
        self.assertIn("rmdir /backups/.dolphin-backup.lock", backup_restore)
        self.assertNotIn("rm -rf /backups/.dolphin-backup.lock", backup_restore)
        self.assertNotIn("docker compose build", checklist)
        self.assertNotIn("docker compose build", tls)
        self.assertIn("docker compose pull", checklist)

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_powershell_parser_accepts_both_scripts(self):
        for script in (BACKUP_SCRIPT, RESTORE_SCRIPT):
            with self.subTest(script=script.name):
                escaped_path = str(script).replace("'", "''")
                parser_command = (
                    "$tokens = $null; $errors = $null; "
                    f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}', "
                    "[ref]$tokens, [ref]$errors) | Out-Null; "
                    "if ($errors.Count -gt 0) { exit 1 }"
                )
                result = subprocess.run(
                    [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", parser_command],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_backup_refuses_root_without_sentinel_before_tool_lookup(self):
        with tempfile.TemporaryDirectory() as backup_root:
            result = self._run_script(
                BACKUP_SCRIPT,
                "-BackupRoot",
                backup_root,
                "-DatabaseHost",
                "127.0.0.1",
                "-DatabasePort",
                "5432",
                "-DatabaseName",
                "dolphin",
                "-DatabaseUser",
                "dolphin",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sentinel", (result.stdout + result.stderr).lower())

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_backup_refuses_connection_string_before_tool_lookup(self):
        with tempfile.TemporaryDirectory() as backup_root:
            root = Path(backup_root)
            (root / ".dolphin-backup-root").write_text("DOLPHIN_BACKUP_ROOT_V1\n", encoding="ascii")
            result = self._run_script(
                BACKUP_SCRIPT,
                "-BackupRoot",
                root,
                "-DatabaseHost",
                "127.0.0.1",
                "-DatabasePort",
                "5432",
                "-DatabaseName",
                "postgresql://invalid/db",
                "-DatabaseUser",
                "dolphin",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("connection string", (result.stdout + result.stderr).lower())

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_backup_rejects_an_invalid_dolphin_sentinel_value(self):
        with tempfile.TemporaryDirectory() as backup_root:
            root = Path(backup_root)
            (root / ".dolphin-backup-root").write_text("bad\n", encoding="ascii")
            result = self._run_script(
                BACKUP_SCRIPT,
                "-BackupRoot",
                root,
                "-DatabaseHost",
                "127.0.0.1",
                "-DatabasePort",
                "5432",
                "-DatabaseName",
                "dolphin",
                "-DatabaseUser",
                "dolphin_backup",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sentinel value is invalid", (result.stdout + result.stderr).lower())

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_a_stray_old_named_sentinel_is_ignored_not_trusted(self):
        """2026-09-05 — the `.frooshbin-backup-root`/`.kariz-backup-root`
        fallback this behaviour used to have is gone on purpose (product-
        owner decision to remove every remaining Kariz/FrooshBin trace):
        only `.dolphin-backup-root` is ever consulted now, so a leftover
        file under either old name is simply invisible to this script — its
        own content, valid or not, can no longer substitute for the real
        sentinel."""
        with tempfile.TemporaryDirectory() as backup_root:
            root = Path(backup_root)
            (root / ".frooshbin-backup-root").write_text(
                "FROOSHBIN_BACKUP_ROOT_V1\n", encoding="ascii"
            )
            result = self._run_script(
                BACKUP_SCRIPT,
                "-BackupRoot",
                root,
                "-DatabaseHost",
                "127.0.0.1",
                "-DatabasePort",
                "5432",
                "-DatabaseName",
                "dolphin",
                "-DatabaseUser",
                "dolphin_backup",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sentinel is missing", (result.stdout + result.stderr).lower())

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_restore_refuses_unsafe_target_before_backup_or_tool_lookup(self):
        with tempfile.TemporaryDirectory() as backup_root:
            root = Path(backup_root)
            (root / ".dolphin-backup-root").write_text("DOLPHIN_BACKUP_ROOT_V1\n", encoding="ascii")
            unsafe_cases = (
                ("192.0.2.10", "55432", "loopback"),
                ("127.0.0.1", "5432", "5432"),
                ("127.0.0.1", "1024", "high disposable port"),
            )
            for host, port, message in unsafe_cases:
                with self.subTest(host=host, port=port):
                    result = self._run_script(
                        RESTORE_SCRIPT,
                        "-BackupRoot",
                        root,
                        "-BackupFile",
                        root / "missing.dump",
                        "-TargetHost",
                        host,
                        "-TargetPort",
                        port,
                        "-DatabaseUser",
                        "dolphin",
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, (result.stdout + result.stderr).lower())

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_restore_refuses_bad_checksum_before_tool_lookup(self):
        with tempfile.TemporaryDirectory() as backup_root:
            root = Path(backup_root)
            (root / ".dolphin-backup-root").write_text("DOLPHIN_BACKUP_ROOT_V1\n", encoding="ascii")
            backup_name = "dolphin-pg-20260809T010203Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.dump"
            backup_file = root / backup_name
            backup_file.write_bytes(b"not-a-database-backup")
            (root / f"{backup_name}.sha256").write_text(
                f"{'0' * 64}  {backup_name}\n",
                encoding="ascii",
            )
            result = self._run_script(
                RESTORE_SCRIPT,
                "-BackupRoot",
                root,
                "-BackupFile",
                backup_file,
                "-TargetHost",
                "127.0.0.1",
                "-TargetPort",
                "55432",
                "-DatabaseUser",
                "dolphin",
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", (result.stdout + result.stderr).lower())
