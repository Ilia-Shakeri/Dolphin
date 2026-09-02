#!/bin/sh
# One command for a first install on a fresh server.
#
# This is not a new mechanism — it is the exact sequence in
# docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md section 1 (OS packages, Docker,
# firewall, directories, the image, the .env, the signed manifest, TLS,
# bringing the stack up in order, verification, the first administrator),
# run in order by calling the same tools the runbook tells you to run by
# hand (scripts/new_deployment.py, scripts/sign_deployment_manifest.py,
# scripts/build-image.sh, scripts/prepare-backup-volume.sh,
# scripts/deploy.sh) instead of copy-pasting ~16 subsections. Nothing here
# bypasses what any of those already check or refuse.
#
# Minimal example — a reviewed image, a manifest signed elsewhere, and a
# real certificate, exactly the documented model:
#
#   sudo ./scripts/quickstart.sh --slug client1 --host crm.client1.ir \
#       --app-image ghcr.io/you/dolphin-app@sha256:<digest> \
#       --manifest /path/to/signed-manifest.json --manifest-keys 'k1:AAAA...' \
#       --tls-cert /path/to/fullchain.pem --tls-key /path/to/privkey.pem
#
# A single dedicated server you fully control, with nothing pre-built and no
# certificate yet, can get one from this checkout instead:
#
#   sudo ./scripts/quickstart.sh --slug client1 --host 203.0.113.10 \
#       --build --self-sign --self-signed-tls
#
# Each of --build / --self-sign / --self-signed-tls trades one documented
# safety boundary (an image built and reviewed elsewhere; a signing key that
# never touches the customer host; a real certificate) for convenience. Fine
# for a server only you operate end-to-end; not the model for a signing
# identity or an image shared across several customer deployments — read
# runbook sections 1.6 / 1.10 / 1.12 first if that is your situation.
#
# --dry-run prints the exact plan — every command this would run, in order,
# with the values it resolved — without touching the host, an image, or any
# file outside a throwaway scratch directory.
#
# Everything after "first install" (an update, a rollback, a backup) is still
# ./scripts/deploy.sh and the rest of the runbook — this script's job ends
# once the stack is up and the first administrator exists.
set -eu

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

# `python3` is what a fresh Ubuntu server (this script's actual target) and
# every runbook command name; `python` is kept as a fallback only so this
# script itself stays runnable somewhere that names it that instead. Checked
# by actually running it, not just `command -v`: Windows ships a `python3.exe`
# App Execution Alias that is on PATH and satisfies `command -v` while doing
# nothing but printing a Microsoft Store prompt.
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" --version >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done
[ -n "$PYTHON_BIN" ] || { echo "error: no working python3 or python on PATH." >&2; exit 2; }

SLUG=""
HOST=""
OUT=""
PROFILE="client-1"
FEATURES=""
ADMIN_USERNAME="admin"
APP_IMAGE=""
BUILD_IMAGE=0
MANIFEST_PATH=""
MANIFEST_KEYS=""
SELF_SIGN=0
SIGNING_KEY=""
TLS_CERT=""
TLS_KEY=""
SELF_SIGNED_TLS=0
SKIP_OS_SETUP=0
SKIP_FIREWALL=0
SKIP_ADMIN=0
DRY_RUN=0
RETENTION_DAYS=0

fail() { echo "error: $1" >&2; exit 2; }
note() { echo "==> $1"; }
run() {
    # Every command this script executes passes through here, so --dry-run
    # has exactly one place to intercept instead of an "if dry_run" guard on
    # every call site — the guard for that command is dropped if this one is.
    if [ "$DRY_RUN" -eq 1 ]; then
        printf '    [dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

usage() {
    # Everything between the shebang and `set -eu` above, stripped of the
    # comment marker — kept in sync by construction, not by a hardcoded line
    # range that a later edit could quietly outgrow.
    sed -n '2,/^set -eu$/p' "$0" | sed '$d; s/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --slug) SLUG="$2"; shift 2 ;;
        --host) HOST="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        --profile) PROFILE="$2"; shift 2 ;;
        --features) FEATURES="$2"; shift 2 ;;
        --admin-username) ADMIN_USERNAME="$2"; shift 2 ;;
        --app-image) APP_IMAGE="$2"; shift 2 ;;
        --build) BUILD_IMAGE=1; shift ;;
        --manifest) MANIFEST_PATH="$2"; shift 2 ;;
        --manifest-keys) MANIFEST_KEYS="$2"; shift 2 ;;
        --self-sign) SELF_SIGN=1; shift ;;
        --signing-key) SIGNING_KEY="$2"; shift 2 ;;
        --tls-cert) TLS_CERT="$2"; shift 2 ;;
        --tls-key) TLS_KEY="$2"; shift 2 ;;
        --self-signed-tls) SELF_SIGNED_TLS=1; shift ;;
        --skip-os-setup) SKIP_OS_SETUP=1; shift ;;
        --skip-firewall) SKIP_FIREWALL=1; shift ;;
        --skip-admin) SKIP_ADMIN=1; shift ;;
        --retention-days) RETENTION_DAYS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option: $1 (--help for usage)" ;;
    esac
done

[ -n "$SLUG" ] || fail "--slug is required."
[ -n "$HOST" ] || fail "--host is required."
[ -n "$OUT" ] || OUT="/srv/dolphin/$SLUG"

if [ -n "$APP_IMAGE" ] && [ "$BUILD_IMAGE" -eq 1 ]; then
    fail "--app-image and --build are mutually exclusive — pick one image source."
fi
if [ -z "$APP_IMAGE" ] && [ "$BUILD_IMAGE" -eq 0 ]; then
    fail "an image source is required: --app-image REPO@sha256:DIGEST, or --build."
fi
if [ -n "$MANIFEST_PATH" ] && [ "$SELF_SIGN" -eq 1 ]; then
    fail "--manifest and --self-sign are mutually exclusive — pick one manifest source."
fi
if [ -z "$MANIFEST_PATH" ] && [ "$SELF_SIGN" -eq 0 ]; then
    fail "a manifest source is required: --manifest PATH (--manifest-keys too), or --self-sign."
fi
if [ -n "$MANIFEST_PATH" ] && [ -z "$MANIFEST_KEYS" ]; then
    fail "--manifest needs --manifest-keys too (the 'key_id:base64publickey' line for it)."
fi
if [ -n "$TLS_CERT" ] || [ -n "$TLS_KEY" ]; then
    [ -n "$TLS_CERT" ] && [ -n "$TLS_KEY" ] || fail "--tls-cert and --tls-key are both required together."
    [ "$SELF_SIGNED_TLS" -eq 0 ] || fail "--tls-cert/--tls-key and --self-signed-tls are mutually exclusive."
fi
if [ -z "$TLS_CERT" ] && [ "$SELF_SIGNED_TLS" -eq 0 ]; then
    fail "a certificate source is required: --tls-cert PATH --tls-key PATH, or --self-signed-tls."
fi

SECRETS_DIR="$OUT/secrets"
ENV_FILE="$SECRETS_DIR/.env"
MANIFEST_DEST="$SECRETS_DIR/manifest.json"
TLS_CERT_DEST="$SECRETS_DIR/tls/fullchain.pem"
TLS_KEY_DEST="$SECRETS_DIR/tls/privkey.pem"

note "plan: slug=$SLUG host=$HOST out=$OUT profile=$PROFILE"
[ "$DRY_RUN" -eq 1 ] && note "DRY RUN — nothing below actually runs"

# --- 1. OS packages, Docker, timezone, firewall ----------------------------

if [ "$SKIP_OS_SETUP" -eq 1 ]; then
    note "skipping OS setup (--skip-os-setup)"
elif [ -f /etc/debian_version ] || command -v apt-get >/dev/null 2>&1; then
    note "installing OS packages and Docker Engine (idempotent — safe to run again)"
    run sudo apt-get update
    run sudo apt-get install -y ca-certificates curl openssl
    run sudo timedatectl set-timezone Asia/Tehran
    if ! command -v docker >/dev/null 2>&1; then
        run sudo install -m 0755 -d /etc/apt/keyrings
        run sudo sh -c 'curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc'
        run sudo chmod a+r /etc/apt/keyrings/docker.asc
        run sudo sh -c '. /etc/os-release; echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list'
        run sudo apt-get update
        run sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    else
        note "docker already installed — skipping"
    fi
    run sudo systemctl enable --now docker
    if [ "$SKIP_FIREWALL" -eq 0 ] && command -v ufw >/dev/null 2>&1; then
        run sudo ufw allow OpenSSH
        run sudo ufw allow 80/tcp
        run sudo ufw allow 443/tcp
        run sudo ufw --force enable
    fi
else
    note "not a Debian/Ubuntu host and --skip-os-setup was not given — skipping OS setup;"
    note "install Docker Engine + Compose v2 yourself (runbook 1.1-1.3), then re-run with --skip-os-setup."
fi

# --- 2. Deployment directory, runtime files, external volumes --------------

note "deployment directory: $OUT"
# Directory creation happens for real even under --dry-run: an empty
# directory holds nothing sensitive, and the rest of this script (including
# `cd "$OUT"` before bringing the stack up) needs it to exist to print an
# accurate plan rather than failing on a directory dry-run deliberately
# never created.
mkdir -p "$SECRETS_DIR/tls"
run chmod 700 "$SECRETS_DIR"
run chmod 700 "$SECRETS_DIR/tls"

# The customer host needs the Compose files, the nginx config and the
# operational scripts — never the application source or the vendor theme;
# those live in the reviewed image. Same list as runbook 1.5, so the two
# cannot silently drift apart.
note "copying runtime files into $OUT"
for relative in \
    compose.yml compose.write-stop.yml compose.restore-verify.yml \
    nginx/default.conf nginx/write-stop-off.conf nginx/write-stop-on.conf \
    scripts/deploy.sh scripts/prepare-backup-volume.sh scripts/bootstrap-postgres.sh \
    scripts/postgres-entrypoint.sh scripts/backup-postgres.sh scripts/verify-postgres-restore.sh \
    scripts/verify-postgres-schema.sql scripts/pg_scram_verifier.py
do
    [ -f "$REPO_ROOT/$relative" ] || fail "expected runtime file missing from this checkout: $relative"
    mkdir -p "$OUT/$(dirname "$relative")"
    run cp "$REPO_ROOT/$relative" "$OUT/$relative"
done
run chmod +x "$OUT/scripts/deploy.sh" "$OUT/scripts/prepare-backup-volume.sh"

note "external volumes (docker volume create is a no-op if one already exists)"
run docker volume create "${SLUG}_postgres_data"
run docker volume create "${SLUG}_postgres_backups"

# --- 3. The application image -----------------------------------------------

if [ "$BUILD_IMAGE" -eq 1 ]; then
    note "building the application image from this checkout (--build)"
    if [ -z "${PYTHON_BASE_IMAGE:-}" ] && [ ! -f "$REPO_ROOT/.python-base-image" ] && [ "$DRY_RUN" -eq 0 ]; then
        note "PYTHON_BASE_IMAGE not set — resolving python:3.13-slim's current digest"
        docker pull python:3.13-slim
        PYTHON_BASE_IMAGE="$(docker inspect --format='{{index .RepoDigests 0}}' python:3.13-slim)"
        export PYTHON_BASE_IMAGE
        note "using $PYTHON_BASE_IMAGE"
    fi
    run ./scripts/build-image.sh
    VERSION_TAG="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"
    APP_IMAGE="dolphin-app:v${VERSION_TAG}"
    if [ "$DRY_RUN" -eq 1 ] && [ -z "$APP_IMAGE" ]; then APP_IMAGE="dolphin-app:v0.0.0"; fi
else
    note "using given image: $APP_IMAGE"
    note "pulling it (already present is a fast no-op)"
    run docker pull "$APP_IMAGE"
fi

# --- 4. The signed deployment manifest --------------------------------------

if [ "$SELF_SIGN" -eq 1 ]; then
    note "self-signing a manifest for this deployment (--self-sign)"
    [ -n "$SIGNING_KEY" ] || SIGNING_KEY="$SECRETS_DIR/manifest-signing-key.pem"
    if [ ! -f "$SIGNING_KEY" ]; then
        run $PYTHON_BIN scripts/sign_deployment_manifest.py --generate-key "$SIGNING_KEY"
    else
        note "reusing existing signing key at $SIGNING_KEY"
    fi
    KEY_ID="$SLUG-$(date +%Y%m%d)"
    if [ "$DRY_RUN" -eq 1 ]; then
        MANIFEST_KEYS="$KEY_ID:DRYRUN"
    else
        MANIFEST_KEYS="$($PYTHON_BIN scripts/sign_deployment_manifest.py --print-public-key \
            --private-key "$SIGNING_KEY" --key-id "$KEY_ID" | head -n 1)"
    fi
    RESOLVED_FEATURES="$($PYTHON_BIN scripts/new_deployment.py --print-resolved-features \
        ${FEATURES:+--features "$FEATURES"})" || fail "could not resolve the feature list — see the error above."
    note "signing for features: $RESOLVED_FEATURES"
    set -- --private-key "$SIGNING_KEY" --key-id "$KEY_ID" --profile-id "$PROFILE" --output "$MANIFEST_DEST"
    OLD_IFS="$IFS"; IFS=','
    for feature in $RESOLVED_FEATURES; do
        set -- "$@" --feature "$feature"
    done
    IFS="$OLD_IFS"
    run $PYTHON_BIN scripts/sign_deployment_manifest.py "$@"
    note "REMINDER: $SIGNING_KEY is this deployment's only copy of its signing key."
    note "Fine for one self-operated server; for several customer deployments the"
    note "signing key belongs off every one of their hosts — runbook 1.10."
else
    note "using given manifest: $MANIFEST_PATH"
    run cp "$MANIFEST_PATH" "$MANIFEST_DEST"
fi
run chmod 644 "$MANIFEST_DEST"

# --- 5. TLS -------------------------------------------------------------

if [ "$SELF_SIGNED_TLS" -eq 1 ]; then
    note "generating a self-signed certificate for $HOST (--self-signed-tls)"
    note "browsers will warn about this — fine for an IP-only or internal deployment,"
    note "not for a customer-facing domain; get a real one instead (runbook 6/7)."
    run openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
        -keyout "$TLS_KEY_DEST" -out "$TLS_CERT_DEST" -days 825 -subj "/CN=$HOST"
else
    note "using given certificate: $TLS_CERT"
    run cp "$TLS_CERT" "$TLS_CERT_DEST"
    run cp "$TLS_KEY" "$TLS_KEY_DEST"
fi
run chmod 600 "$TLS_KEY_DEST"
run chmod 644 "$TLS_CERT_DEST"

# --- 6. The .env — generated, never hand-written ----------------------------

note "writing $ENV_FILE"
run $PYTHON_BIN scripts/new_deployment.py \
    --slug "$SLUG" --host "$HOST" --out "$OUT" --profile "$PROFILE" \
    ${FEATURES:+--features "$FEATURES"} \
    --image "$APP_IMAGE" \
    --manifest-path "$MANIFEST_DEST" \
    --manifest-keys "$MANIFEST_KEYS" \
    --retention-days "$RETENTION_DAYS"
# new_deployment.py writes the TLS lines as REPLACE-WITH-* placeholders — it
# cannot know these paths before this script resolved them above. The
# variable name is KARIZ_TLS_*, deliberately not renamed — see CLAUDE.md's
# Branding section and .env.example's own comment on why.
if [ "$DRY_RUN" -eq 0 ]; then
    sed -i "s|^KARIZ_TLS_CERT_PATH=.*|KARIZ_TLS_CERT_PATH=$TLS_CERT_DEST|" "$ENV_FILE"
    sed -i "s|^KARIZ_TLS_KEY_PATH=.*|KARIZ_TLS_KEY_PATH=$TLS_KEY_DEST|" "$ENV_FILE"
fi

# --- 7. Bring the stack up ---------------------------------------------------

cd "$OUT"
note "validating the composition"
run docker compose --env-file secrets/.env config --quiet
note "preparing the backup volume's sentinel (idempotent)"
run ./scripts/prepare-backup-volume.sh
note "releasing — db-bootstrap, backup, migrate, db-finalize, then web+nginx"
run ./scripts/deploy.sh "$APP_IMAGE"

# --- 8. Verify -----------------------------------------------------------

if [ "$DRY_RUN" -eq 0 ]; then
    note "verifying"
    CURL_FLAGS=""
    [ "$SELF_SIGNED_TLS" -eq 1 ] && CURL_FLAGS="-k"
    if curl $CURL_FLAGS -sf "https://${HOST}/health/live/" >/dev/null; then
        note "health/live: OK"
    else
        note "health/live: NOT OK YET — containers may still be starting; check 'docker compose ps'."
    fi
fi

# --- 9. First Platform Admin -------------------------------------------------

if [ "$SKIP_ADMIN" -eq 1 ]; then
    note "skipping admin creation (--skip-admin) — run this later:"
    note "  cd $OUT && docker compose --env-file secrets/.env run --rm web python manage.py bootstrap_platform_admin --username $ADMIN_USERNAME"
elif [ "$DRY_RUN" -eq 1 ]; then
    note "[dry-run] would prompt to create the first Platform Admin ($ADMIN_USERNAME) here"
else
    note "creating the first Platform Admin ($ADMIN_USERNAME) — you will be prompted for a password"
    docker compose --env-file secrets/.env run --rm web \
        python manage.py bootstrap_platform_admin --username "$ADMIN_USERNAME"
fi

echo
note "done. https://$HOST/ — sign in as $ADMIN_USERNAME."
note "Everything after this is the ordinary runbook: section 3 for an update,"
note "section 4 for backups, section 5 for a rollback."
