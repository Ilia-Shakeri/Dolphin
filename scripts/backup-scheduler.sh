#!/bin/sh
# The scheduled backup (2.40.50, owner decision 2026-10-14, BIZ-009: «بهترین و
# جهانی‌ترین و منطقی‌ترین سازوکار را خودت انتخاب کن»). Runs for as long as its
# container runs (Compose profile `backup-schedule`) and, on every slot:
#
#   1. backs up the database with the existing job (`backup-postgres.sh`:
#      `pg_dump`, checksum, published atomically);
#   2. encrypts that archive with GnuPG (AES-256, a passphrase only the
#      deployment's owner holds) into the off-host directory, then decrypts it
#      again and checks the checksum before calling the copy done;
#   3. keeps an encrypted copy of the signed deployment manifest beside them,
#      refreshed whenever it changes (attachments live in the database, so the
#      archive already holds them);
#   4. thins both places to the retention policy (`backup-gfs-prune.sh`);
#   5. once a week, restores the newest archive into a throwaway cluster and
#      checks the schema contract (`verify-postgres-restore.sh`).
#
# Every step is recorded in `common_backuprun` — the backup role's one write —
# which is what the panel shows and alerts on (`common.backup_health`). The
# 3-2-1 rule: the live database, the archive on the backup volume, and the
# encrypted copy somewhere else (a second disk, a network mount, or a folder the
# host syncs to object storage — docs/ops runbook, «Scheduled backups»).
set -eu

fail() { echo "backup-scheduler: $*" >&2; exit 2; }
whole_in() {
    case "$2" in ''|*[!0-9]*) fail "$1 must be a whole number." ;; esac
    [ "$2" -ge "$3" ] && [ "$2" -le "$4" ] || fail "$1 must be between $3 and $4."
}

every_hours="${DOLPHIN_BACKUP_EVERY_HOURS:-6}"
first_at="${DOLPHIN_BACKUP_FIRST_AT:-02:00}"
drill_weekday="${DOLPHIN_RESTORE_DRILL_WEEKDAY:-5}"
whole_in DOLPHIN_BACKUP_EVERY_HOURS "$every_hours" 1 24
whole_in DOLPHIN_RESTORE_DRILL_WEEKDAY "$drill_weekday" 0 7
printf '%s' "$first_at" | grep -Eq '^([01][0-9]|2[0-3]):[0-5][0-9]$' || fail "DOLPHIN_BACKUP_FIRST_AT must be HH:MM."
[ -d /backups ] || fail "the backup volume is not mounted."
[ "$(cat /backups/.dolphin-backup-root 2>/dev/null || true)" = "DOLPHIN_BACKUP_ROOT_V1" ] || fail "the backup volume sentinel is missing."

offsite=/offsite
offsite_ready=0
if [ -d "$offsite" ] && [ "$(cat "$offsite/.dolphin-offsite-root" 2>/dev/null || true)" = "DOLPHIN_OFFSITE_ROOT_V1" ]; then
    offsite_ready=1
fi
passphrase="${DOLPHIN_BACKUP_PASSPHRASE:-}"
if [ "$offsite_ready" -eq 1 ] && [ "${#passphrase}" -lt 24 ]; then
    fail "DOLPHIN_BACKUP_PASSPHRASE must be at least 24 characters to encrypt the off-host copy."
fi

export LC_ALL=C
export PGPASSWORD="${POSTGRES_BACKUP_PASSWORD:?}"
export PGAPPNAME=dolphin_backup_scheduler
export GNUPGHOME="${TMPDIR:-/tmp}/dolphin-gnupg"
mkdir -p -m 0700 "$GNUPGHOME"
umask 077

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# One row in `common_backuprun`. Values travel as psql variables, quoted by
# psql itself (`:'name'`), never spliced into the statement.
record() {
    printf '%s\n' "INSERT INTO common_backuprun (kind, status, started_at, finished_at, archive, size_bytes, detail, created_at) VALUES (:'kind', :'status', :'started'::timestamptz, :'finished'::timestamptz, :'archive', NULLIF(:'size', '')::bigint, :'detail', now());" \
        | psql --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" --username="$POSTGRES_BACKUP_USER" \
            --dbname="$POSTGRES_DB" --no-password --no-psqlrc --quiet --set=ON_ERROR_STOP=1 \
            --set=kind="$1" --set=status="$2" --set=started="$3" --set=finished="$(now_utc)" \
            --set=archive="$4" --set=size="$5" --set=detail="$(printf '%s' "$6" | tr -cd '[:print:]' | cut -c1-290)" \
        >/dev/null 2>&1 || echo "backup-scheduler: could not record a $1 run in the database." >&2
}

newest_archive() {
    find /backups -mindepth 1 -maxdepth 1 -type f -name 'dolphin-pg-*.dump' -print \
        | sed 's#.*/##' \
        | grep -E '^dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}[.]dump$' \
        | sort -r | head -n 1 || true
}

ship_offsite() {
    archive="$1"
    started="$(now_utc)"
    if [ "$offsite_ready" -ne 1 ]; then
        record offsite failed "$started" "$archive" "" "off-host directory not configured"
        return 0
    fi
    source_path="/backups/$archive"
    expected="$(cut -d' ' -f1 "/backups/$archive.sha256")"
    temp="$offsite/.$archive.gpg.tmp"
    final="$offsite/$archive.gpg"
    rm -f -- "$temp"
    if ! printf '%s' "$passphrase" | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 \
            --symmetric --cipher-algo AES256 --s2k-digest-algo SHA512 --s2k-mode 3 --s2k-count 65011712 \
            --compress-algo none --output "$temp" "$source_path" 2>/dev/null; then
        rm -f -- "$temp"
        record offsite failed "$started" "$archive" "" "encryption failed"
        return 0
    fi
    # Called done only once the copy decrypts back to the very same bytes.
    actual="$(printf '%s' "$passphrase" | gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 0 \
        --decrypt "$temp" 2>/dev/null | sha256sum | cut -d' ' -f1)"
    if [ "$actual" != "$expected" ]; then
        rm -f -- "$temp"
        record offsite failed "$started" "$archive" "" "the encrypted copy did not verify"
        return 0
    fi
    mv -f -- "$temp" "$final"
    hash="$(sha256sum "$final" | cut -d' ' -f1)"
    printf '%s  %s\n' "$hash" "$archive.gpg" >"$final.sha256"
    record offsite ok "$started" "$archive.gpg" "$(stat -c %s "$final")" "verified"
}

# A server rebuilt from the off-host copy needs the same features enabled, so
# the signed manifest goes there too — only when it changed. Its `.sha256`
# holds the plaintext's hash, which is what is compared next time.
ship_manifest() {
    [ "$offsite_ready" -eq 1 ] && [ -f /profile/manifest.json ] || return 0
    manifest_hash="$(sha256sum /profile/manifest.json | cut -d' ' -f1)"
    [ "$(cut -d' ' -f1 "$offsite/deployment-manifest.json.sha256" 2>/dev/null || true)" != "$manifest_hash" ] || return 0
    temp="$offsite/.deployment-manifest.json.gpg.tmp"
    rm -f -- "$temp"
    if printf '%s' "$passphrase" | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 \
            --symmetric --cipher-algo AES256 --s2k-digest-algo SHA512 --s2k-mode 3 --s2k-count 65011712 \
            --output "$temp" /profile/manifest.json 2>/dev/null; then
        mv -f -- "$temp" "$offsite/deployment-manifest.json.gpg"
        printf '%s  %s\n' "$manifest_hash" deployment-manifest.json >"$offsite/deployment-manifest.json.sha256"
    else
        rm -f -- "$temp"
        echo "backup-scheduler: could not copy the deployment manifest off the host." >&2
    fi
}

prune() {
    started="$(now_utc)"
    if summary="$(sh /ops/backup-gfs-prune.sh /backups dump 2>&1)"; then
        detail="local: $summary"
        status=ok
    else
        detail="local prune failed: $summary"
        status=failed
    fi
    if [ "$offsite_ready" -eq 1 ]; then
        if offsite_summary="$(sh /ops/backup-gfs-prune.sh "$offsite" dump.gpg 2>&1)"; then
            detail="$detail; off-host: $offsite_summary"
        else
            detail="$detail; off-host prune failed: $offsite_summary"
            status=failed
        fi
    fi
    record prune "$status" "$started" "" "" "$detail"
}

drill_marker=/backups/.dolphin-last-restore-drill
drill_if_due() {
    [ "$drill_weekday" -ne 0 ] || return 0
    [ "$(date +%u)" -eq "$drill_weekday" ] || return 0
    [ "$(cat "$drill_marker" 2>/dev/null || true)" != "$(date +%Y-%m-%d)" ] || return 0
    archive="$(newest_archive)"
    [ -n "$archive" ] || return 0
    started="$(now_utc)"
    if output="$(sh /ops/verify-postgres-restore.sh "$archive" 2>&1)"; then
        record drill ok "$started" "$archive" "$(stat -c %s "/backups/$archive")" "restored and the schema contract held"
    else
        record drill failed "$started" "$archive" "" "$(printf '%s' "$output" | tail -n 1)"
    fi
    date +%Y-%m-%d >"$drill_marker"
}

run_cycle() {
    started="$(now_utc)"
    if output="$(POSTGRES_BACKUP_RETENTION_DAYS=0 sh /ops/backup-postgres.sh 2>&1)"; then
        archive="$(printf '%s\n' "$output" | sed -n 's/^Backup created: //p' | tail -n 1)"
        record backup ok "$started" "$archive" "$(stat -c %s "/backups/$archive")" "dump verified"
        ship_offsite "$archive"
        ship_manifest
    else
        record backup failed "$started" "" "" "$(printf '%s' "$output" | tail -n 1)"
    fi
    prune
    drill_if_due
}

# The next slot: FIRST_AT, then every EVERY_HOURS, in the container's TZ.
next_slot() {
    now="$(date +%s)"
    slot="$(date -d "$(date +%Y-%m-%d) $first_at" +%s)"
    slot=$((slot - 86400))
    step=$((every_hours * 3600))
    while [ "$slot" -le "$now" ]; do slot=$((slot + step)); done
    echo "$slot"
}

# Catch up at start when the newest archive is older than one interval.
newest="$(newest_archive)"
if [ -z "$newest" ]; then
    run_cycle
else
    stamp="${newest#dolphin-pg-}"
    stamp="${stamp%%-*}"
    taken="$(printf '%s' "$stamp" | sed -E 's/^(....)(..)(..)T(..)(..)(..)Z$/\1-\2-\3 \4:\5:\6/')"
    age=$(( $(date -u +%s) - $(date -u -d "$taken" +%s) ))
    if [ "$age" -ge $((every_hours * 3600)) ]; then run_cycle; fi
fi

while :; do
    slot="$(next_slot)"
    pause=$((slot - $(date +%s)))
    [ "$pause" -le 0 ] || sleep "$pause"
    run_cycle
done
