#!/bin/sh
# The privileged half of «پشتیبان‌گیری و بازگردانی از پنل».
#
# The application container cannot back up or restore anything, and that is
# deliberate: it is read-only, holds no PostgreSQL client tools, and
# connects as a NOSUPERUSER role with table-level grants (see
# scripts/bootstrap-postgres.sh and common/tests/test_database_privileges.py).
# This job is the other side of that split. It holds the credentials the web
# container must never hold, and it takes its instructions from exactly one
# place: request files on the spool volume. No socket, no shell, no network
# input — it joins the internal `backend` network only, to reach the
# database.
#
# Read common/backups.py for the whole design and the trade it carries. In
# one line: a deployment that runs this agent has accepted that one
# authenticated Platform Admin request can replace the entire database, and
# a deployment that does not run it keeps exactly the posture it had before
# (the panel then reports the request as waiting, which is the truth).
#
# Run it from the reviewed release directory, behind its own profile:
#
#   docker compose --env-file secrets/.env --profile backup-agent up -d backup-agent
set -eu

fail() {
    echo "backup-agent: $1" >&2
    exit "${2:-2}"
}

require_value() {
    [ -n "$2" ] || fail "$1 must be set."
}

require_identifier() {
    require_value "$1" "$2"
    if [ "${#2}" -gt 63 ] || \
       printf '%s' "$2" | LC_ALL=C grep -Eq '^pg_' || \
       ! printf '%s' "$2" | LC_ALL=C grep -Eq '^[a-z_][a-z0-9_]*$'; then
        fail "$1 must be a safe lowercase PostgreSQL identifier."
    fi
}

require_value POSTGRES_HOST "${POSTGRES_HOST:-}"
require_value POSTGRES_PORT "${POSTGRES_PORT:-}"
require_identifier POSTGRES_DB "${POSTGRES_DB:-}"
require_identifier POSTGRES_INIT_USER "${POSTGRES_INIT_USER:-}"
require_value POSTGRES_INIT_PASSWORD "${POSTGRES_INIT_PASSWORD:-}"
require_identifier POSTGRES_APP_USER "${POSTGRES_APP_USER:-}"

BACKUP_ROOT="${BACKUP_ROOT:-/backups}"
SPOOL_ROOT="${SPOOL_ROOT:-/spool}"
POLL_SECONDS="${BACKUP_AGENT_POLL_SECONDS:-5}"
case "$POLL_SECONDS" in
    ''|*[!0-9]*) fail "BACKUP_AGENT_POLL_SECONDS must be a whole number." ;;
esac
[ "$POLL_SECONDS" -ge 1 ] || fail "BACKUP_AGENT_POLL_SECONDS must be at least 1."

[ -d "$BACKUP_ROOT" ] && [ ! -L "$BACKUP_ROOT" ] || fail "The fixed backup mount must be a real directory."
[ -d "$SPOOL_ROOT" ] && [ ! -L "$SPOOL_ROOT" ] || fail "The fixed spool mount must be a real directory."

sentinel="$BACKUP_ROOT/.dolphin-backup-root"
if [ ! -f "$sentinel" ] || [ -L "$sentinel" ] || \
   [ "$(cat "$sentinel")" != "DOLPHIN_BACKUP_ROOT_V1" ]; then
    fail "The backup volume sentinel is missing or invalid."
fi

# 027, not 077 like scripts/backup-postgres.sh.
#
# That difference is the whole reason this agent can work with the panel at
# all, so it is worth being exact about. The scheduled backup job writes for
# nobody but itself, and 0600 is right for it. This one publishes archives
# the `web` container has to read and consumes uploads that container wrote,
# and the two run as different users. The shared *group* (see `user:` on the
# backup-agent service in compose.yml, and the setgid bit
# `prepare-backup-volume.sh --share-with-panel` puts on both directories) is
# what they have in common, so group-readable is exactly the access needed
# and no more — a dump never becomes world-readable.
umask 027
export LC_ALL=C
export PGAPPNAME=dolphin_backup_agent

# --- helpers ----------------------------------------------------------------

# One JSON string field, read without a JSON parser: this image has `sh` and
# the PostgreSQL client tools and nothing else, and adding an interpreter to
# a privileged container to read four fields would be a poor trade. The
# request files are written by common/backups.py with `sort_keys=True`, no
# nesting and no escapes, so the shape is known exactly rather than guessed.
json_field() {
    sed -n 's/.*"'"$2"'"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" | head -n 1
}

write_result() {
    result_token="$1"
    result_status="$2"
    result_message="$3"
    result_safety="${4:-}"
    result_final="$SPOOL_ROOT/$result_token.result.json"
    result_temp="$SPOOL_ROOT/.$result_token.result.json.tmp"
    printf '{"finished_at":"%s","message":"%s","safety_backup":"%s","status":"%s","token":"%s"}\n' \
        "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
        "$(printf '%s' "$result_message" | tr -d '"\\' | tr '\n' ' ')" \
        "$result_safety" \
        "$result_status" \
        "$result_token" >"$result_temp"
    mv "$result_temp" "$result_final"
}

# A backup taken by this agent, with the same name shape, the same custom
# format and the same checksum sidecar the scheduled `backup` service
# produces — one archive vocabulary across the product, not two. Prints the
# archive name on success and nothing on failure, so a caller can write
# `if name="$(take_backup)"`.
take_backup() {
    backup_timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    backup_token="$(od -An -N16 -tx1 /dev/urandom | tr -d '[:space:]')"
    printf '%s' "$backup_token" | grep -Eq '^[0-9a-f]{32}$' || return 1
    backup_name="dolphin-pg-$backup_timestamp-$backup_token.dump"
    backup_temp="$BACKUP_ROOT/.$backup_name.tmp"

    PGPASSWORD="$POSTGRES_INIT_PASSWORD" pg_dump \
        --format=custom \
        --file="$backup_temp" \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_INIT_USER" \
        --dbname="$POSTGRES_DB" \
        --no-password >&2 || { rm -f -- "$backup_temp"; return 1; }
    [ -s "$backup_temp" ] || { rm -f -- "$backup_temp"; return 1; }
    pg_restore --list "$backup_temp" >/dev/null 2>&1 || { rm -f -- "$backup_temp"; return 1; }

    backup_hash_line="$(sha256sum "$backup_temp")"
    backup_hash="${backup_hash_line%% *}"
    printf '%s  %s\n' "$backup_hash" "$backup_name" >"$BACKUP_ROOT/.$backup_name.sha256.tmp"
    mv "$backup_temp" "$BACKUP_ROOT/$backup_name"
    mv "$BACKUP_ROOT/.$backup_name.sha256.tmp" "$BACKUP_ROOT/$backup_name.sha256"
    printf '%s' "$backup_name"
}

# Close the application out of the database, and let it back in. Writes are
# stopped this way rather than by stopping the web container, because this
# agent has no Docker socket and must never have one. `app_user` holds
# CONNECT explicitly and PUBLIC holds nothing (bootstrap-postgres.sh), so
# withdrawing that one grant and dropping the open backends really does
# leave `pg_restore` alone with the database.
# On stdin, not `--command`. Measured, not assumed: `psql -c` runs its
# argument as a single SQL string and does **not** process psql's own
# meta-commands, so `\gexec` and `:'identifier'` interpolation -- which is
# how scripts/bootstrap-postgres.sh safely quotes a role name into DDL --
# came back as `syntax error at or near ":"`. The first drill of this
# agent caught exactly that, and caught it in the right place: the restore
# refused to continue because it could not close the application out, the
# safety backup had already been taken, and no data was touched.
run_sql() {
    PGPASSWORD="$POSTGRES_INIT_PASSWORD" psql \
        --quiet --no-password --set=ON_ERROR_STOP=1 \
        --host="$POSTGRES_HOST" --port="$POSTGRES_PORT" \
        --username="$POSTGRES_INIT_USER" --dbname="$POSTGRES_DB" \
        --set=app_user="$POSTGRES_APP_USER" \
        --set=db_name="$POSTGRES_DB" >/dev/null
}

lock_app_out() {
    run_sql <<'SQL' || return 1
SELECT format('REVOKE CONNECT ON DATABASE %I FROM %I', :'db_name', :'app_user') \gexec
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid();
SQL
}

let_app_back_in() {
    run_sql <<'SQL' || return 1
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'app_user') \gexec
SQL
}

# --- the two jobs -----------------------------------------------------------

handle_backup() {
    token="$1"
    if name="$(take_backup)"; then
        write_result "$token" "done" "پشتیبان ساخته شد: $name" "$name"
    else
        write_result "$token" "failed" "ساخت پشتیبان ناموفق بود."
    fi
}

handle_restore() {
    token="$1"
    request="$2"
    upload_name="$(json_field "$request" upload)"
    expected_hash="$(json_field "$request" sha256)"

    case "$upload_name" in
        ''|*[!a-z0-9.]*)
            write_result "$token" "failed" "نام فایل بارگذاری‌شده معتبر نیست."
            return
            ;;
    esac
    if ! printf '%s' "$expected_hash" | grep -Eq '^[0-9a-f]{64}$'; then
        write_result "$token" "failed" "اثر انگشت فایل معتبر نیست."
        return
    fi
    upload_path="$SPOOL_ROOT/$upload_name"
    if [ ! -f "$upload_path" ] || [ -L "$upload_path" ]; then
        write_result "$token" "failed" "فایل بارگذاری‌شده پیدا نشد."
        return
    fi

    # Re-hashed here, not trusted from the request: the web container wrote
    # both, and the whole point of the split is that this side checks.
    actual_line="$(sha256sum "$upload_path")"
    actual_hash="${actual_line%% *}"
    if [ "$actual_hash" != "$expected_hash" ]; then
        write_result "$token" "failed" "اثر انگشت فایل با آنچه ثبت شده یکی نیست."
        return
    fi
    if ! pg_restore --list "$upload_path" >/dev/null 2>&1; then
        write_result "$token" "failed" "این فایل یک پشتیبان custom-format معتبر پستگرس نیست."
        return
    fi

    # Always, before anything is destroyed. The runbook makes this step 3 of
    # the manual disaster procedure and calls it evidence; a restore driven
    # from a web page must not be able to skip it.
    if ! safety="$(take_backup)"; then
        write_result "$token" "failed" "پشتیبان ایمنی پیش از بازگردانی ساخته نشد؛ بازگردانی انجام نشد."
        return
    fi

    if ! lock_app_out; then
        let_app_back_in || true
        write_result "$token" "failed" "دسترسی برنامه به پایگاه داده بسته نشد؛ بازگردانی انجام نشد." "$safety"
        return
    fi

    restore_status=0
    PGPASSWORD="$POSTGRES_INIT_PASSWORD" pg_restore \
        --clean --if-exists --no-owner --exit-on-error \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_INIT_USER" \
        --dbname="$POSTGRES_DB" \
        --no-password \
        "$upload_path" >&2 || restore_status=$?

    # Grants come back whether the restore worked or not. A failed restore
    # that also left the application locked out would turn a recoverable
    # problem into an outage.
    let_app_back_in || true

    if [ "$restore_status" -ne 0 ]; then
        write_result "$token" "failed" \
            "بازگردانی ناموفق بود. پایگاه داده ممکن است ناقص باشد؛ پشتیبان ایمنی پیش از شروع ساخته شده است." "$safety"
        return
    fi

    rm -f -- "$upload_path"
    write_result "$token" "done" \
        "بازگردانی انجام شد. برای بازگرداندن کامل مجوزهای پایگاه داده، db-finalize را اجرا کنید." "$safety"
}

# --- the loop ---------------------------------------------------------------

echo "backup-agent: watching $SPOOL_ROOT every ${POLL_SECONDS}s"
while true; do
    for request in "$SPOOL_ROOT"/*.request.json; do
        [ -f "$request" ] || continue
        if [ -L "$request" ]; then
            continue
        fi

        token="$(json_field "$request" token)"
        if ! printf '%s' "$token" | grep -Eq '^[0-9a-f]{32}$'; then
            rm -f -- "$request"
            continue
        fi
        [ -f "$SPOOL_ROOT/$token.result.json" ] && continue

        # An expired request is refused rather than run late: one that sat
        # in the spool because the agent was stopped must not execute when
        # it is started again, hours later, against a database that has
        # moved on. Both sides write `%Y-%m-%dT%H:%M:%SZ` in UTC, so the
        # lexical comparison below is a chronological one.
        expires_at="$(json_field "$request" expires_at)"
        now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
        if [ -n "$expires_at" ] && [ "$now" \> "$expires_at" ]; then
            write_result "$token" "expired" "این درخواست منقضی شده بود و اجرا نشد."
            continue
        fi

        kind="$(json_field "$request" kind)"
        case "$kind" in
            backup) handle_backup "$token" ;;
            restore) handle_restore "$token" "$request" ;;
            *) write_result "$token" "failed" "نوع درخواست شناخته نشد." ;;
        esac
    done
    sleep "$POLL_SECONDS"
done
