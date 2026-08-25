#!/bin/sh
# Move this deployment to a given application image tag, or back to a previous
# one. Run from the deployment directory — the one holding compose.yml and .env.
#
#   ./scripts/deploy.sh v1.1.1     switch to that tag
#   ./scripts/deploy.sh --status   what is running now
#   ./scripts/deploy.sh --rollback go back to the tag this script last replaced
#
#   --no-backup   proceed without one. For a deployment whose backup path is
#                 not working yet; never for one holding data you would miss.
#
# This exists because the upgrade is a fixed sequence with three steps that are
# easy to forget and quiet when skipped:
#
#   * `nginx/default.conf` is bind-mounted from this checkout rather than baked
#     into the image, so a release that changed it does nothing until the
#     checkout is updated. Nothing errors; the old limits simply stay in force.
#   * a second Compose project left running holds ports 80 and 443, and the new
#     stack half-starts — database and application up, nginx refused.
#   * migrations must run before the new application serves traffic.
#
# The script refuses to continue rather than half-applying any of them.
set -eu

COMPOSE="docker compose"
ENV_FILE=".env"
SKIP_BACKUP=0
STATE_FILE=".deploy-previous-image"

fail() {
    echo "error: $1" >&2
    exit 2
}

note() { echo "==> $1"; }

env_value() {
    # The value of one key in .env, empty if absent. Deliberately not `source`:
    # this file holds secrets and must never be executed.
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

set_env_value() {
    key="$1"
    value="$2"
    tmp="$(mktemp)"
    if grep -q "^$key=" "$ENV_FILE"; then
        sed "s|^$key=.*|$key=$value|" "$ENV_FILE" > "$tmp"
    else
        cat "$ENV_FILE" > "$tmp"
        printf '%s=%s\n' "$key" "$value" >> "$tmp"
    fi
    # Preserve the original permissions: .env holds secrets and mktemp's
    # ownership is not necessarily the same.
    cat "$tmp" > "$ENV_FILE"
    rm -f "$tmp"
}

require_deployment_directory() {
    [ -f compose.yml ] || fail "no compose.yml here. Run this from the deployment directory."
    [ -f "$ENV_FILE" ] || fail "no $ENV_FILE here. Run this from the deployment directory."
}

show_status() {
    note "project:  $(env_value KARIZ_COMPOSE_PROJECT_NAME)"
    note "image:    $(env_value KARIZ_APP_IMAGE)"
    note "database: $(env_value POSTGRES_DATA_VOLUME)"
    echo
    $COMPOSE ps
    echo
    note "every ForooshBin container on this host:"
    docker ps --filter "name=forooshbin" \
        --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
}

# --- preflight ------------------------------------------------------------

check_image_exists() {
    docker image inspect "$1" >/dev/null 2>&1 \
        || fail "image $1 is not on this host. Load or build it first."
}

check_nginx_config_is_current() {
    # Only meaningful in a git checkout. A deployment that took the runtime
    # files by copy has to keep them in step by hand, and is told so.
    if [ ! -d .git ]; then
        note "not a git checkout — confirm nginx/default.conf matches this release by hand."
        return 0
    fi
    if ! git rev-parse --verify --quiet origin/main >/dev/null 2>&1; then
        note "no origin/main to compare against — skipping the nginx check."
        return 0
    fi
    if ! git diff --quiet origin/main -- nginx/; then
        fail "nginx/ differs from origin/main. The nginx config is bind-mounted from
       this checkout, so a stale copy silently keeps the old limits in force. Fix with:

           git fetch origin && git checkout origin/main -- nginx/

       then run this script again."
    fi
}

foreign_containers_matching() {
    # Containers matching a `docker ps` filter that do NOT belong to this
    # deployment. Membership is decided by asking Compose for its own container
    # ids rather than by comparing the project label against a name read out of
    # .env: the project can be set in the environment rather than the file, and
    # a name this script failed to find made every container look foreign —
    # including the deployment's own database.
    own="$($COMPOSE ps -aq 2>/dev/null || true)"
    docker ps --no-trunc --filter "$1" --format '{{.ID}} {{.Names}}' \
        | while read -r id name; do
              printf '%s\n' "$own" | grep -qx "$id" || printf '%s\n' "$name"
          done
}

check_ports_are_free() {
    # Any other project publishing 80 will make nginx fail to bind, after the
    # rest of the stack has already come up.
    intruders="$(foreign_containers_matching 'publish=80')"
    if [ -n "$intruders" ]; then
        echo "error: another stack already holds port 80:" >&2
        echo "$intruders" | sed 's/^/       /' >&2
        echo "       Stop it first, from its own directory:" >&2
        echo "           docker compose stop nginx web db" >&2
        exit 2
    fi
}

check_database_is_not_shared() {
    # Two projects over one external volume means two PostgreSQL servers over
    # one data directory. PostgreSQL's own lock stops the second from starting,
    # so it shows up as a restart loop rather than as corruption — but it is
    # never intended and is worth refusing.
    volume="$(env_value POSTGRES_DATA_VOLUME)"
    [ -n "$volume" ] || return 0
    sharers="$(foreign_containers_matching "volume=$volume")"
    if [ -n "$sharers" ]; then
        echo "error: another running stack mounts the same database volume ($volume):" >&2
        echo "$sharers" | sed 's/^/       /' >&2
        echo "       Two PostgreSQL servers must never share one data directory." >&2
        echo "       Stop that stack before continuing." >&2
        exit 2
    fi
}

check_backup_volume_is_prepared() {
    # The backup job refuses a volume without its sentinel — that is what stops
    # it writing a database dump into the wrong place. Preparing the volume is a
    # one-time step (runbook 4.1), easy to have never done on a deployment that
    # has not been backed up yet. Checked here so the release stops before
    # anything starts and says what to run, rather than failing halfway with a
    # message about a sentinel.
    #
    # Best effort: this reads the volume through the local driver's mountpoint,
    # which needs root. Where that is not possible the check stands aside rather
    # than blocking a release it cannot judge.
    volume="$(env_value POSTGRES_BACKUP_VOLUME)"
    [ -n "$volume" ] || return 0
    mountpoint="$(docker volume inspect -f '{{.Mountpoint}}' "$volume" 2>/dev/null || true)"
    if [ -z "$mountpoint" ] || [ ! -d "$mountpoint" ]; then
        note "cannot read volume $volume from here — skipping the backup-volume check."
        return 0
    fi
    if [ -f "$mountpoint/.frooshbin-backup-root" ] || [ -f "$mountpoint/.kariz-backup-root" ]; then
        return 0
    fi
    echo "error: the backup volume ($volume) has no sentinel, so the backup job will" >&2
    echo "       refuse to write to it. Prepare it once (runbook 4.1), from this" >&2
    echo "       directory, then run this script again:" >&2
    echo >&2
    # Quoted so the shell expands nothing: this is text to be copied, and the
    # inner $(find ...) must reach the reader intact.
    cat >&2 <<'PREPARE'
    docker compose --profile backup run --rm --no-deps --user root --cap-add CHOWN --entrypoint sh backup -c 'set -eu; test -z "$(find /backups -mindepth 1 -maxdepth 1 -print -quit)"; chown root:root /backups; chmod 0700 /backups; printf "%s\n" FROOSHBIN_BACKUP_ROOT_V1 > /backups/.frooshbin-backup-root; chmod 0600 /backups/.frooshbin-backup-root; chown postgres:postgres /backups/.frooshbin-backup-root; chown postgres:postgres /backups'
PREPARE
    echo >&2
    exit 2
}

# --- the release ----------------------------------------------------------

deploy() {
    target="$1"
    case "$target" in
        *:*) image="$target" ;;
        # A bare tag is the usual case; spell out the repository for the caller.
        *)   image="forooshbin-app:$target" ;;
    esac

    current="$(env_value KARIZ_APP_IMAGE)"
    note "current image: ${current:-none}"
    note "target image:  $image"

    check_image_exists "$image"
    check_nginx_config_is_current
    check_ports_are_free
    check_database_is_not_shared
    if [ "$SKIP_BACKUP" -eq 0 ]; then
        check_backup_volume_is_prepared
    fi

    if [ "$image" = "$current" ]; then
        note "already on that image; continuing so migrations and static files are refreshed."
    else
        printf '%s\n' "$current" > "$STATE_FILE"
        set_env_value KARIZ_APP_IMAGE "$image"
        note "recorded $current for --rollback"
    fi

    if [ "$SKIP_BACKUP" -eq 1 ]; then
        note "SKIPPING THE BACKUP because --no-backup was given."
    else
        note "backing up the database first"
        # `backup` depends on `db` alone, so on a stack whose roles have not been
        # provisioned against this database it authenticates before
        # `db-bootstrap` has ever had a chance to set their passwords. Bootstrap
        # first, so the backup meets the credentials the .env actually describes.
        # -T matters, it is not tidiness. `docker compose run` attaches a
        # TTY by default, and psql's \password reads from the terminal rather
        # than from stdin whenever one is present — so bootstrap prompts the
        # operator and silently discards the passwords the script piped in from
        # .env. The roles then carry whatever the terminal supplied, and the
        # next backup fails to authenticate. Without a TTY, \password reads
        # the piped stdin, which is what this path was written for.
        $COMPOSE run --rm -T db-bootstrap
        $COMPOSE --profile backup run --rm -T backup
    fi

    note "applying migrations and collecting static files"
    $COMPOSE run --rm -T migrate

    note "starting the stack"
    $COMPOSE up -d

    note "running version, read from the container:"
    $COMPOSE exec -T web cat /app/VERSION 2>/dev/null \
        || note "could not read /app/VERSION — check the panel footer instead."

    echo
    $COMPOSE ps
    echo
    note "done. Confirm the version in the panel footer before testing."
}

rollback() {
    [ -f "$STATE_FILE" ] || fail "no previous image recorded — nothing to roll back to."
    previous="$(cat "$STATE_FILE")"
    [ -n "$previous" ] || fail "the recorded previous image is empty."
    note "rolling back to $previous"
    # Migrations are not reversed. Every migration this project ships is
    # additive, so the older application ignores what it does not know about.
    # A migration that ever stops being additive must be reversed by hand, and
    # that decision does not belong in a script.
    deploy "$previous"
}

require_deployment_directory

# --no-backup may come before or after the tag; take it from anywhere.
args=""
for arg in "$@"; do
    if [ "$arg" = "--no-backup" ]; then
        SKIP_BACKUP=1
    else
        args="${args:+$args }$arg"
    fi
done
# shellcheck disable=SC2086
set -- $args

case "${1:-}" in
    --status|"") show_status ;;
    --rollback)  rollback ;;
    -h|--help)   sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' ;;
    -*)          fail "unknown option: $1" ;;
    *)           deploy "$1" ;;
esac
