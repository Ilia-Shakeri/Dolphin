"""`common.backups` and `/api/v1/backups/` — the panel's half of backup and
restore.

Product owner, 2026-09-20, stage two of two: «دانلود + بازگردانی کامل از
پنل». Stage one shipped in 2.9.0's predecessor; this is the rest.

The thing most worth proving here is a negative. This feature puts a
"replace the entire database" control on a web page, and the only reason
that is defensible is that **the web container still cannot do it**. So
these tests check, first and repeatedly, that nothing in this module
performs a backup or a restore — it writes a request file and stops — and
that every gate in front of that request holds:

* the feature (`panel_backup`, default off) and the Platform Admin role,
  enforced in the service layer and not only in the view;
* the archive name, which is matched by the URL router *and* re-matched in
  Python, so nothing that could leave the backup directory is ever joined
  to a path;
* the confirmation phrase, typed;
* the sentinel on the backup volume, so a missing or wrong mount reads as
  "unavailable" and never as "no backups yet";
* the uploaded file's format, checked before anything is spooled.

And two positives that matter as much:

* an agent that is not running produces a job that says `waiting` and then
  `expired` — never a success the panel invented;
* the request the agent will read carries the fields the agent actually
  parses, in the timestamp format it can compare.
"""

import json
import pathlib
import re
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.labels import OPERATION_LABELS
from auditlog.models import ActivityLog
from common import backups
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES, DEFAULT_OFF_FEATURES, FEATURE_DEPENDENCIES
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.models import BackupJob

PASSWORD = "Strong-pass-913!"

ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENT = (ROOT / "scripts" / "backup-agent.sh").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.yml").read_text(encoding="utf-8")
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")

def code_only(source, comment="#"):
    """The source with its comments stripped.

    These scans check what the file *does*, and every one of these files
    explains at length why it does not do the forbidden thing — so a scan
    over the raw text matches the explanation and fails. Docstrings are
    stripped too, for the same reason.
    """
    without_docstrings = re.sub(r'\"\"\".*?\"\"\"', "", source, flags=re.S)
    lines = []
    for line in without_docstrings.split(chr(10)):
        stripped = line.strip()
        if stripped.startswith(comment):
            continue
        lines.append(line)
    return chr(10).join(lines)


VALID_NAME = "dolphin-pg-20260920T101500Z-" + "a" * 32 + ".dump"
OTHER_NAME = "dolphin-pg-20260919T090000Z-" + "b" * 32 + ".dump"


def with_feature():
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) | {"panel_backup"},
        source="signed-manifest",
    )


def without_feature():
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - {"panel_backup"},
        source="signed-manifest",
    )


class BackupFixtures(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="backup.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN,
        )
        self.manager = User.objects.create_user(
            username="backup.manager", password=PASSWORD, role=User.Role.SALES_MANAGER,
        )
        self._temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._temp.name)
        self.backup_dir = self.root / "backups"
        self.spool_dir = self.root / "spool"
        self.backup_dir.mkdir()
        self.spool_dir.mkdir()
        (self.backup_dir / backups.SENTINEL_NAME).write_text(backups.SENTINEL_VALUE)
        self.addCleanup(self._temp.cleanup)

        self.settings_patch = override_settings(
            DOLPHIN_BACKUP_ROOT=str(self.backup_dir),
            DOLPHIN_RESTORE_SPOOL=str(self.spool_dir),
        )
        self.settings_patch.enable()
        self.addCleanup(self.settings_patch.disable)

        self.profile_patch = override_active_profile(with_feature())
        self.profile_patch.__enter__()
        self.addCleanup(self.profile_patch.__exit__, None, None, None)

    def write_archive(self, name=VALID_NAME, body=b"PGDMP fake archive", checksum=True):
        path = self.backup_dir / name
        path.write_bytes(body)
        if checksum:
            import hashlib

            digest = hashlib.sha256(body).hexdigest()
            (self.backup_dir / f"{name}.sha256").write_text(f"{digest}  {name}\n")
        return path

    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def upload(self, body=b"PGDMP" + b"\x00" * 64, name="backup.dump"):
        return SimpleUploadedFile(name, body, content_type="application/octet-stream")


class RegistryTests(BackupFixtures):
    def test_panel_backup_is_registered_and_depends_on_nothing(self):
        """A deployment with no sales module still has a database worth
        backing up."""
        self.assertEqual(FEATURE_DEPENDENCIES["panel_backup"], frozenset())

    def test_it_defaults_off(self):
        """Not a preference and not a convenience: enabling it and starting
        its agent means one authenticated request can replace the whole
        database."""
        self.assertIn("panel_backup", DEFAULT_OFF_FEATURES)


class GateTests(BackupFixtures):
    def test_the_service_refuses_when_the_feature_is_off(self):
        with override_active_profile(without_feature()):
            with self.assertRaises(BusinessPermissionDenied):
                backups.list_backups(actor=self.admin)

    def test_the_service_refuses_a_lower_role(self):
        """Enforced here and not only in the view, so a second caller
        cannot reach it without the check."""
        with self.assertRaises(BusinessPermissionDenied):
            backups.list_backups(actor=self.manager)
        with self.assertRaises(BusinessPermissionDenied):
            backups.request_backup(actor=self.manager)
        with self.assertRaises(BusinessPermissionDenied):
            backups.request_restore(actor=self.manager, upload=self.upload(), original_filename="x.dump")

    def test_available_is_false_without_the_feature(self):
        with override_active_profile(without_feature()):
            self.assertFalse(backups.available())

    def test_available_is_false_when_the_volume_is_not_mounted(self):
        with override_settings(DOLPHIN_BACKUP_ROOT=""):
            self.assertFalse(backups.available())

    def test_available_is_false_when_the_sentinel_is_missing(self):
        """A directory that is not the backup volume must read as
        unavailable, never as "no backups yet" — which would be
        reassuring and wrong."""
        (self.backup_dir / backups.SENTINEL_NAME).unlink()
        self.assertFalse(backups.available())

    def test_a_wrong_sentinel_value_is_refused_too(self):
        (self.backup_dir / backups.SENTINEL_NAME).write_text("SOMETHING_ELSE")
        self.assertFalse(backups.available())


class ArchiveNameTests(BackupFixtures):
    def test_only_the_one_shape_this_product_produces_is_accepted(self):
        for bad in (
            "../../etc/passwd",
            "..%2Fetc%2Fpasswd",
            "dolphin-pg-20260920T101500Z-shorttoken.dump",
            "evil.dump",
            VALID_NAME + ".sha256",
            "",
        ):
            with self.subTest(name=bad):
                with self.assertRaises(BusinessRuleError):
                    backups.open_backup(actor=self.admin, name=bad)

    def test_the_pattern_matches_the_one_the_shell_scripts_use(self):
        """Three places accept an archive name — this module, the backup
        script and the restore-verify script. They have to be the same
        pattern or one of them is a hole."""
        verify = (ROOT / "scripts" / "verify-postgres-restore.sh").read_text(encoding="utf-8")
        shell_pattern = "dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}"
        self.assertIn(shell_pattern, verify)
        self.assertIn(shell_pattern, (ROOT / "scripts" / "backup-postgres.sh").read_text(encoding="utf-8"))
        self.assertIn(shell_pattern, backups.ARCHIVE_NAME.pattern)

    def test_the_download_route_matches_it_too(self):
        """A name that could leave the directory is a 404 before any Python
        runs."""
        urls = (ROOT / "common" / "urls.py").read_text(encoding="utf-8")
        self.assertIn("dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}", urls)


class ListingTests(BackupFixtures):
    def test_an_empty_volume_lists_nothing_without_erroring(self):
        self.assertEqual(backups.list_backups(actor=self.admin), [])

    def test_an_archive_and_its_checksum_are_reported(self):
        self.write_archive()
        rows = backups.list_backups(actor=self.admin)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], VALID_NAME)
        self.assertTrue(rows[0]["has_checksum"])
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", rows[0]["checksum"]))

    def test_an_archive_with_no_sidecar_is_listed_but_marked(self):
        """Hiding a file that is really on the volume would be worse; it is
        named for what it is instead."""
        self.write_archive(checksum=False)
        rows = backups.list_backups(actor=self.admin)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["has_checksum"])

    def test_a_sidecar_naming_a_different_archive_does_not_count(self):
        self.write_archive(checksum=False)
        (self.backup_dir / f"{VALID_NAME}.sha256").write_text(f"{'0' * 64}  something-else.dump\n")
        self.assertFalse(backups.list_backups(actor=self.admin)[0]["has_checksum"])

    def test_files_that_are_not_dolphin_archives_are_ignored(self):
        (self.backup_dir / "notes.txt").write_text("hello")
        (self.backup_dir / "other.dump").write_bytes(b"PGDMP")
        self.write_archive()
        self.assertEqual([row["name"] for row in backups.list_backups(actor=self.admin)], [VALID_NAME])

    def test_newest_first(self):
        self.write_archive(OTHER_NAME)
        self.write_archive(VALID_NAME)
        self.assertEqual(
            [row["name"] for row in backups.list_backups(actor=self.admin)],
            [VALID_NAME, OTHER_NAME],
        )

    def test_the_time_comes_from_the_name_not_the_filesystem(self):
        """mtime is rewritten by a copy between hosts; the name is not."""
        self.write_archive()
        taken = backups.list_backups(actor=self.admin)[0]["taken_at"]
        self.assertEqual((taken.year, taken.month, taken.day, taken.hour), (2026, 9, 20, 10))


class RequestTests(BackupFixtures):
    def test_requesting_a_backup_writes_a_row_and_a_request_file(self):
        job = backups.request_backup(actor=self.admin)
        self.assertEqual(job.kind, BackupJob.Kind.BACKUP)
        self.assertEqual(job.status, BackupJob.Status.WAITING)
        written = list(self.spool_dir.glob("*.request.json"))
        self.assertEqual(len(written), 1)
        payload = json.loads(written[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "backup")
        self.assertEqual(payload["token"], job.token)

    def test_the_request_carries_the_fields_the_agent_actually_reads(self):
        """The agent parses four fields with `sed`. If this payload stops
        carrying one of them the agent silently does nothing, which is the
        worst possible failure for this feature."""
        backups.request_restore(actor=self.admin, upload=self.upload(), original_filename="x.dump")
        payload = json.loads(next(self.spool_dir.glob("*.request.json")).read_text(encoding="utf-8"))
        for field in ("token", "kind", "upload", "sha256", "expires_at"):
            self.assertIn(field, payload, field)
            self.assertIsInstance(payload[field], str)
            self.assertNotIn('"', payload[field])

    def test_the_timestamps_are_in_the_format_the_agent_can_compare(self):
        """The agent has `date -u` and no date library, and decides expiry
        by comparing strings. Two spellings of the same instant would make
        that comparison meaningless."""
        backups.request_backup(actor=self.admin)
        payload = json.loads(next(self.spool_dir.glob("*.request.json")).read_text(encoding="utf-8"))
        for field in ("requested_at", "expires_at"):
            self.assertRegex(payload[field], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertLess(payload["requested_at"], payload["expires_at"])

    def test_no_password_or_secret_reaches_the_spool(self):
        backups.request_restore(actor=self.admin, upload=self.upload(), original_filename="x.dump")
        text = next(self.spool_dir.glob("*.request.json")).read_text(encoding="utf-8").lower()
        for secret in ("password", "secret", "token_key", "postgres_init"):
            self.assertNotIn(secret, text)

    def test_the_upload_is_stored_and_hashed(self):
        body = b"PGDMP" + b"\x01" * 100
        job = backups.request_restore(
            actor=self.admin, upload=self.upload(body=body), original_filename="mine.dump",
        )
        import hashlib

        self.assertEqual(job.sha256, hashlib.sha256(body).hexdigest())
        self.assertEqual(job.size_bytes, len(body))
        stored = list(self.spool_dir.glob("*.upload.dump"))
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].read_bytes(), body)

    def test_the_stored_file_is_named_from_the_token_not_from_the_upload(self):
        """The operator's filename is display and evidence only; it never
        reaches a path."""
        job = backups.request_restore(
            actor=self.admin, upload=self.upload(name="../../evil.dump"), original_filename="../../evil.dump",
        )
        stored = list(self.spool_dir.glob("*.upload.dump"))
        self.assertEqual(stored[0].name, f"{job.token}{backups.UPLOAD_SUFFIX}")

    def test_a_file_that_is_not_a_custom_format_dump_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            backups.request_restore(
                actor=self.admin, upload=self.upload(body=b"not a dump at all"), original_filename="x.dump",
            )
        self.assertEqual(list(self.spool_dir.glob("*")), [])
        self.assertFalse(BackupJob.objects.exists())

    def test_an_empty_file_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            backups.request_restore(
                actor=self.admin, upload=self.upload(body=b""), original_filename="x.dump",
            )
        self.assertEqual(list(self.spool_dir.glob("*")), [])

    def test_a_refused_upload_leaves_no_temporary_file_behind(self):
        try:
            backups.request_restore(
                actor=self.admin, upload=self.upload(body=b"nope"), original_filename="x.dump",
            )
        except BusinessRuleError:
            pass
        self.assertEqual(sorted(path.name for path in self.spool_dir.iterdir()), [])

    def test_an_absurd_filename_is_reduced_before_it_is_stored(self):
        job = backups.request_restore(
            actor=self.admin,
            upload=self.upload(),
            original_filename="a" + chr(0) + chr(7) + "b" + "x" * 500,
        )
        self.assertLessEqual(len(job.original_filename), 120)
        self.assertNotIn(chr(0), job.original_filename)


class NothingIsPerformedHereTests(BackupFixtures):
    """The whole design in one class: the web container asks, it does not
    act. If any of these ever fail, the security boundary this feature
    depends on has been dissolved.
    """

    def test_the_module_shells_out_to_nothing(self):
        source = code_only((ROOT / "common" / "backups.py").read_text(encoding="utf-8"))
        for forbidden in ("subprocess", "os.system", "pg_dump", "pg_restore", "popen"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_requesting_a_restore_does_not_touch_the_database_schema(self):
        """Proven by the rows still being there afterwards — the request is
        a file, and nothing in this process can drop a table."""
        before = User.objects.count()
        backups.request_restore(actor=self.admin, upload=self.upload(), original_filename="x.dump")
        self.assertEqual(User.objects.count(), before)

    def test_the_agent_is_a_separate_container_behind_its_own_profile(self):
        """A deployment that does not start it cannot have its database
        replaced from a web page, whatever the panel shows."""
        self.assertIn("backup-agent:", COMPOSE)
        agent_block = COMPOSE.split("backup-agent:", 1)[1].split("\n  web:", 1)[0]
        self.assertIn('profiles: ["backup-agent"]', agent_block)
        self.assertIn("read_only: true", agent_block)
        self.assertIn("no-new-privileges:true", agent_block)
        self.assertIn("- ALL", agent_block)

    def test_the_agent_never_joins_the_network_the_browser_can_reach(self):
        agent_block = COMPOSE.split("backup-agent:", 1)[1].split("\n  web:", 1)[0]
        networks = agent_block.split("networks:", 1)[1]
        self.assertIn("backend", networks)
        self.assertNotIn("frontend", networks)

    def test_the_web_container_mounts_the_backups_read_only(self):
        """So a compromised panel cannot forge an archive beside the real
        ones."""
        web_block = COMPOSE.split("\n  web:", 1)[1].split("\n  nginx:", 1)[0]
        self.assertIn("backup_data:/backups:ro", web_block)
        self.assertIn("restore_spool:/spool", web_block)

    def test_the_web_container_never_receives_the_init_password(self):
        web_block = COMPOSE.split("\n  web:", 1)[1].split("\n  nginx:", 1)[0]
        self.assertNotIn("POSTGRES_INIT_PASSWORD", web_block)

    def test_the_spool_is_not_the_backup_volume(self):
        """Two volumes on purpose: the one the panel may write to is not the
        one published archives live on."""
        self.assertIn("restore_spool:", COMPOSE.split("volumes:")[-1])
        self.assertNotEqual(backups.backup_root(), backups.spool_root())


class AgentContractTests(BackupFixtures):
    """What the agent does, read off its source. It cannot be executed in
    this suite — it needs a PostgreSQL server, `pg_restore` and a mounted
    volume — so the properties that make it safe are pinned here and the
    end-to-end run is an operator drill the runbook describes.
    """

    def test_it_verifies_the_checksum_itself_rather_than_trusting_the_request(self):
        self.assertIn("sha256sum", AGENT)
        self.assertIn('if [ "$actual_hash" != "$expected_hash" ]', AGENT)

    def test_it_refuses_an_archive_pg_restore_cannot_read(self):
        self.assertIn("pg_restore --list", AGENT)

    def test_it_always_takes_a_safety_backup_before_replacing_anything(self):
        """The runbook makes this step 3 of the manual disaster procedure
        and calls it evidence. A restore driven from a web page must not be
        able to skip it."""
        restore_body = AGENT.split("handle_restore()", 1)[1].split("# --- the loop", 1)[0]
        safety_at = restore_body.index('safety="$(take_backup)"')
        restore_at = restore_body.index("pg_restore \\")
        self.assertLess(safety_at, restore_at)

    def test_it_stops_writes_before_restoring_and_restores_access_after(self):
        restore_body = AGENT.split("handle_restore()", 1)[1].split("# --- the loop", 1)[0]
        restore_at = restore_body.index("pg_restore \\")
        self.assertLess(restore_body.index("lock_app_out"), restore_at)
        # The *last* re-grant, not the first: the first one is on the
        # failure path of `lock_app_out` itself, which legitimately sits
        # above the restore.
        self.assertLess(restore_at, restore_body.rindex("let_app_back_in"))

    def test_access_is_restored_even_when_the_restore_failed(self):
        """A failed restore that also left the application locked out would
        turn a recoverable problem into an outage."""
        restore_body = AGENT.split("handle_restore()", 1)[1].split("# --- the loop", 1)[0]
        after = restore_body.rsplit("let_app_back_in || true", 1)[1]
        self.assertIn('if [ "$restore_status" -ne 0 ]', after)

    def test_an_expired_request_is_refused_rather_than_run_late(self):
        self.assertIn("expired", AGENT)
        self.assertIn('[ "$now" \\> "$expires_at" ]', AGENT)

    def test_it_writes_its_result_by_rename_so_a_half_written_one_is_never_read(self):
        self.assertIn('mv "$result_temp" "$result_final"', AGENT)

    def test_it_takes_no_input_but_the_spool(self):
        body = code_only(AGENT)
        for forbidden in ("docker", "curl", "wget", "nc ", "/var/run/docker.sock"):
            self.assertNotIn(forbidden, body, forbidden)


class ReconcileTests(BackupFixtures):
    def test_a_job_with_no_result_stays_waiting(self):
        job = backups.request_backup(actor=self.admin)
        backups.reconcile_jobs()
        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.WAITING)

    def test_a_result_is_folded_into_the_row(self):
        job = backups.request_backup(actor=self.admin)
        (self.spool_dir / f"{job.token}.result.json").write_text(json.dumps({
            "status": "done", "message": "ok", "safety_backup": VALID_NAME,
            "finished_at": "2026-09-20T10:30:00Z", "token": job.token,
        }), encoding="utf-8")
        backups.reconcile_jobs()
        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.DONE)
        self.assertEqual(job.archive_name, VALID_NAME)
        self.assertIsNotNone(job.finished_at)

    def test_an_unknown_status_is_ignored_rather_than_stored(self):
        job = backups.request_backup(actor=self.admin)
        (self.spool_dir / f"{job.token}.result.json").write_text(
            json.dumps({"status": "hacked", "message": "x"}), encoding="utf-8",
        )
        backups.reconcile_jobs()
        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.WAITING)

    def test_an_unreadable_result_does_not_raise(self):
        job = backups.request_backup(actor=self.admin)
        (self.spool_dir / f"{job.token}.result.json").write_text("{ not json", encoding="utf-8")
        backups.reconcile_jobs()
        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.WAITING)

    def test_a_request_nobody_ever_picked_up_expires_and_says_why(self):
        """The common case for a deployment that enabled the feature and
        forgot to start the agent. It must read as "this did not happen",
        not as a spinner."""
        job = backups.request_backup(actor=self.admin)
        BackupJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - backups.REQUEST_TTL - timedelta(minutes=1),
        )
        backups.reconcile_jobs()
        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.EXPIRED)
        self.assertIn("backup-agent", job.message)

    def test_a_finished_job_is_never_moved_backwards(self):
        job = backups.request_backup(actor=self.admin)
        BackupJob.objects.filter(pk=job.pk).update(status=BackupJob.Status.DONE)
        (self.spool_dir / f"{job.token}.result.json").write_text(
            json.dumps({"status": "failed", "message": "stale"}), encoding="utf-8",
        )
        backups.reconcile_jobs()
        job.refresh_from_db()
        self.assertEqual(job.status, BackupJob.Status.DONE)


class AuditTests(BackupFixtures):
    def test_all_three_events_have_persian_labels(self):
        for operation in ("backup.create", "backup.downloaded", "backup.restore"):
            self.assertIn(operation, OPERATION_LABELS, operation)

    def test_a_download_is_recorded(self):
        """Downloading a dump takes the entire database off the server. It
        is exactly the kind of event somebody later goes looking for."""
        self.write_archive()
        handle, _size = backups.open_backup(actor=self.admin, name=VALID_NAME)
        handle.close()
        self.assertTrue(ActivityLog.objects.filter(operation="backup.downloaded").exists())

    def test_a_restore_request_is_recorded_with_its_fingerprint(self):
        backups.request_restore(actor=self.admin, upload=self.upload(), original_filename="x.dump")
        entry = ActivityLog.objects.get(operation="backup.restore")
        self.assertIn("sha256", entry.safe_changes)
        self.assertEqual(entry.actor, self.admin)


class APITests(BackupFixtures):
    def test_the_endpoint_is_404_when_the_feature_is_off(self):
        with override_active_profile(without_feature()):
            self.assertEqual(self.client_for(self.admin).get("/api/v1/backups/").status_code, 404)

    def test_a_lower_role_is_refused(self):
        self.assertEqual(self.client_for(self.manager).get("/api/v1/backups/").status_code, 403)

    def test_an_anonymous_caller_is_refused(self):
        self.assertIn(APIClient().get("/api/v1/backups/").status_code, (401, 403))

    def test_listing_returns_archives_and_jobs(self):
        self.write_archive()
        backups.request_backup(actor=self.admin)
        response = self.client_for(self.admin).get("/api/v1/backups/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertEqual(len(response.data["archives"]), 1)
        self.assertEqual(len(response.data["jobs"]), 1)

    def test_an_unmounted_volume_answers_unavailable_not_an_error(self):
        with override_settings(DOLPHIN_BACKUP_ROOT=""):
            response = self.client_for(self.admin).get("/api/v1/backups/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])

    def test_the_download_streams_the_file(self):
        body = b"PGDMP" + b"\x02" * 500
        self.write_archive(body=body)
        response = self.client_for(self.admin).get(f"/api/v1/backups/download/{VALID_NAME}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), body)
        self.assertIn(VALID_NAME, response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_a_download_name_outside_the_pattern_is_a_404(self):
        for bad in ("evil.dump", "../secrets", VALID_NAME.replace("dump", "sha256")):
            with self.subTest(name=bad):
                self.assertEqual(
                    self.client_for(self.admin).get(f"/api/v1/backups/download/{bad}").status_code, 404,
                )

    def test_creating_a_backup_returns_202_and_a_waiting_job(self):
        response = self.client_for(self.admin).post("/api/v1/backups/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "waiting")

    def test_a_restore_without_the_confirmation_phrase_is_refused(self):
        response = self.client_for(self.admin).post(
            "/api/v1/backups/restore/", {"archive": self.upload()}, format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BackupJob.objects.exists())
        self.assertEqual(list(self.spool_dir.glob("*")), [])

    def test_a_restore_with_the_wrong_phrase_is_refused(self):
        response = self.client_for(self.admin).post(
            "/api/v1/backups/restore/",
            {"archive": self.upload(), "confirm": "yes"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(BackupJob.objects.exists())

    def test_a_restore_with_no_file_is_refused(self):
        from common.backup_views import RESTORE_CONFIRMATION

        response = self.client_for(self.admin).post(
            "/api/v1/backups/restore/", {"confirm": RESTORE_CONFIRMATION}, format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_correct_restore_request_is_accepted_and_spooled(self):
        from common.backup_views import RESTORE_CONFIRMATION

        response = self.client_for(self.admin).post(
            "/api/v1/backups/restore/",
            {"archive": self.upload(), "confirm": RESTORE_CONFIRMATION},
            format="multipart",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["status"], "waiting")
        self.assertEqual(len(list(self.spool_dir.glob("*.request.json"))), 1)

    def test_a_lower_role_cannot_restore_even_with_a_perfect_request(self):
        from common.backup_views import RESTORE_CONFIRMATION

        response = self.client_for(self.manager).post(
            "/api/v1/backups/restore/",
            {"archive": self.upload(), "confirm": RESTORE_CONFIRMATION},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(list(self.spool_dir.glob("*")), [])


class SettingsPageTests(BackupFixtures):
    def page(self, user):
        self.client.force_login(user)
        return self.client.get("/settings/").content.decode("utf-8")

    def test_a_platform_admin_sees_the_section(self):
        self.assertIn("پشتیبان‌گیری و بازگردانی", self.page(self.admin))

    def test_a_manager_does_not(self):
        self.assertNotIn("پشتیبان‌گیری و بازگردانی", self.page(self.manager))

    def test_nobody_sees_it_when_the_feature_is_off(self):
        with override_active_profile(without_feature()):
            self.assertNotIn("پشتیبان‌گیری و بازگردانی", self.page(self.admin))

    def test_nobody_sees_it_when_the_volume_is_not_mounted(self):
        """A section offering downloads from a directory that is not there
        would be a control that only looks real (CLAUDE.md §27)."""
        with override_settings(DOLPHIN_BACKUP_ROOT=""):
            self.assertNotIn("پشتیبان‌گیری و بازگردانی", self.page(self.admin))

    def test_the_page_says_what_a_restore_destroys_before_offering_it(self):
        page = self.page(self.admin)
        warning = page.split("بازگردانی از فایل پشتیبان", 1)[1].split("backup-restore-form", 1)[0]
        self.assertIn("از بین می‌رود", warning)
        self.assertIn("پشتیبان ایمنی", warning)

    def test_the_confirmation_phrase_is_rendered_from_the_one_the_server_checks(self):
        from common.backup_views import RESTORE_CONFIRMATION

        self.assertIn(RESTORE_CONFIRMATION, self.page(self.admin))

    def test_the_page_module_is_wired(self):
        self.assertIn("setupBackupSection();", SCRIPT)


class UploadLimitTests(BackupFixtures):
    def test_the_restore_route_has_its_own_body_limit(self):
        """A dump is a different order of size from every other upload this
        product takes; raising the shared file limit to fit one would raise
        it for attachments too."""
        from django.conf import settings

        self.assertIn("/api/v1/backups/restore/", settings.BACKUP_UPLOAD_PATHS)
        self.assertGreater(settings.BACKUP_UPLOAD_MAX_BYTES, settings.FILE_UPLOAD_MAX_MEMORY_SIZE)

    def test_an_oversized_body_is_refused_by_the_middleware(self):
        from common.backup_views import RESTORE_CONFIRMATION

        with override_settings(BACKUP_UPLOAD_MAX_BYTES=10):
            response = self.client_for(self.admin).post(
                "/api/v1/backups/restore/",
                {"archive": self.upload(), "confirm": RESTORE_CONFIRMATION},
                format="multipart",
            )
        self.assertEqual(response.status_code, 413)

    def test_large_uploads_do_not_spill_into_the_containers_tmpfs(self):
        """`/tmp` in the web container is a 64 MB tmpfs — RAM. A restore
        upload is far larger, so Django's spill directory has to be the
        spool volume when one is mounted.

        Read off the settings source rather than the running value: it is
        decided once, from the environment, at import time, which is
        exactly right in a container and is therefore not something
        `override_settings` can exercise.
        """
        source = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
        self.assertIn("if DOLPHIN_RESTORE_SPOOL:", source)
        self.assertIn("FILE_UPLOAD_TEMP_DIR = DOLPHIN_RESTORE_SPOOL", source)
