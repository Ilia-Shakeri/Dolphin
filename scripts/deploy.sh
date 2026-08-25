#!/bin/sh
# Move this deployment to a given application image tag, or back to a previous
# one. Run from the deployment directory — the one holding compose.yml and .env.
#
#   ./scripts/deploy.sh v1.1.1     switch to that tag
#   ./scripts/deploy.sh --status   what is running now
#   ./scripts/deploy.sh --rollback go back to the tag this script last replaced
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

check_ports_are_free() {
    # Any *other* Compose project publishing 80/443 will make nginx fail to
    # bind, after the rest of the stack has already come up.
    project="$(env_value KARIZ_COMPOSE_PROJECT_NAME)"
    intruders="$(docker ps \
        --filter "publish=80" \
        --format '{{.Names}} {{.Label "com.docker.compose.project"}}' \
        | awk -v p="$project" '$2 != "" && $2 != p {print $1" (project "$2")"}')"
    if [ -n "$intruders" ]; then
        echo "error: another stack already holds port 80:" >&2
        echo "$intruders" | sed 's/^/       /' >&2
        echo "       Stop it first, from its own directory:" >&2
        echo "           docker compose stop nginx web db" >&2
        exit 2
    fi
}

check_database_is_not_shared() {
    # Two Compose projects pointed at one external volume means two PostgreSQL
    # servers over one data directory. PostgreSQL's own lock stops the second
    # from starting, so this shows up as a restart loop rather than as
    # corruption — but it is never intended and is worth refusing.
    volume="$(env_value POSTGRES_DATA_VOLUME)"
    [ -n "$volume" ] || return 0
    project="$(env_value KARIZ_COMPOSE_PROJECT_NAME)"
    sharers="$(docker ps --filter "volume=$volume" \
        --format '{{.Names}} {{.Label "com.docker.compose.project"}}' \
        | awk -v p="$project" '$2 != "" && $2 != p {print $1" (project "$2")"}')"
    if [ -n "$sharers" ]; then
        echo "error: another running stack mounts the same database volume ($volume):" >&2
        echo "$sharers" | sed 's/^/       /' >&2
        echo "       Two PostgreSQL servers must never share one data directory." >&2
        echo "       Stop that stack before continuing." >&2
        exit 2
    fi
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

    if [ "$image" = "$current" ]; then
        note "already on that image; continuing so migrations and static files are refreshed."
    else
        printf '%s\n' "$current" > "$STATE_FILE"
        set_env_value KARIZ_APP_IMAGE "$image"
        note "recorded $current for --rollback"
    fi

    note "backing up the database first"
    $COMPOSE --profile backup run --rm backup

    note "applying migrations and collecting static files"
    $COMPOSE run --rm migrate

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

case "${1:-}" in
    --status|"") show_status ;;
    --rollback)  rollback ;;
    -h|--help)   sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' ;;
    -*)          fail "unknown option: $1" ;;
    *)           deploy "$1" ;;
esac
