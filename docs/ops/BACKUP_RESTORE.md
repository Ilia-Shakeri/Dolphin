# PostgreSQL backup and restore verification

> **Deployment and startup live in [`DOLPHIN_DEPLOYMENT_RUNBOOK.md`](DOLPHIN_DEPLOYMENT_RUNBOOK.md).**
> That runbook is canonical for installing, starting, updating, backing up,
> restoring and recovering the stack. This document covers backup internals and the restore-verification contract in more
> depth and does not restate the procedure; where the two differ, the runbook
> is correct.

The bundled profile-only `backup` service creates verified custom-format PostgreSQL backups over the internal database network. It uses only the managed read-only backup login and one exact external backup volume. The host PowerShell tools remain available for a separately approved host-reachable database and for disposable restore verification. No tool accepts a password argument, overwrites a backup, or restores into a named business database.

## Prerequisites

- Complete `db-bootstrap` for the current role layout. The bundled job fails until the managed backup login exists.
- Set `POSTGRES_BACKUP_USER`, `POSTGRES_BACKUP_PASSWORD`, `POSTGRES_BACKUP_VOLUME`, `POSTGRES_BACKUP_RETENTION_DAYS`, and `POSTGRES_RESTORE_TMPFS_SIZE_BYTES` through the protected deployment environment. The role name must be unused and distinct; the secret must be random, private, at least 16 characters, and different from every other database secret. Size the restore tmpfs in bytes for the full expanded database plus safe headroom; a low value must fail the drill instead of spilling into a business volume.
- Choose one exact external Docker volume backed by protected storage outside the database volume and web/static paths. A remote or separately replicated protected store is preferred; one local Docker volume is not host-loss protection.
- Use PostgreSQL client tools compatible with the server for host-only backup or restore work. Put `pg_dump`, `pg_restore`, `psql`, `createdb`, and `dropdb` on `PATH`, or pass their directory with `-PostgresBin`.
- Supply host-tool authentication through the deployment secret mechanism or a protected PostgreSQL password file. Do not place a password in command history or a script argument.

## Prepare one exact external backup volume

For a reviewed new backup destination only, create the approved volume name and set that exact name as `POSTGRES_BACKUP_VOLUME`. Never guess an old name or substitute the PostgreSQL data volume.

```powershell
$approvedBackupVolume = Read-Host 'Approved new backup volume name'
docker volume create $approvedBackupVolume
```

After the protected environment points to that new empty volume, initialize its fixed sentinel and owner once. This command refuses a nonempty destination and refuses to replace a sentinel:

```powershell
docker compose --profile backup run --rm --no-deps --user root --cap-add CHOWN --entrypoint sh backup -c 'set -eu; test -z "$(find /backups -mindepth 1 -maxdepth 1 -print -quit)"; chown postgres:postgres /backups; chmod 0700 /backups; printf "%s\n" DOLPHIN_BACKUP_ROOT_V1 > /backups/.dolphin-backup-root; chown postgres:postgres /backups/.dolphin-backup-root; chmod 0600 /backups/.dolphin-backup-root'
```

Do not run the initializer to adopt an existing destination. Prove its exact volume record, sentinel, access, backup pairs, and recovery history instead. The backup service runs as `postgres`, has a read-only root filesystem and no Linux capabilities, and is the only service that mounts `backup_data`.

Existing destinations may keep the exact legacy `.dolphin-backup-root` sentinel and exact `dolphin-pg-...` archives as read-only compatibility input. New jobs always publish `dolphin-pg-...`. If both old and new sentinel files exist, both must carry their exact valid values or all backup and restore work fails closed.

## Run the bundled backup job

```powershell
docker compose --profile backup run --rm backup
```

The profile prevents a normal `docker compose up -d` from starting a backup. The explicit command joins only the backend network, waits for database health, reads with `POSTGRES_BACKUP_USER`, and receives no init, migration, or application password. The job validates the fixed mount and sentinel, writes a temporary custom-format archive, runs `pg_restore --list`, calculates SHA-256, writes the checksum sidecar, and renames both files to final names on the same volume. It prints only the generated backup filename. A nonzero exit is failure and must reach the approved alert path.

The job atomically creates the exact `/backups/.dolphin-backup.lock` directory before it connects to PostgreSQL. A second or overlapping run exits nonzero and publishes no archive. Normal exit and handled signals release the lock after exact temporary-file cleanup. An unhandled container kill can leave the lock in place and deliberately blocks later jobs until an operator proves that no backup runs.

Final names use only this form:

```text
dolphin-pg-YYYYMMDDTHHMMSSZ-32_lowercase_hex.dump
dolphin-pg-YYYYMMDDTHHMMSSZ-32_lowercase_hex.dump.sha256
```

Temporary or failed outputs are removed only by their exact generated paths.

## Explicit retention and schedule

`POSTGRES_BACKUP_RETENTION_DAYS` is required and accepts `0` through `3650`. `0` disables deletion and is the safe value for an isolated pre-migration recovery point. A positive value removes only direct, strictly named dump/checksum pairs old enough by file age and only after recalculating and matching the checksum. It never recurses or uses a caller path for deletion.

The repository supplies the runnable one-shot job, not a guessed production schedule. After a manual backup and disposable restore succeed, the deployment owner must record the exact release directory, scheduler identity, daily time, retention days, weekly/off-host copy rule, concurrency rule, timeout, failure alert, and missed-run alert. Schedule this exact noninteractive job from the reviewed release directory:

```powershell
docker compose --profile backup run --rm backup
```

Do not overlap jobs. Treat a lock failure as an alert, not as permission to retry in parallel. First inspect the exact Compose service state:

```powershell
docker compose --profile backup ps --all backup
```

Only after the job owner proves that no backup container or external scheduler run is active may an approved operator remove the one empty stale lock directory:

```powershell
docker compose --profile backup run --rm --no-deps --entrypoint sh backup -c 'set -eu; test -d /backups/.dolphin-backup.lock; test ! -L /backups/.dolphin-backup.lock; rmdir /backups/.dolphin-backup.lock'
```

`rmdir` refuses a nonempty lock. If it fails, preserve the directory and investigate; do not recursively delete it or any backup path. Record the failed run, process proof, approval, exact command, UTC time, and next successful backup/restore result. Docker/Compose does not provide the scheduler or alert system. Destination, schedule, retention, operator, recovery-time target, recovery-point target, alert path, and off-host replication remain explicit deployment inputs.

## Optional host-only backup tool

`scripts/backup-postgres.ps1` keeps the same sentinel, archive-list, checksum, atomic publication, and exact retention guards for a separately approved host that can already reach PostgreSQL. The bundled database publishes no host port, so this script is not the default path into the Compose database. Pass the real approved host, database, backup login, protected root, and compatible client-tool directory; never use the old illustrative `db.internal` name.

## Verify the bundled backup in an isolated disposable database

Use the exact archive leaf printed by the bundled backup. Do not pass a path, connection value, password, or caller-selected database name:

```powershell
$approvedArchive = Read-Host 'Exact archive leaf printed by the successful backup job'
docker compose -f compose.restore-verify.yml --profile restore-verify config --quiet
docker compose -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify $approvedArchive
```

The standalone definition has one service and one external read-only backup-volume mount. It has no business database volume, port, Compose network, database target, or password. The script accepts one strictly named archive, verifies the fixed sentinel, rejects links, matches the exact SHA-256 sidecar, and lists the custom archive before starting a new local cluster. PostgreSQL listens only on a generated Unix-socket directory inside the container. The restore uses owner and privilege replay disabled, one transaction, and a generated database in the bounded `/tmp` mount. Normal `--rm` completion removes the container and its tmpfs; never use a broad container or volume prune for cleanup.

One shared boolean SQL contract checks all nine core tables, exact migration heads, twelve true PostgreSQL constraints, and the two named partial unique phone indexes with their indexed columns and predicates. Both restore tools use this same file. The query returns only `1` or `0`; it does not print business rows.

If the run is interrupted, inspect only the exact stopped restore container from that command and remove only that reviewed container. It has no durable restore volume. Do not delete the backup volume or any database volume.

## Optional host-only restore verifier

For a separately approved backup root already accessible to the host, use only a disposable PostgreSQL server bound to a loopback IP on a high port other than `5432`. The PowerShell verifier rejects remote hosts, low ports, port `5432`, nonstandard backup names, missing or mismatched checksums, and files outside the sentinel root.

```powershell
.\scripts\verify-postgres-restore.ps1 `
  -BackupRoot 'D:\DolphinBackups' `
  -BackupFile 'D:\DolphinBackups\dolphin-pg-20260809T010203Z-0123456789abcdef0123456789abcdef.dump' `
  -TargetHost '127.0.0.1' `
  -TargetPort 55432 `
  -DatabaseUser 'dolphin_restore' `
  -PostgresBin 'C:\Program Files\PostgreSQL\17\bin'
```

The host verifier chooses a new database named `dolphin_restore_verify_<32_lowercase_hex>`. It first proves that name does not exist, creates it, restores with owner and privilege replay disabled, and runs the same shared SQL contract. It drops only that exact generated database in `finally` and refuses any caller-selected target database name.

Never point this verifier at production or staging, even through a tunnel. A successful local guard test is not a real restore drill; final evidence needs a live disposable PostgreSQL engine and recorded operator results without credentials.

## Recovery runbook

For a real recovery, do not overwrite the damaged database in place.

1. Declare the incident and stop business writes through the approved maintenance path.
2. Preserve the failed database and its logs.
3. Select a backup with its matching SHA-256 sidecar and verify the checksum.
4. Restore into a newly created recovery database with reviewed ownership and privileges.
5. Run migrations only when the selected application release requires them and its rollback path is approved.
6. Check health, schema, row counts, role isolation, core customer/lead/sale flows, and audit continuity.
7. Get owner approval before changing application database routing.
8. Keep the prior database and application release until acceptance and rollback windows close.

The live backup destination, daily and weekly retention, alert owner, recovery-time target, recovery-point target, and cutover authority remain deployment decisions.
