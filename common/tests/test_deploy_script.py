"""`scripts/deploy.sh`'s own text, pinned the way `test_backup_scripts.py` pins
the PowerShell backup/restore scripts: running the real thing needs a live
Compose stack, which is out of reach for a unit test, so what is checked here
is that the fixes for a real, reported deployment incident are still in the
script rather than reintroduced-then-lost.

DEPLOY-ENV-001: an operator's `secrets/.env` (what the runbook's first-install
sequence, and `scripts/new_deployment.py`, both write to) and this script's own
default (a bare `.env`) used to be two different files. One install ran
`db-bootstrap`/`migrate` against `secrets/.env` by hand, then had this script
read an empty or stale bare `.env` and report a stack it did not recognize as
its own.

The missing `db-finalize` call: `db-bootstrap`'s per-table grant loop only
touches tables that exist when it runs, which is before `migrate` creates
whatever a release adds. Skipping `db-finalize` after `migrate` left a new
table ungranted for the application role until someone noticed by hand.
"""

import subprocess
from pathlib import Path

from django.test import SimpleTestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "deploy.sh"


class DeployScriptEnvFileTests(SimpleTestCase):
    def setUp(self):
        self.text = SCRIPT.read_text(encoding="utf-8")

    def test_the_default_env_file_is_secrets_env_not_a_bare_env(self):
        # Unset at the top (resolved later, in resolve_env_file) rather than
        # hardcoded to a bare .env the way it used to be.
        self.assertIn('ENV_FILE=""', self.text)
        self.assertIn('if [ -f secrets/.env ]; then\n        ENV_FILE="secrets/.env"', self.text)

    def test_secrets_env_is_preferred_over_a_bare_env_when_both_exist(self):
        both_exist_branch = self.text[self.text.index("Both exist."):self.text.index("check_ports_are_free")]
        self.assertIn('ENV_FILE="secrets/.env"', both_exist_branch)

    def test_compose_is_always_invoked_with_the_resolved_env_file(self):
        self.assertIn('COMPOSE="docker compose --env-file $ENV_FILE"', self.text)

    def test_env_file_is_an_accepted_option(self):
        self.assertIn("--env-file", self.text)

    def test_a_conflicting_pair_of_env_files_is_refused_not_guessed(self):
        self.assertIn("name different deployments", self.text)

    def test_db_finalize_runs_after_migrate_on_every_release(self):
        """The exact defect: a release ran migrate and never re-granted."""
        migrate_index = self.text.index("run --rm -T migrate")
        finalize_index = self.text.index("run --rm -T db-finalize")
        self.assertGreater(
            finalize_index, migrate_index,
            "db-finalize must run after migrate, so a table migrate just "
            "created is not left with no grant for the application role",
        )

    def test_db_bootstrap_runs_even_when_the_backup_is_skipped(self):
        """`--no-backup` must skip the backup, not the role provisioning
        `migrate` depends on to authenticate at all."""
        no_backup_index = self.text.index('SKIP_BACKUP" -eq 1')
        bootstrap_index = self.text.index("run --rm -T db-bootstrap")
        self.assertLess(
            bootstrap_index, no_backup_index,
            "db-bootstrap must run unconditionally, before the backup/"
            "--no-backup branch decides whether a dump is taken",
        )

    def test_manifest_and_tls_paths_are_checked_before_anything_starts(self):
        self.assertIn("check_manifest_and_tls_files_are_readable", self.text)
        deploy_body = self.text[self.text.index("deploy() {"):]
        self.assertIn("check_manifest_and_tls_files_are_readable", deploy_body[:deploy_body.index("check_ports_are_free")])

    def test_the_backup_sentinel_check_recognises_every_project_name(self):
        """Collapsed to a self-comparison once already by a careless
        find-and-replace; a real backup volume prepared under an earlier
        project name must still be recognised."""
        for sentinel in (".dolphin-backup-root", ".frooshbin-backup-root", ".kariz-backup-root"):
            with self.subTest(sentinel=sentinel):
                self.assertIn(sentinel, self.text)

    def test_the_backup_volume_hint_points_at_the_prepare_script(self):
        self.assertIn("./scripts/prepare-backup-volume.sh", self.text)

    def test_the_script_is_syntactically_valid_posix_sh(self):
        result = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class PrepareBackupVolumeScriptTests(SimpleTestCase):
    SCRIPT = REPOSITORY_ROOT / "scripts" / "prepare-backup-volume.sh"

    def test_it_recognises_every_sentinel_name_before_trying_to_prepare(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        for sentinel in (".dolphin-backup-root", ".frooshbin-backup-root", ".kariz-backup-root"):
            with self.subTest(sentinel=sentinel):
                self.assertIn(sentinel, text)

    def test_it_reports_already_prepared_rather_than_failing_on_a_second_run(self):
        text = self.SCRIPT.read_text(encoding="utf-8")
        self.assertIn("already prepared", text)

    def test_the_script_is_syntactically_valid_posix_sh(self):
        result = subprocess.run(["sh", "-n", str(self.SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
