#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Pass one exact Dolphin, FrooshBin, or Kariz archive name." >&2
    exit 2
fi
archive_name="$1"
backup_root=/backups
verification_sql=/ops/verify-postgres-schema.sql

if [ ! -d "$backup_root" ] || [ -L "$backup_root" ]; then
    echo "The fixed backup mount must be a real directory." >&2
    exit 2
fi
if ! printf '%s' "$archive_name" | LC_ALL=C grep -Eq \
    '^(dolphin|frooshbin|kariz)-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}[.]dump$'; then
    echo "The restore input must be one exact Dolphin, FrooshBin, or Kariz archive name." >&2
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
    sentinel_path="$backup_root/$sentinel_name"
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

archive_path="$backup_root/$archive_name"
checksum_path="$archive_path.sha256"
if [ ! -f "$archive_path" ] || [ -L "$archive_path" ]; then
    echo "The exact restore archive is missing or is a link." >&2
    exit 2
fi
if [ ! -f "$checksum_path" ] || [ -L "$checksum_path" ]; then
    echo "The exact restore checksum is missing or is a link." >&2
    exit 2
fi
if [ ! -f "$verification_sql" ] || [ -L "$verification_sql" ]; then
    echo "The restore schema contract is missing or is a link." >&2
    exit 2
fi

umask 077
export LC_ALL=C
actual_hash_line="$(sha256sum "$archive_path")"
actual_hash="${actual_hash_line%% *}"
checksum_text="$(cat "$checksum_path")"
if ! printf '%s' "$actual_hash" | grep -Eq '^[0-9a-f]{64}$' || \
   [ "$checksum_text" != "$actual_hash  $archive_name" ]; then
    echo "Backup checksum verification failed." >&2
    exit 3
fi
pg_restore --list "$archive_path" >/dev/null

token="$(od -An -N16 -tx1 /dev/urandom | tr -d '[:space:]')"
if ! printf '%s' "$token" | grep -Eq '^[0-9a-f]{32}$'; then
    echo "A safe restore token could not be made." >&2
    exit 3
fi

restore_root="/tmp/dolphin-restore-$token"
data_dir="$restore_root/data"
socket_dir="$restore_root/socket"
database_name="dolphin_restore_verify_$token"
mkdir -m 0700 "$restore_root"
mkdir -m 0700 "$data_dir" "$socket_dir"

server_started=0
cleanup() {
    status=$?
    trap - EXIT
    if [ "$server_started" -eq 1 ]; then
        pg_ctl --pgdata="$data_dir" --mode=immediate --wait stop >/dev/null 2>&1 || true
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

initdb \
    --pgdata="$data_dir" \
    --username=postgres \
    --auth-local=trust \
    --auth-host=reject \
    --encoding=UTF8 \
    --locale=C >/dev/null
pg_ctl \
    --pgdata="$data_dir" \
    --options="-c listen_addresses='' -c unix_socket_directories='$socket_dir' -c fsync=off -c synchronous_commit=off -c full_page_writes=off" \
    --wait start >/dev/null
server_started=1

createdb \
    --host="$socket_dir" \
    --username=postgres \
    --no-password \
    "$database_name"
pg_restore \
    --host="$socket_dir" \
    --username=postgres \
    --dbname="$database_name" \
    --no-password \
    --no-owner \
    --no-privileges \
    --exit-on-error \
    --single-transaction \
    "$archive_path" >/dev/null

verification_output="$(psql \
    --host="$socket_dir" \
    --username=postgres \
    --dbname="$database_name" \
    --no-password \
    --no-psqlrc \
    --tuples-only \
    --no-align \
    --set=ON_ERROR_STOP=1 \
    --file="$verification_sql"
)"
if [ "$verification_output" != "1" ]; then
    echo "Restored Dolphin schema verification failed." >&2
    exit 4
fi

printf '%s\n' "Disposable restore verification passed."
