#!/bin/sh
# Open the backup directory and the restore spool to the application's group.
#
# Run once, by `scripts/prepare-backup-volume.sh --share-with-panel`, as root
# with CHOWN and FOWNER, on the `backup-agent` service — the one service that
# mounts both volumes. Nothing else ever runs it, and the agent itself runs
# unprivileged as `postgres` in this same group afterwards.
#
# What it is for: the panel and the agent run as different users (10001 and
# 70) and each has to read what the other wrote. A shared group with the
# setgid bit on both directories is what makes that work without making a
# database dump world-readable. See common/backups.py.
set -eu

if [ "$#" -ne 1 ]; then
    echo "share-backup-volume: pass exactly one numeric group id." >&2
    exit 2
fi
gid="$1"
case "$gid" in
    ''|*[!0-9]*)
        echo "share-backup-volume: the group id must be a whole number." >&2
        exit 2
        ;;
esac

for mount in /backups /spool; do
    if [ ! -d "$mount" ] || [ -L "$mount" ]; then
        echo "share-backup-volume: $mount must be a real directory." >&2
        exit 2
    fi
done

sentinel=/backups/.dolphin-backup-root
if [ ! -f "$sentinel" ] || [ -L "$sentinel" ] || \
   [ "$(cat "$sentinel")" != "DOLPHIN_BACKUP_ROOT_V1" ]; then
    echo "share-backup-volume: the backup volume sentinel is missing or invalid." >&2
    exit 2
fi

# setgid on both, so anything created inside inherits the group rather than
# depending on which of the two processes happened to create it.
chown "postgres:$gid" /backups
chmod 2750 /backups
chown "postgres:$gid" /spool
chmod 2770 /spool

# The sentinel itself, not only the archives: `common.backups._checked_root`
# reads it from the panel's own uid on every list/download, and it was
# written 0600 by `prepare-backup-volume.sh` before this group existed. Found
# by running this script against a live volume and then reading the sentinel
# back as the panel's uid, which failed with Permission denied until this
# line was added — the archives being group-readable was not enough on its
# own, because the read that decides whether to show them at all comes first.
chgrp "$gid" "$sentinel"
chmod g+r "$sentinel"

# Archives the scheduled `backup` service published before this group existed
# are 0600 and otherwise invisible to the panel. Opened to the group so the
# deployment's existing backups are offered too, not only the ones taken from
# now on. Matched by the one exact name shape this product produces — never a
# wildcard over whatever else is in the directory.
opened=0
for archive in /backups/dolphin-pg-*.dump /backups/dolphin-pg-*.dump.sha256; do
    [ -f "$archive" ] || continue
    [ -L "$archive" ] && continue
    name="$(basename "$archive")"
    if ! printf '%s' "$name" | LC_ALL=C grep -Eq \
        '^dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}[.]dump([.]sha256)?$'; then
        continue
    fi
    chgrp "$gid" "$archive"
    chmod g+r "$archive"
    opened=$((opened + 1))
done

printf 'shared with group %s (%s existing files opened).\n' "$gid" "$opened"
