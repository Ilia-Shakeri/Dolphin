"""Is this deployment's data safe? — from what the scheduled backup recorded (2.40.50).

Owner decision 2026-10-14 (BIZ-009): the team chooses the standard mechanism.
`scripts/backup-scheduler.sh` records every run in `common.BackupRun`; this
module turns those rows into what the panel says and alerts on:

* a backup on the server within the last 26 hours (a day and a slack for one
  missed run) — the newest one must not have failed;
* its encrypted copy off the server within the same window — the newest one
  must not have failed either;
* a restore drill that succeeded within the last 8 days;
* the newest retention pass did not fail (old archives would pile up).

The 26-hour window holds for any schedule: `DOLPHIN_BACKUP_EVERY_HOURS` is at
most 24.

No rows at all means the scheduler is not running here, and the panel says
exactly that rather than staying quiet. Read by the platform's own roles only
(`can_see_backup_health`): the Platform Admin and the company's IT role.
"""

from datetime import timedelta

from django.db import DatabaseError
from django.utils import timezone

from accounts.access import is_crm_identity
from accounts.models import User
from common.models import BackupRun

BACKUP_WINDOW = timedelta(hours=26)
DRILL_WINDOW = timedelta(days=8)


def can_see_backup_health(user):
    return (
        user is not None
        and is_crm_identity(user)
        and user.role in (User.Role.PLATFORM_ADMIN, User.Role.COMPANY_IT)
    )


def _latest(kind, *, ok=None):
    queryset = BackupRun.objects.filter(kind=kind)
    if ok is not None:
        queryset = queryset.filter(status=BackupRun.Status.OK if ok else BackupRun.Status.FAILED)
    return queryset.order_by("-finished_at", "-id").first()


def _run(row):
    if row is None:
        return None
    return {
        "status": row.status,
        "finished_at": row.finished_at.isoformat(),
        "archive": row.archive,
        "size_bytes": row.size_bytes,
        "detail": row.detail,
    }


def backup_health(*, now=None):
    """`{"configured", "healthy", "problems": [...], "backup", "offsite", "drill"}`.

    Each problem is one plain Persian sentence a reader can act on. Never raises:
    the dashboard and the bell must render even when this table is unreachable.
    """
    now = now or timezone.now()
    try:
        if not BackupRun.objects.exists():
            return {
                "configured": False,
                "healthy": False,
                "problems": ["پشتیبان‌گیری زمان‌بندی‌شده روی این سرور اجرا نمی‌شود."],
                "backup": None, "offsite": None, "drill": None,
            }
        last_backup = _latest(BackupRun.Kind.BACKUP)
        good_backup = _latest(BackupRun.Kind.BACKUP, ok=True)
        last_offsite = _latest(BackupRun.Kind.OFFSITE)
        good_offsite = _latest(BackupRun.Kind.OFFSITE, ok=True)
        last_drill = _latest(BackupRun.Kind.DRILL)
        good_drill = _latest(BackupRun.Kind.DRILL, ok=True)
        last_prune = _latest(BackupRun.Kind.PRUNE)
    except DatabaseError:
        return {"configured": False, "healthy": False, "problems": ["وضعیت پشتیبان‌گیری خوانده نشد."],
                "backup": None, "offsite": None, "drill": None}

    problems = []
    if good_backup is None or now - good_backup.finished_at > BACKUP_WINDOW:
        problems.append("در ۲۶ ساعت گذشته پشتیبان موفقی گرفته نشده است.")
    elif last_backup.status == BackupRun.Status.FAILED:
        problems.append("آخرین پشتیبان‌گیری ناموفق بود.")
    if last_offsite is not None and last_offsite.status == BackupRun.Status.FAILED and last_offsite.detail == "off-host directory not configured":
        problems.append("نسخهٔ بیرون از سرور تنظیم نشده است؛ پشتیبان‌ها فقط روی همین سرورند.")
    elif good_offsite is None or now - good_offsite.finished_at > BACKUP_WINDOW:
        problems.append("در ۲۶ ساعت گذشته نسخهٔ رمزگذاری‌شده‌ای بیرون از سرور ساخته نشده است.")
    elif last_offsite.status == BackupRun.Status.FAILED:
        problems.append("آخرین نسخهٔ رمزگذاری‌شدهٔ بیرون از سرور ناموفق بود.")
    if last_drill is not None and last_drill.status == BackupRun.Status.FAILED:
        problems.append("آخرین آزمون بازگردانی ناموفق بود؛ پشتیبان‌ها را بررسی کنید.")
    elif good_drill is None or now - good_drill.finished_at > DRILL_WINDOW:
        problems.append("در هشت روز گذشته آزمون بازگردانی موفقی انجام نشده است.")
    if last_prune is not None and last_prune.status == BackupRun.Status.FAILED:
        problems.append("پاک‌سازی نسخه‌های قدیمی ناموفق بود؛ فضای پشتیبان را بررسی کنید.")
    return {
        "configured": True,
        "healthy": not problems,
        "problems": problems,
        "backup": _run(good_backup),
        "offsite": _run(good_offsite),
        "drill": _run(good_drill),
    }
