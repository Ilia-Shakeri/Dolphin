#!/bin/sh
# Prepare the backup volume's sentinel, once, before the first release or the
# first manual backup. Idempotent: running it again on an already-prepared
# volume reports that and exits 0, rather than failing the way the raw
# one-liner this replaces did — that command's own emptiness check treats the
# sentinel it just wrote as "not empty" on a second run, so it could only ever
# succeed exactly once and gave the same error for "already done" and for "this
# volume has something else in it".
#
# Run from the deployment directory, the one holding compose.yml.
#
#   ./scripts/prepare-backup-volume.sh
#   ./scripts/prepare-backup-volume.sh --env-file secrets/.env
set -eu

ENV_FILE=""
take_next_as_env_file=0
for arg in "$@"; do
    if [ "$take_next_as_env_file" -eq 1 ]; then
        ENV_FILE="$arg"
        take_next_as_env_file=0
    elif [ "$arg" = "--env-file" ]; then
        take_next_as_env_file=1
    fi
done

fail() {
    echo "error: $1" >&2
    exit 2
}

[ -f compose.yml ] || fail "no compose.yml here. Run this from the deployment directory."
if [ -z "$ENV_FILE" ]; then
    if [ -f secrets/.env ]; then
        ENV_FILE="secrets/.env"
    elif [ -f .env ]; then
        ENV_FILE=".env"
    else
        fail "no secrets/.env or .env here. Run this from the deployment directory."
    fi
fi
[ -f "$ENV_FILE" ] || fail "$ENV_FILE does not exist."

volume="$(sed -n 's/^POSTGRES_BACKUP_VOLUME=//p' "$ENV_FILE" | tail -n 1)"
[ -n "$volume" ] || fail "POSTGRES_BACKUP_VOLUME is not set in $ENV_FILE."

echo "==> env file: $ENV_FILE"
echo "==> backup volume: $volume"

mountpoint="$(docker volume inspect -f '{{.Mountpoint}}' "$volume" 2>/dev/null || true)"
if [ -n "$mountpoint" ] && [ -d "$mountpoint" ]; then
    # Best effort: reading the volume's mountpoint directly needs root, and is
    # only possible at all when the local driver backs it. Where it is not
    # possible, fall through to letting the container-side check decide —
    # slower, but it always works.
    for sentinel in .dolphin-backup-root; do
        if [ -f "$mountpoint/$sentinel" ]; then
            echo "==> already prepared ($sentinel found). Nothing to do."
            exit 0
        fi
    done
fi

echo "==> preparing (this must be the volume's first use — it refuses a volume that already holds anything else)"
docker compose --env-file "$ENV_FILE" --profile backup run --rm --no-deps \
    --user root --cap-add CHOWN --entrypoint sh backup -c '
set -eu
for sentinel in .dolphin-backup-root; do
    if [ -f "/backups/$sentinel" ]; then
        echo "already prepared ($sentinel found)."
        exit 0
    fi
done
if [ -n "$(find /backups -mindepth 1 -maxdepth 1 -print -quit)" ]; then
    echo "error: /backups is not empty and has no recognised sentinel." >&2
    echo "       Refusing to touch a volume that might hold something else." >&2
    exit 2
fi
chown root:root /backups
chmod 0700 /backups
printf "%s\n" DOLPHIN_BACKUP_ROOT_V1 > /backups/.dolphin-backup-root
chmod 0600 /backups/.dolphin-backup-root
chown postgres:postgres /backups/.dolphin-backup-root
chown postgres:postgres /backups
echo "prepared."
'
echo "==> done. The backup profile and 'db-finalize' can both write here now."
