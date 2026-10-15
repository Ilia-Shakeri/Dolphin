"""2.40.50 — scheduled backups (BIZ-009, owner decision 2026-10-14: «بهترین و
جهانی‌ترین و منطقی‌ترین سازوکار را خودت انتخاب کن»).

3-2-1: the live database, the archive on the backup volume, and an AES-256
(GnuPG) copy off the server that is decrypted again and checked before it
counts. Grandfather-father-son retention, a weekly restore drill into a
throwaway cluster, and every run recorded in `common_backuprun` — the backup
role's one write — for the panel to show and alert on.
"""

import os
import shutil
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

import yaml
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import User
from common.backup_health import backup_health
from common.models import BackupRun
from common.reminders import reminders_for

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def run(kind, status="ok", hours_ago=1, detail=""):
    finished = timezone.now() - timedelta(hours=hours_ago)
    return BackupRun.objects.create(
        kind=kind, status=status, started_at=finished - timedelta(minutes=2), finished_at=finished,
        archive="dolphin-pg-20261015T020000Z-" + "a" * 32 + ".dump", size_bytes=1024 * 1024, detail=detail,
    )


class HealthTests(TestCase):
    def test_no_runs_says_the_schedule_is_not_running(self):
        health = backup_health()
        self.assertFalse(health["configured"])
        self.assertFalse(health["healthy"])
        self.assertIn("اجرا نمی‌شود", health["problems"][0])

    def test_fresh_backup_copy_and_drill_are_healthy(self):
        run("backup")
        run("offsite")
        run("drill", hours_ago=48)
        health = backup_health()
        self.assertTrue(health["healthy"], health["problems"])

    def test_each_gap_is_named(self):
        run("backup", hours_ago=30)
        run("offsite", status="failed", detail="off-host directory not configured")
        run("drill", status="failed", detail="schema contract failed")
        problems = backup_health()["problems"]
        self.assertEqual(len(problems), 3)
        self.assertIn("۲۶ ساعت", problems[0])
        self.assertIn("بیرون از سرور تنظیم نشده", problems[1])
        self.assertIn("آزمون بازگردانی ناموفق", problems[2])

    def test_a_failed_latest_backup_is_flagged_even_after_a_good_one(self):
        run("backup", hours_ago=5)
        run("backup", status="failed", hours_ago=1)
        run("offsite")
        run("drill")
        self.assertEqual(backup_health()["problems"], ["آخرین پشتیبان‌گیری ناموفق بود."])

    def test_a_failed_newest_copy_or_prune_is_flagged(self):
        run("backup")
        run("offsite", hours_ago=5)
        run("offsite", status="failed", detail="the encrypted copy did not verify")
        run("prune", status="failed", detail="local prune failed")
        run("drill")
        self.assertEqual(backup_health()["problems"], [
            "آخرین نسخهٔ رمزگذاری‌شدهٔ بیرون از سرور ناموفق بود.",
            "پاک‌سازی نسخه‌های قدیمی ناموفق بود؛ فضای پشتیبان را بررسی کنید.",
        ])

    def test_the_record_refuses_nonsense(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            BackupRun.objects.create(kind="restore", status="ok", started_at=timezone.now(), finished_at=timezone.now())
        with self.assertRaises(IntegrityError), transaction.atomic():
            now = timezone.now()
            BackupRun.objects.create(kind="backup", status="ok", started_at=now, finished_at=now - timedelta(minutes=1))


class PanelTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="b.admin", password="Strong-pass-750!", role=User.Role.PLATFORM_ADMIN)
        self.it = User.objects.create_user(username="b.it", password="Strong-pass-750!", role=User.Role.COMPANY_IT)
        self.manager = User.objects.create_user(username="b.manager", password="Strong-pass-750!", role=User.Role.SALES_MANAGER)

    def test_the_platform_roles_see_the_page_tile_and_alert(self):
        run("backup", hours_ago=40)
        for user in (self.admin, self.it):
            self.client.force_login(user)
            page = self.client.get("/settings/backup-health/")
            self.assertContains(page, "پشتیبان‌گیری توجه می‌خواهد")
            # The menu entry, from the sidebar's own flag list.
            self.assertContains(page, 'data-module="backup-health"')
            self.assertContains(self.client.get("/"), "سلامت پشتیبان‌گیری")
            groups = {group["kind"]: group for group in reminders_for(user)["groups"]}
            self.assertIn("backup_health", groups)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/settings/backup-health/").status_code, 403)
        self.assertNotContains(self.client.get("/"), 'data-module="backup-health"')
        self.assertNotIn("backup_health", {group["kind"] for group in reminders_for(self.manager)["groups"]})


class ComposeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.compose = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
        cls.scheduler = cls.compose["services"]["backup-scheduler"]

    def test_the_scheduler_is_as_locked_down_as_the_backup_job(self):
        service = self.scheduler
        self.assertEqual(service["profiles"], ["backup-schedule"])
        self.assertEqual(service["user"], "postgres")
        self.assertTrue(service["read_only"])
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", service["security_opt"])
        self.assertEqual(service["networks"], ["backend"])
        self.assertEqual(service["environment"]["TZ"], "Asia/Tehran")
        self.assertNotIn("POSTGRES_INIT_PASSWORD", service["environment"])
        self.assertNotIn("POSTGRES_APP_PASSWORD", service["environment"])
        self.assertIn("${DOLPHIN_BACKUP_OFFSITE_DIR:-backup_offsite}:/offsite", service["volumes"])
        self.assertIn("backup_scratch:/tmp", service["volumes"])
        # The signed manifest rides along with the off-host copy, read-only.
        self.assertTrue(any(volume.endswith(":/profile/manifest.json:ro") for volume in service["volumes"]))

    def test_deploy_recreates_it_when_it_runs(self):
        deploy = (SCRIPTS / "deploy.sh").read_text(encoding="utf-8")
        self.assertIn("--profile backup-schedule up -d --no-deps --force-recreate backup-scheduler", deploy)


class ScriptTests(SimpleTestCase):
    def test_the_scheduler_records_safely_and_verifies_the_copy(self):
        script = (SCRIPTS / "backup-scheduler.sh").read_text(encoding="utf-8")
        # Values reach SQL only as psql variables.
        self.assertIn("VALUES (:'kind', :'status', :'started'::timestamptz", script)
        self.assertIn("--set=kind=", script)
        self.assertIn("--cipher-algo AES256", script)
        self.assertIn("--passphrase-fd 0", script)
        self.assertIn("the encrypted copy did not verify", script)
        self.assertIn("off-host directory not configured", script)
        self.assertIn("sh /ops/verify-postgres-restore.sh", script)
        self.assertIn("deployment-manifest.json.gpg", script)
        self.assertNotIn("echo \"$passphrase", script)
        self.assertNotIn("set -x", script)

    def test_retention_keeps_the_grandfather_father_son_set(self):
        shell = shutil.which("sh")
        if shell is None:
            self.skipTest("no POSIX shell here")
        probe = subprocess.run([shell, "-c", "date -u -d 2026-01-01 +%s"], capture_output=True, text=True)
        if probe.returncode != 0:
            self.skipTest("no GNU date here")
        now = 1792065600  # 2026-10-15 12:00:00 UTC
        with tempfile.TemporaryDirectory() as directory:
            names = []
            for hours in range(0, 24 * 80, 12):
                moment = now - hours * 3600
                stamp = subprocess.run([shell, "-c", f"date -u -d @{moment} +%Y%m%dT%H%M%SZ"], capture_output=True, text=True).stdout.strip()
                name = f"dolphin-pg-{stamp}-{hours:032x}.dump"
                Path(directory, name).touch()
                Path(directory, name + ".sha256").touch()
                names.append(name)
            Path(directory, "notes.txt").touch()
            result = subprocess.run(
                [shell, str(SCRIPTS / "backup-gfs-prune.sh"), directory, "dump"],
                capture_output=True, text=True, env={**os.environ, "DOLPHIN_PRUNE_NOW_EPOCH": str(now)},
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            left = sorted(name for name in os.listdir(directory) if name.endswith(".dump"))
            self.assertIn(names[0], left)  # the newest
            self.assertIn(names[1], left)  # within 24 hours
            self.assertTrue(Path(directory, "notes.txt").exists())
            self.assertLess(len(left), len(names))
            # Each kept archive still has its checksum; each removed one lost both.
            for name in names:
                self.assertEqual(Path(directory, name).exists(), Path(directory, name + ".sha256").exists())
