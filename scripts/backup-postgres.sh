#!/bin/sh
set -eu

require_value() {
    value_name="$1"
    value="$2"
    if [ -z "$value" ]; then
        echo "$value_name must be set." >&2
        exit 2
    fi
}

require_identifier() {
    value_name="$1"
    value="$2"
    require_value "$value_name" "$value"
    if [ "${#value}" -gt 63 ] || \
       printf '%s' "$value" | LC_ALL=C grep -Eq '^pg_' || \
       ! printf '%s' "$value" | LC_ALL=C grep -Eq '^[a-z_][a-z0-9_]*$'; then
        echo "$value_name must be a safe lowercase PostgreSQL identifier." >&2
        exit 2
    fi
}

require_number() {
    value_name="$1"
    value="$2"
    maximum="$3"
    require_value "$value_name" "$value"
    case "$value" in
        *[!0-9]*)
            echo "$value_name must be a whole number." >&2
            exit 2
            ;;
    esac
    if [ "$value" -gt "$maximum" ]; then
        echo "$value_name is outside the safe range." >&2
        exit 2
    fi
}

require_value POSTGRES_HOST "${POSTGRES_HOST:-}"
require_number POSTGRES_PORT "${POSTGRES_PORT:-}" 65535
require_identifier POSTGRES_DB "${POSTGRES_DB:-}"
require_identifier POSTGRES_BACKUP_USER "${POSTGRES_BACKUP_USER:-}"
require_value POSTGRES_BACKUP_PASSWORD "${POSTGRES_BACKUP_PASSWORD:-}"
require_value POSTGRES_BACKUP_ROOT "${POSTGRES_BACKUP_ROOT:-}"
require_number POSTGRES_BACKUP_RETENTION_DAYS "${POSTGRES_BACKUP_RETENTION_DAYS:-}" 3650

if [ "$POSTGRES_PORT" -eq 0 ]; then
    echo "POSTGRES_PORT is outside the safe range." >&2
    exit 2
fi
if [ "${#POSTGRES_BACKUP_PASSWORD}" -lt 16 ]; then
    echo "POSTGRES_BACKUP_PASSWORD must be at least 16 characters." >&2
    exit 2
fi
if [ "$POSTGRES_BACKUP_ROOT" != "/backups" ]; then
    echo "POSTGRES_BACKUP_ROOT must be the fixed /backups mount." >&2
    exit 2
fi
if [ ! -d "$POSTGRES_BACKUP_ROOT" ] || [ -L "$POSTGRES_BACKUP_ROOT" ]; then
    echo "The fixed backup mount must be a real directory." >&2
    exit 2
fi

# A real backup root created under either earlier project name still carries
# its old sentinel file; all three are checked so an already-deployed backup
# root keeps working without a manual fix-up before this script runs again.
sentinel_seen=0
for sentinel_pair in \
    ".dolphin-backup-root:DOLPHIN_BACKUP_ROOT_V1" \
    ".frooshbin-backup-root:FROOSHBIN_BACKUP_ROOT_V1" \
    ".kariz-backup-root:KARIZ_BACKUP_ROOT_V1"; do
    sentinel_name="${sentinel_pair%%:*}"
    sentinel_value="${sentinel_pair#*:}"
    sentinel_path="$POSTGRES_BACKUP_ROOT/$sentinel_name"
    if [ -e "$sentinel_path" ]; then
        sentinel_seen=1
        if [ ! -f "$sentinel_path" ] || [ -L "$sentinel_path" ] || \
           [ "$(cat "$sentinel_path")" != "$sentinel_value" ]; then
            echo "The backup volume sentinel is missing or invalid." >&2
            exit 2
        fi
    fi
done
if [ "$sentinel_seen" -eq 0 ]; then
    echo "The backup volume sentinel is missing or invalid." >&2
    exit 2
fi

umask 077
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
token="$(od -An -N16 -tx1 /dev/urandom | tr -d '[:space:]')"
if ! printf '%s' "$token" | grep -Eq '^[0-9a-f]{32}$'; then
    echo "A safe backup token could not be made." >&2
    exit 3
fi

backup_name="dolphin-pg-$timestamp-$token.dump"
checksum_name="$backup_name.sha256"
temp_dump="$POSTGRES_BACKUP_ROOT/.$backup_name.tmp"
temp_checksum="$POSTGRES_BACKUP_ROOT/.$checksum_name.tmp"
final_dump="$POSTGRES_BACKUP_ROOT/$backup_name"
final_checksum="$POSTGRES_BACKUP_ROOT/$checksum_name"
lock_dir="$POSTGRES_BACKUP_ROOT/.dolphin-backup.lock"
published=0
lock_held=0

for path in "$temp_dump" "$temp_checksum" "$final_dump" "$final_checksum"; do
    if [ -e "$path" ] || [ -L "$path" ]; then
        echo "A generated backup path already exists." >&2
        exit 3
    fi
done

cleanup() {
    status=$?
    trap - EXIT
    rm -f -- "$temp_dump" "$temp_checksum"
    if [ "$published" -ne 1 ]; then
        rm -f -- "$final_dump" "$final_checksum"
    fi
    if [ "$lock_held" -eq 1 ] && ! rmdir "$lock_dir"; then
        echo "The exact backup lock could not be released." >&2
        if [ "$status" -eq 0 ]; then
            status=5
        fi
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! mkdir -m 0700 "$lock_dir" 2>/dev/null; then
    echo "Another backup run or a stale exact backup lock exists." >&2
    exit 5
fi
lock_held=1

export LC_ALL=C
export PGPASSWORD="$POSTGRES_BACKUP_PASSWORD"
export PGAPPNAME=dolphin_backup_job

pg_dump \
    --format=custom \
    --file="$temp_dump" \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_BACKUP_USER" \
    --dbname="$POSTGRES_DB" \
    --no-password
if [ ! -s "$temp_dump" ]; then
    echo "PostgreSQL backup output is empty." >&2
    exit 4
fi
pg_restore --list "$temp_dump" >/dev/null

hash_line="$(sha256sum "$temp_dump")"
hash="${hash_line%% *}"
if ! printf '%s' "$hash" | grep -Eq '^[0-9a-f]{64}$'; then
    echo "Backup checksum generation failed." >&2
    exit 4
fi
printf '%s  %s\n' "$hash" "$backup_name" >"$temp_checksum"

mv "$temp_dump" "$final_dump"
mv "$temp_checksum" "$final_checksum"
published=1

if [ "$POSTGRES_BACKUP_RETENTION_DAYS" -gt 0 ]; then
    retention_age=$((POSTGRES_BACKUP_RETENTION_DAYS - 1))
    candidate_list="/tmp/dolphin-backup-retention-$token"
    find "$POSTGRES_BACKUP_ROOT" \
        -mindepth 1 \
        -maxdepth 1 \
        -type f \
        \( -name 'dolphin-pg-*.dump' -o -name 'frooshbin-pg-*.dump' -o -name 'kariz-pg-*.dump' \) \
        -mtime "+$retention_age" \
        -print >"$candidate_list"
    while IFS= read -r candidate; do
        [ "$candidate" != "$final_dump" ] || continue
        candidate_name="$(basename "$candidate")"
        if ! printf '%s' "$candidate_name" | grep -Eq \
            '^(dolphin|frooshbin|kariz)-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}[.]dump$'; then
            continue
        fi
        checksum_path="$POSTGRES_BACKUP_ROOT/$candidate_name.sha256"
        if [ ! -f "$checksum_path" ] || [ -L "$checksum_path" ]; then
            continue
        fi
        candidate_hash_line="$(sha256sum "$candidate")"
        candidate_hash="${candidate_hash_line%% *}"
        checksum_text="$(cat "$checksum_path")"
        if [ "$checksum_text" != "$candidate_hash  $candidate_name" ]; then
            continue
        fi
        rm -f -- "$candidate"
        rm -f -- "$checksum_path"
    done <"$candidate_list"
    rm -f -- "$candidate_list"
fi

unset PGPASSWORD
printf 'Backup created: %s\n' "$backup_name"
