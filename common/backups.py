"""Database backups, reachable from the panel: list, download, create, restore.

Product owner, 2026-09-20 (item 13 of thirteen, and the second of the two
stages agreed for it): «دانلود پشتیبان» و «بارگذاری/بازگردانی کامل از پنل».

## Why this module holds no `pg_dump` and no `pg_restore`

The application container is `read_only`, drops every Linux capability, and
connects to PostgreSQL as `POSTGRES_APP_USER` — a `NOSUPERUSER` role with
table-level grants and nothing more (`scripts/bootstrap-postgres.sh`,
`common/tests/test_database_privileges.py`). It cannot drop a table, cannot
create a database, and does not contain the PostgreSQL client tools. That is
not an accident to work around; it is the boundary this product's security
posture is built on, and a panel feature does not get to dissolve it
(CLAUDE.md §9).

So the panel does not perform backups or restores. It **asks** for one, by
writing a request file into a spool volume, and a separate one-shot
container — `backup-agent`, behind its own Compose profile, holding the
privileged credentials the web container must never hold — picks the request
up and performs it. The only channel between the two is a file on a shared
volume; there is no socket, no shell, and nothing the web container can
execute.

That split is what makes «بازگردانی از پنل» honest rather than a control
that pretends. The trade it carries is stated plainly in
`docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md`: a deployment that runs the agent
has accepted that one authenticated Platform Admin request can replace the
whole database. A deployment that has not enabled the `panel_backup` feature
and has not started the agent keeps exactly the posture it had before this
module existed — the panel shows the request as waiting and says so, rather
than reporting a success that never happened.

## What protects the live database even so

* the feature gate (`panel_backup`, default off) and Platform Admin only;
* a request names one archive by its exact `dolphin-pg-...dump` name, which
  is validated against the same regular expression the shell scripts use;
* the agent re-verifies the SHA-256 sidecar before touching anything;
* the agent always takes a fresh backup of the *current* database first, so
  a restore is never one-way;
* a request expires, so one that sat in the spool cannot be replayed later;
* every request and every outcome is written to the audit log.
"""

import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.models import BackupJob

#: The one archive-name shape this product produces, character for
#: character the pattern `scripts/backup-postgres.sh` writes and
#: `scripts/verify-postgres-restore.sh` accepts. Anything else is refused
#: before it reaches a path join, so no name can escape the backup root.
ARCHIVE_NAME = re.compile(r"^dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}\.dump$")

#: The sentinel `scripts/prepare-backup-volume.sh` writes. Its absence means
#: the mount is not the backup volume — an empty directory, a failed mount,
#: or the wrong volume entirely — and every read here fails closed rather
#: than reporting "no backups yet", which would read as reassuring.
SENTINEL_NAME = ".dolphin-backup-root"
SENTINEL_VALUE = "DOLPHIN_BACKUP_ROOT_V1"

#: An uploaded dump is written here for the agent to pick up, and it must be
#: a *different* volume from the backup root: the backup root is mounted
#: read-only on the web container precisely so a compromised panel cannot
#: forge an archive beside the genuine ones.
REQUEST_SUFFIX = ".request.json"
RESULT_SUFFIX = ".result.json"
UPLOAD_SUFFIX = ".upload.dump"

#: How long a spooled request stays valid. Long enough for an agent that
#: polls on a slow cycle, short enough that a request left behind by an
#: abandoned browser tab cannot be executed an hour later.
REQUEST_TTL = timedelta(minutes=30)

#: A custom-format `pg_dump` archive begins with this magic. Checked on
#: upload so an operator who picks the wrong file is told immediately,
#: rather than after the agent has already taken a safety backup.
CUSTOM_FORMAT_MAGIC = b"PGDMP"


class BackupsUnavailable(BusinessRuleError):
    """The backup volume is not mounted, or is not the backup volume.

    A distinct type because the panel answers it differently from an
    ordinary validation error: there is nothing the reader can correct, and
    the fix is a deployment change.
    """


def _require_feature():
    if not feature_enabled("panel_backup"):
        raise BusinessPermissionDenied("پشتیبان‌گیری از پنل در این استقرار فعال نیست.")


def _require_platform_admin(actor):
    if actor is None or not getattr(actor, "is_authenticated", False):
        raise BusinessPermissionDenied("برای این کار باید وارد شوید.")
    if actor.role != User.Role.PLATFORM_ADMIN:
        raise BusinessPermissionDenied("پشتیبان‌گیری و بازگردانی فقط برای مدیر پلتفرم مجاز است.")


def backup_root():
    return Path(settings.DOLPHIN_BACKUP_ROOT) if settings.DOLPHIN_BACKUP_ROOT else None


def spool_root():
    return Path(settings.DOLPHIN_RESTORE_SPOOL) if settings.DOLPHIN_RESTORE_SPOOL else None


def _checked_root(path, *, sentinel):
    """The mount, confirmed to be a real directory and (for the backup root)
    to carry the sentinel the volume-preparation script wrote.

    `is_symlink` is checked as well as `is_dir` for the same reason the
    shell scripts check it: a symlink where the mount should be is how a
    fixed path stops being fixed.
    """
    if path is None:
        raise BackupsUnavailable("مسیر پشتیبان‌ها برای این استقرار تنظیم نشده است.")
    if path.is_symlink() or not path.is_dir():
        raise BackupsUnavailable("مسیر پشتیبان‌ها در دسترس نیست.")
    if sentinel:
        marker = path / SENTINEL_NAME
        try:
            if marker.is_symlink() or not marker.is_file() or marker.read_text().strip() != SENTINEL_VALUE:
                raise BackupsUnavailable("حجم پشتیبان‌ها معتبر نیست.")
        except OSError as error:
            raise BackupsUnavailable("حجم پشتیبان‌ها خوانده نشد.") from error
    return path


def available():
    """Whether the panel can show this section at all.

    Never raises: the settings page renders it or does not, and a
    misconfigured mount must not take the page down with it.
    """
    if not feature_enabled("panel_backup"):
        return False
    try:
        _checked_root(backup_root(), sentinel=True)
    except BackupsUnavailable:
        return False
    return True


def _archive_path(root, name):
    if not ARCHIVE_NAME.match(name):
        raise BusinessRuleError({"archive": "نام فایل پشتیبان معتبر نیست."})
    # Joined only after the name has been proven to match the one shape this
    # product produces, which contains no separator and no dot segment — so
    # the join cannot leave the root. Resolved and re-checked anyway,
    # because a defence that depends on one regular expression staying
    # correct forever is one defence too few.
    candidate = (root / name).resolve()
    if candidate.parent != root.resolve():
        raise BusinessRuleError({"archive": "نام فایل پشتیبان معتبر نیست."})
    return candidate


def list_backups(*, actor):
    """Every archive on the backup volume, newest first.

    The checksum is read from the `.sha256` sidecar the backup job wrote,
    not recomputed: hashing every archive on every page load would read
    gigabytes to answer a question the agent asks again, properly, before it
    restores anything. What *is* checked here is that a sidecar exists and
    names this archive — a missing one means the archive was not published
    by a Dolphin backup job, and it must not be offered as though it had
    been.

    Sorted by name rather than by mtime, and they are the same order: the
    name carries a UTC timestamp in a format that sorts lexically, while
    mtime can be rewritten by a file copy between hosts.
    """
    _require_feature()
    _require_platform_admin(actor)
    root = _checked_root(backup_root(), sentinel=True)

    rows = []
    for entry in root.iterdir():
        if entry.is_symlink() or not entry.is_file():
            continue
        if not ARCHIVE_NAME.match(entry.name):
            continue
        recorded = None
        sidecar = root / f"{entry.name}.sha256"
        if sidecar.is_file() and not sidecar.is_symlink():
            try:
                text = sidecar.read_text().strip()
            except OSError:
                text = ""
            if text.endswith(f"  {entry.name}"):
                candidate = text.split(" ", 1)[0]
                if re.fullmatch(r"[0-9a-f]{64}", candidate):
                    recorded = candidate
        try:
            size = entry.stat().st_size
        except OSError:
            continue
        rows.append({
            "name": entry.name,
            "size_bytes": size,
            "taken_at": _taken_at(entry.name),
            "checksum": recorded,
            "has_checksum": recorded is not None,
        })
    rows.sort(key=lambda row: row["name"], reverse=True)
    return rows


def _taken_at(name):
    """The moment in the archive's own name, as an aware datetime.

    `dolphin-pg-20260920T101500Z-<token>.dump` — the timestamp the backup
    job stamped, which is the one that means something. Returns `None`
    rather than guessing if the name somehow does not parse; every caller
    already has the name to fall back on.
    """
    try:
        stamp = name.split("-")[2]
        return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt_timezone.utc)
    except (IndexError, ValueError):
        return None


def open_backup(*, actor, name):
    """The archive, open for reading, plus its size.

    Returned as an open handle rather than bytes so the response can stream
    it: a dump is measured in hundreds of megabytes, and reading one into
    memory would take the container's memory limit with it.
    """
    _require_feature()
    _require_platform_admin(actor)
    root = _checked_root(backup_root(), sentinel=True)
    path = _archive_path(root, name)
    if path.is_symlink() or not path.is_file():
        raise BusinessRuleError({"archive": "این فایل پشتیبان پیدا نشد."})
    size = path.stat().st_size
    log_activity(
        actor=actor,
        operation="backup.downloaded",
        instance=actor,
        changes={"archive": name, "size_bytes": size},
    )
    return path.open("rb"), size


#: The one timestamp format both sides of the spool write.
#:
#: `datetime.isoformat()` would produce `...+00:00` here, and the agent —
#: which has `date -u` and no date library — produces `...Z`. The agent
#: decides whether a request has expired by comparing the two as strings,
#: so two spellings of the same instant would make that comparison
#: meaningless. Both sides are pinned to this, in UTC, seconds resolution.
SPOOL_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _spool_time(moment):
    return moment.astimezone(dt_timezone.utc).strftime(SPOOL_TIME_FORMAT)


def _new_token():
    return hashlib.sha256(os.urandom(32)).hexdigest()[:32]


def _write_request(root, token, payload):
    """Write the request atomically: a temporary name first, then a rename.

    The agent looks only for the final suffix, so it can never read a
    half-written request — the same publish-by-rename the backup script
    itself uses for an archive and its checksum.
    """
    final = root / f"{token}{REQUEST_SUFFIX}"
    temporary = root / f".{token}{REQUEST_SUFFIX}.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, final)
    return final


@transaction.atomic
def request_backup(*, actor):
    """Ask the agent to take a backup now.

    The row is written before the request file, not after: a row with no
    file is a job that shows as waiting and eventually reads as never
    picked up, which is recoverable and visible. A file with no row would
    be a database replacement nobody can account for.
    """
    _require_feature()
    _require_platform_admin(actor)
    root = _checked_root(spool_root(), sentinel=False)

    token = _new_token()
    job = BackupJob.objects.create(token=token, kind=BackupJob.Kind.BACKUP, requested_by=actor)
    requested_at = timezone.now()
    _write_request(root, token, {
        "kind": "backup",
        "token": token,
        "requested_at": _spool_time(requested_at),
        "expires_at": _spool_time(requested_at + REQUEST_TTL),
        "requested_by_username": actor.username,
    })
    log_activity(actor=actor, operation="backup.create", instance=actor, changes={"token": token})
    return job


def request_restore(*, actor, upload, original_filename):
    """Store an uploaded dump in the spool and ask the agent to restore it.

    The upload is written in chunks and hashed as it is written — never read
    whole into memory, and never hashed in a second pass, because a second
    pass would hash a file that could have changed between the two.

    What is *not* done here, deliberately: no judgement about whether the
    archive's contents are the right contents. That is a business decision
    nobody in this process can make, and pretending to make it would be
    worse than saying plainly, on the page, that restoring replaces
    everything written since the backup was taken.
    """
    _require_feature()
    _require_platform_admin(actor)
    root = _checked_root(spool_root(), sentinel=False)

    token = _new_token()
    destination = root / f"{token}{UPLOAD_SUFFIX}"
    temporary = root / f".{token}{UPLOAD_SUFFIX}.tmp"
    digest = hashlib.sha256()
    size = 0
    first_block = b""
    try:
        with temporary.open("wb") as handle:
            for chunk in upload.chunks():
                if not first_block:
                    first_block = bytes(chunk[: len(CUSTOM_FORMAT_MAGIC)])
                size += len(chunk)
                digest.update(chunk)
                handle.write(chunk)
        if size == 0:
            raise BusinessRuleError({"archive": "فایل انتخاب‌شده خالی است."})
        if not first_block.startswith(CUSTOM_FORMAT_MAGIC):
            raise BusinessRuleError({
                "archive": (
                    "این فایل یک پشتیبان custom-format پستگرس نیست. "
                    "همان فایل «.dump» دانلودشده از همین پنل را بفرستید."
                ),
            })
    except BusinessRuleError:
        temporary.unlink(missing_ok=True)
        raise
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise BackupsUnavailable("فایل پشتیبان ذخیره نشد.") from error

    checksum = digest.hexdigest()
    label = _safe_label(original_filename)
    with transaction.atomic():
        job = BackupJob.objects.create(
            token=token,
            kind=BackupJob.Kind.RESTORE,
            requested_by=actor,
            original_filename=label,
            sha256=checksum,
            size_bytes=size,
        )
        os.replace(temporary, destination)
        requested_at = timezone.now()
        _write_request(root, token, {
            "kind": "restore",
            "token": token,
            "upload": destination.name,
            "sha256": checksum,
            "requested_at": _spool_time(requested_at),
            "expires_at": _spool_time(requested_at + REQUEST_TTL),
            "requested_by_username": actor.username,
        })
        log_activity(
            actor=actor,
            operation="backup.restore",
            instance=actor,
            # The operator's own filename is not in the audit payload on
            # purpose: `auditlog.services._clean_changes` allows only
            # backend-generated values, and a name somebody typed is not
            # one. It is on the `BackupJob` row, which is where an
            # investigator looking for it will be.
            changes={"token": token, "sha256": checksum, "size_bytes": size},
        )
    return job


def _safe_label(value):
    """An uploaded filename, reduced to something safe to store and print.

    Never used to build a path — the stored file is named from the token —
    so this only has to stop control characters and an unbounded length from
    reaching the audit log and the settings page.
    """
    text = unicodedata.normalize("NFC", str(value or "")).strip()
    text = "".join(character for character in text if character.isprintable())
    return text[:120] or "بدون‌نام"


def _read_result(root, token):
    path = root / f"{token}{RESULT_SUFFIX}"
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def reconcile_jobs():
    """Fold whatever the agent has written back into the job rows.

    Called on every read of the job list rather than on a schedule: there is
    no task queue in this deployment, the only reader who cares is the
    Platform Admin looking at the settings page, and a handful of `stat`
    calls per page view is cheaper than any machinery that would avoid them.

    Idempotent, and it never moves a job backwards — a row that has already
    finished is left exactly as it was, so a stale result file cannot
    rewrite history.
    """
    waiting = list(BackupJob.objects.filter(status=BackupJob.Status.WAITING))
    if not waiting:
        return
    try:
        root = _checked_root(spool_root(), sentinel=False)
    except BackupsUnavailable:
        return

    now = timezone.now()
    for job in waiting:
        result = _read_result(root, job.token)
        if result is None:
            # No result yet. If the request could not possibly still run,
            # say so rather than leaving it "waiting" forever — an agent
            # that was never started is the common case and the reader
            # needs to be told, not left watching a spinner.
            if job.created_at + REQUEST_TTL < now:
                job.status = BackupJob.Status.EXPIRED
                job.message = "درخواست اجرا نشد و منقضی شد. آیا سرویس backup-agent در حال اجراست؟"
                job.finished_at = now
                job.save(update_fields=["status", "message", "finished_at", "updated_at"])
            continue
        status = str(result.get("status", "")).strip()
        if status not in BackupJob.Status.values:
            continue
        job.status = status
        job.message = str(result.get("message", ""))[:2000]
        job.archive_name = str(result.get("safety_backup", ""))[:128]
        job.finished_at = _parse_spool_time(result.get("finished_at")) or now
        job.save(update_fields=["status", "message", "archive_name", "finished_at", "updated_at"])


def _parse_spool_time(value):
    try:
        return datetime.strptime(str(value), SPOOL_TIME_FORMAT).replace(tzinfo=dt_timezone.utc)
    except (TypeError, ValueError):
        return None


def recent_jobs(*, actor, limit=10):
    """The last few requests and what became of them."""
    _require_feature()
    _require_platform_admin(actor)
    reconcile_jobs()
    return list(BackupJob.objects.select_related("requested_by")[:limit])
