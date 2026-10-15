#!/bin/sh
# Grandfather-father-son retention for Dolphin backups (2.40.50, BIZ-009).
#
#   sh backup-gfs-prune.sh DIRECTORY dump        # the local volume: X.dump + X.dump.sha256
#   sh backup-gfs-prune.sh DIRECTORY dump.gpg    # the off-host copy: X.dump.gpg + X.dump.gpg.sha256
#
# Keeps, among archives named exactly `dolphin-pg-YYYYMMDDTHHMMSSZ-<32 hex>`:
#   * the newest one, always;
#   * everything younger than DOLPHIN_BACKUP_KEEP_RECENT_HOURS (default 24);
#   * the newest of each day for DOLPHIN_BACKUP_KEEP_DAILY days (default 7);
#   * the newest of each ISO week for DOLPHIN_BACKUP_KEEP_WEEKLY weeks (default 4);
#   * the newest of each month for DOLPHIN_BACKUP_KEEP_MONTHLY months (default 12).
# Removes every other such archive with its checksum, and touches nothing whose
# name is not exactly that shape. Ages come from the UTC stamp in the name, not
# from file times, so a copy keeps its age wherever it lives. Every date is
# converted in one `date -f` call, not one process per archive.
#
# DOLPHIN_PRUNE_NOW_EPOCH overrides "now" and DOLPHIN_PRUNE_DRY_RUN=1 only
# prints, for tests. Prints one summary line: `kept N removed M`.
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: backup-gfs-prune.sh DIRECTORY dump|dump.gpg" >&2
    exit 2
fi
directory="$1"
suffix="$2"
case "$suffix" in
    dump) suffix_pattern='dump' ;;
    dump.gpg) suffix_pattern='dump[.]gpg' ;;
    *) echo "The suffix must be dump or dump.gpg." >&2; exit 2 ;;
esac
if [ ! -d "$directory" ] || [ -L "$directory" ]; then
    echo "The archive directory must be a real directory." >&2
    exit 2
fi

whole() {
    case "$2" in
        ''|*[!0-9]*) echo "$1 must be a whole number." >&2; exit 2 ;;
    esac
}
recent_hours="${DOLPHIN_BACKUP_KEEP_RECENT_HOURS:-24}"
keep_daily="${DOLPHIN_BACKUP_KEEP_DAILY:-7}"
keep_weekly="${DOLPHIN_BACKUP_KEEP_WEEKLY:-4}"
keep_monthly="${DOLPHIN_BACKUP_KEEP_MONTHLY:-12}"
now="${DOLPHIN_PRUNE_NOW_EPOCH:-$(date -u +%s)}"
whole DOLPHIN_BACKUP_KEEP_RECENT_HOURS "$recent_hours"
whole DOLPHIN_BACKUP_KEEP_DAILY "$keep_daily"
whole DOLPHIN_BACKUP_KEEP_WEEKLY "$keep_weekly"
whole DOLPHIN_BACKUP_KEEP_MONTHLY "$keep_monthly"
whole DOLPHIN_PRUNE_NOW_EPOCH "$now"

export LC_ALL=C
work="$(mktemp -d "${TMPDIR:-/tmp}/dolphin-prune.XXXXXXXX")"
trap 'rm -rf -- "$work"' EXIT

# name, then its UTC date and time, newest first.
find "$directory" -mindepth 1 -maxdepth 1 -type f -name "dolphin-pg-*" -print \
    | sed 's#.*/##' \
    | grep -E "^dolphin-pg-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}[.]${suffix_pattern}\$" \
    | sort -r \
    | sed -E 's/^(dolphin-pg-([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})Z-.*)$/\1 \2-\3-\4 \5:\6:\7/' \
    >"$work/list" || true
if [ ! -s "$work/list" ]; then
    echo "kept 0 removed 0"
    exit 0
fi
cut -d' ' -f2,3 "$work/list" | date -u -f - +%s >"$work/taken"
cut -d' ' -f2 "$work/list" | date -u -f - +%s >"$work/day"
cut -d' ' -f2 "$work/list" | date -u -f - +%G%V >"$work/week"
cut -d' ' -f1 "$work/list" >"$work/names"
today="$(date -u -d "@$now" +%Y-%m-%d)"
today="$(date -u -d "$today" +%s)"

paste -d' ' "$work/names" "$work/taken" "$work/day" "$work/week" | {
    seen_days=" "
    seen_weeks=" "
    seen_months=" "
    newest=1
    kept=0
    removed=0
    while read -r name taken day week; do
        stamp="${name#dolphin-pg-}"
        ymd="${stamp%%T*}"
        month="${ymd%??}"
        age_hours=$(( (now - taken) / 3600 ))
        age_days=$(( (today - day) / 86400 ))
        keep=0
        if [ "$newest" -eq 1 ]; then
            keep=1
            newest=0
        fi
        if [ "$age_hours" -lt "$recent_hours" ]; then
            keep=1
        fi
        case "$seen_days" in
            *" $day "*) ;;
            *)
                seen_days="$seen_days$day "
                if [ "$age_days" -lt "$keep_daily" ]; then keep=1; fi
                ;;
        esac
        case "$seen_weeks" in
            *" $week "*) ;;
            *)
                seen_weeks="$seen_weeks$week "
                if [ "$age_days" -lt $((keep_weekly * 7)) ]; then keep=1; fi
                ;;
        esac
        case "$seen_months" in
            *" $month "*) ;;
            *)
                seen_months="$seen_months$month "
                if [ "$age_days" -lt $((keep_monthly * 31)) ]; then keep=1; fi
                ;;
        esac
        if [ "$keep" -eq 1 ]; then
            kept=$((kept + 1))
            continue
        fi
        removed=$((removed + 1))
        if [ "${DOLPHIN_PRUNE_DRY_RUN:-0}" = "1" ]; then
            printf 'would remove %s\n' "$name"
            continue
        fi
        rm -f -- "$directory/$name" "$directory/$name.sha256"
    done
    printf 'kept %s removed %s\n' "$kept" "$removed"
}
