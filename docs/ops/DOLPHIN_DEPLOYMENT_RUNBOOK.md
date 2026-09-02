# Dolphin — deployment and operations runbook

**This is the canonical document for installing, starting, updating, backing up,
restoring and recovering Dolphin.** Where any other document disagrees with
this one, this one is correct.

Written for a Linux administrator who does not know the codebase. Every command
below was checked against the repository it ships with: service names come from
`compose.yml`, script paths from `scripts/`, environment names from
`.env.example`, and management commands from the Django apps. Nothing here is
invented.

Target environment: **Ubuntu Server 24.04 LTS**, Docker Engine, Docker Compose
v2, PostgreSQL and nginx in containers, and a Django/Gunicorn application image
**built elsewhere and reviewed before it reaches the customer host**.

---

## Contents

| Section | When you need it |
|---|---|
| [Shipping a change](#shipping-a-change) | **Every ordinary release — start here** |
| [0. Cheat sheet](#0-cheat-sheet) | Daily operation |
| [1. First install on a fresh server](#1-first-install-on-a-fresh-server) | Once, on a clean machine |
| [2. Start after a reboot](#2-start-after-a-reboot) | Every restart |
| [3. Application update](#3-application-update) | What a release does, and the same steps by hand |
| [4. Backup and restore](#4-backup-and-restore) | Routine and disaster |
| [5. Rollback](#5-rollback) | A release went wrong |
| [6. Domain deployment](#6-domain-deployment) | Recommended production |
| [6a. Internal hostname with a private CA](#6a-internal-only-hostname-with-a-private-ca) | Internal-only, real hostname, no public CA |
| [7. Static-IP deployment](#7-static-ip-deployment) | Staging / internal only |
| [8. Troubleshooting](#8-troubleshooting) | Something is broken |
| [9. Security and secrets](#9-security-and-secrets) | Always |

Throughout, `$DEPLOY` is the deployment directory — this runbook uses
`/srv/dolphin/client-1`. Adjust once and stay consistent.

Every Compose command needs `--env-file secrets/.env`. Compose does **not** read
that path automatically, and without it the stack fails on missing variables.

---

## Shipping a change

The everyday loop, start to finish. Two commands on the server; everything else
happens on the machine you develop on. The longer sections below explain what
these do and what to reach for when something is wrong — this is the path when
nothing is.

`$DEPLOY` is the deployment directory, `/srv/dolphin/Dolphin` on the
current host. `v1.1.2` stands in for the version being shipped.

### 1. On the development machine

Bump the version **before you build**. The image tag is only a label; the
`VERSION` file inside the image is what the footer prints, so building first and
bumping afterwards produces an image whose tag and contents disagree. The
release refuses that outright, naming both numbers — but the fix is still a
rebuild, so do it in this order.

`VERSION` is the single source of truth — `config/settings.py`
reads it, the panel footer prints it, and the OpenAPI schema carries it.

```bash
echo 1.1.2 > VERSION
```

Record what changed in `CHANGELOG.md`: what was added, changed, removed and
fixed. Commit both with the work they describe, and push.

Build the image and tag it with the same version:

```bash
./scripts/build-image.sh --save
```

The tag is read from `VERSION`, so it cannot name a version the image does not
contain, and the script reads the version back out of what it built before it
finishes. It also supplies the two build arguments the Dockerfile requires:
plain `docker build .` fails with `base name (${PYTHON_BASE_IMAGE}) should not
be blank`, because the base is pinned by digest rather than by tag.

Record that digest once per build machine — it is git-ignored, since which
digest has been reviewed belongs to your machine and its date, not to the
source:

```bash
docker pull python:3.13-slim && docker inspect --format='{{index .RepoDigests 0}}' python:3.13-slim > .python-base-image
```

Use the `RepoDigests` value, not the image ID from `docker image ls`. An image
ID names the config on one machine and will not resolve anywhere else.

```bash
scp dolphin-app-v1.1.2.tar.gz deploy@<server>:/srv/dolphin/
```

### 2. On the server

Load the image:

```bash
docker load -i /srv/dolphin/dolphin-app-v1.1.2.tar.gz
```

Pull the checkout and release:

```bash
cd $DEPLOY && git pull --ff-only && ./scripts/deploy.sh v1.1.2
```

That is the whole release. The script backs up, provisions the database roles,
migrates, collects static files, recreates the stack, and prints the running
version read out of the container.

**The `git pull` is not optional.** `nginx/default.conf` is bind-mounted from
this checkout rather than baked into the image, so a release that changed it
does nothing at all until the checkout is updated — nothing errors, the previous
limits simply stay in force. The script refuses to run when the two have
drifted, which is the only reason that failure is visible.

### 3. Confirm

Log in and read the version in the panel footer. It must show the version just
shipped; if it shows the previous one, `KARIZ_APP_IMAGE` did not change.

```bash
cd $DEPLOY && ./scripts/deploy.sh --status
```

### If something is wrong

```bash
cd $DEPLOY && ./scripts/deploy.sh --rollback
```

Returns to the tag the script last replaced — which requires that image to still
be loaded, so **keep at least the previous tag on the host**. Migrations are not
reversed; every migration this project ships is additive, so the older
application ignores what it does not know about.

If the backup step blocks a release you need out, `--no-backup` proceeds without
one and says so. It is for a deployment whose backup path is not working yet,
never for one holding data you would miss.

### Two rules this deployment learned the hard way

**One Compose project, one database volume.** The project name is stable
(`dolphin`); the version lives in the image tag and nowhere else. Standing up
a second project beside the live one looks like a safe way to trial a release
and is not: both publish 80 and 443, and both name the same external volume, so
two PostgreSQL servers end up writing one data directory. `postmaster.pid` does
not protect against this across containers — the second server checks the
recorded PID inside its own namespace, does not find it, decides the lock is
stale and starts anyway. The result is shared-catalog corruption. To trial a
release without touching production, use a separate host or a separate volume
set.

**A release allocates no terminal.** Every service invocation in a release path
uses `-T`. `db-bootstrap` still prints three password prompts as it runs — psql
echoes them while reading the values piped in from `.env` — and that is expected
rather than a fault. The backup that follows is what proves the values landed,
because it authenticates as the role that step just configured.

---

## 0. Cheat sheet

Run all of these from `$DEPLOY`.

**VALIDATE** (catches a missing or malformed variable before anything starts)

```bash
docker compose --env-file secrets/.env config --quiet
```

That only proves Compose can resolve every `${VARIABLE}` — it does not read the
manifest, sign anything, or touch the database. The real preflight, once `web`
has an image to run and a manifest to read, is Django's own:

```bash
docker compose --env-file secrets/.env run --rm --no-deps web python manage.py check
```

Prefer this over any ad hoc `python -c 'from django.conf import settings; ...'`
one-liner — Django settings are lazy, so a bare import can succeed while the
same host later fails to actually start; only `manage.py check` (or a real
`runserver`/`gunicorn` boot) forces every setting to actually resolve,
including the deployment manifest's signature.

**PREPARE THE BACKUP VOLUME** (once, before the first backup or the first
release — see [4.1](#41-prepare-the-backup-volume-once))

```bash
./scripts/prepare-backup-volume.sh --env-file secrets/.env
```

**STATUS**

```bash
docker compose --env-file secrets/.env ps
```

**START**

```bash
docker compose --env-file secrets/.env up -d
```

**STOP** (ordered; not `down`, which detaches the external volumes)

```bash
docker compose --env-file secrets/.env stop nginx web db
```

**RESTART one service**

```bash
docker compose --env-file secrets/.env restart web
```

**LOGS**

```bash
docker compose --env-file secrets/.env logs --tail 200 web
```

**HEALTH** (liveness is answered by nginx; readiness reaches Django and the database)

```bash
curl -sf "https://${PUBLIC}/health/live/" && echo LIVE
```

```bash
curl -s -o /dev/null -w '%{http_code}\n' "https://${PUBLIC}/api/v1/health/ready/"
```

**MIGRATE + COLLECTSTATIC** (one service does both)

```bash
docker compose --env-file secrets/.env run --rm migrate
```

**CREATE INITIAL ADMIN** (interactive; prompts for the password twice)

```bash
docker compose --env-file secrets/.env run --rm web python manage.py bootstrap_platform_admin --username <name>
```

**BACKUP**

```bash
docker compose --env-file secrets/.env --profile backup run --rm backup
```

**RESTORE VERIFICATION** (into a disposable database — never over the live one)

```bash
docker compose --env-file secrets/.env -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify <archive-name>.dump
```

**UPDATE IMAGE**

```bash
./scripts/deploy.sh v1.1.1
```

Backs up, migrates, collects static files and recreates the stack, refusing to
start if the nginx config is stale, another project holds the ports, or another
project shares the database volume. See [section 3](#3-application-update).

**WHAT IS RUNNING**

```bash
./scripts/deploy.sh --status
```

**CHECK VERSION** (which image each container actually runs)

```bash
docker compose --env-file secrets/.env images
```

**CHECK STATIC ASSETS**

```bash
for path in \
  /static/css/style.bundle.rtl.css \
  /static/plugins/global/plugins.bundle.rtl.css \
  /static/js/scripts.bundle.js \
  /static/common/dolphin.css \
  /static/common/dolphin-app.js \
  /static/common/brand/favicon.ico \
  /static/common/brand/Logo.png \
  /static/fonts/IRANSansWeb.woff \
  /static/plugins/global/fonts/keenicons/keenicons-duotone.woff ; do
  printf '%s ' "$path"
  curl -s -o /dev/null -w '%{http_code}\n' "https://${PUBLIC}${path}"
done
```

All nine must print `200`. Anything else — go to
[8.1](#81-the-panel-loads-unstyled-or-theme-assets-404).

---

## 1. First install on a fresh server

### 1.0 The one-command path

`scripts/quickstart.sh` runs every subsection below (1.1–1.16, minus the
smoke check) in order, by calling the same tools each subsection tells you to
run by hand — nothing here is a new mechanism, and nothing it does bypasses
what any of those already check or refuse. Read 1.1–1.16 once regardless: this
is what to fall back to when a step fails, and what `--dry-run` prints a plan
against.

Reviewed image, a manifest signed elsewhere, a real certificate — the
documented model, unchanged:

```bash
sudo ./scripts/quickstart.sh --slug client1 --host crm.client1.ir \
    --app-image ghcr.io/you/dolphin-app@sha256:<digest> \
    --manifest /path/to/signed-manifest.json --manifest-keys 'k1:AAAA...' \
    --tls-cert /path/to/fullchain.pem --tls-key /path/to/privkey.pem
```

A single dedicated server you fully control end-to-end, with nothing
pre-built and no certificate issued yet:

```bash
sudo ./scripts/quickstart.sh --slug client1 --host 203.0.113.10 \
    --build --self-sign --self-signed-tls
```

`--build`, `--self-sign` and `--self-signed-tls` each trade one safety
boundary documented below (1.6: an image built and reviewed elsewhere; 1.10:
a signing key that never touches the customer host; 1.12: a real certificate)
for convenience. That trade is reasonable for one server only you operate;
it is not the model for a signing identity or an image shared across several
customer deployments — use `--app-image`/`--manifest`/`--tls-cert` there
instead, each produced the documented way, off this host.

`--dry-run` prints the exact plan — every command it would run, in the order
it would run them, with every value resolved — without touching the host, an
image, or any file outside a throwaway directory. `./scripts/quickstart.sh
--help` lists every option; `--skip-os-setup` skips 1.1–1.3 for a host
already prepared, and `--skip-admin` skips 1.15 to run it separately later.

### 1.1 Operating system

```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl openssl
```

Timezone and clock. The application stores UTC and presents Asia/Tehran; a wrong
clock produces wrong Jalali dates and breaks TLS validation.

```bash
sudo timedatectl set-timezone Asia/Tehran
timedatectl status
```

`System clock synchronized: yes` and `NTP service: active` are both required. If
not:

```bash
sudo systemctl enable --now systemd-timesyncd
timedatectl timesync-status
```

### 1.2 Docker Engine and Compose v2

From Docker's own repository — Ubuntu's `docker.io` package is older and ships no
Compose v2 plugin.

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Verify, and make sure Docker starts at boot:

```bash
docker --version
docker compose version          # must report v2.x
sudo systemctl enable --now docker
systemctl is-enabled docker     # must print: enabled
```

`systemctl is-enabled docker` printing anything but `enabled` is the single most
common reason a server comes back from a reboot with nothing running.

### 1.3 Firewall

Only 80 and 443 are public. PostgreSQL is on an internal Docker network and
publishes no port; do not open 5432.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

### 1.4 Directories and ownership

```bash
sudo mkdir -p /srv/dolphin/client-1
sudo chown "$USER":"$USER" /srv/dolphin/client-1
cd /srv/dolphin/client-1
mkdir -p secrets/tls
chmod 700 secrets
chmod 700 secrets/tls
```

`secrets/` holds the `.env` file, the TLS private key and the signed deployment
manifest. Nothing in it is ever committed.

### 1.5 Runtime files from the repository

The customer host needs the Compose files, the nginx configuration and the
operational scripts — **not** the application source, the vendor theme sources or
the demo material. Those live in the reviewed image.

Required on the host:

```
compose.yml
compose.write-stop.yml
compose.restore-verify.yml
nginx/default.conf
nginx/write-stop-off.conf
nginx/write-stop-on.conf
scripts/deploy.sh
scripts/prepare-backup-volume.sh
scripts/bootstrap-postgres.sh
scripts/postgres-entrypoint.sh
scripts/backup-postgres.sh
scripts/verify-postgres-restore.sh
scripts/verify-postgres-schema.sql
scripts/pg_scram_verifier.py
```

Cloning the repository at the reviewed tag is acceptable and is what the current
staging host does. Cloning is a convenience for these files only — the running
application always comes from the image.

### 1.6 Images

The application image is built and reviewed elsewhere. **Never build it on the
customer host**: the host has no build toolchain, may have no PyPI access, and a
locally built image is not the artefact anyone reviewed.

Online host — pull by digest:

```bash
docker pull <app-repository>@sha256:<digest>
docker pull <postgres-repository>@sha256:<digest>
docker pull <nginx-repository>@sha256:<digest>
```

Offline host — transfer and load. On the build machine:

```bash
docker save <app-repository>@sha256:<digest> <postgres-repository>@sha256:<digest> <nginx-repository>@sha256:<digest> \
  | gzip > dolphin-images.tar.gz
sha256sum dolphin-images.tar.gz
```

Copy the archive across, verify the checksum matches what the build machine
printed, then:

```bash
gunzip -c dolphin-images.tar.gz | docker load
docker images --digests | grep -E 'app-repository|postgres|nginx'
```

The digests on the host must equal the digests in `.env`. That equality is the
whole point of pinning by digest.

### 1.7 External volumes

Database and backup volumes are declared `external: true`, so Compose refuses to
invent them. Creating them by hand is deliberate: it makes accidental data loss
through `docker compose down -v` impossible.

```bash
docker volume create dolphin_postgres_data
docker volume create dolphin_postgres_backups
```

The backup volume needs a one-time sentinel before the backup job will write to
it — see [4.1](#41-prepare-the-backup-volume-once).

### 1.8 `.env`

**Generate it rather than writing it by hand:**

```bash
python3 scripts/new_deployment.py --slug <customer> --host <public-hostname> --out /srv/dolphin/<customer>
```

One answer set produces the whole file: the project name, the database, all four
role names, both volume names, and five generated secrets, all derived from the
single slug so they cannot disagree with each other. The tool creates nothing
and starts nothing; it writes one `.env` at mode `0600`, refuses to replace an
existing one, and prints the remaining steps in order. Only the two TLS paths
and the manifest key are left for you to fill in, because neither can be
generated here.

Choose the feature set with `--features customers,products,invoices`; omit it
for this release's default set. Dependencies are added for you and the additions
are named — asking for `payments` also enables `invoices`, `customers` and
`products`, because an invoice cannot exist without a customer and a product.

```bash
python3 scripts/new_deployment.py --list-features
```

The feature list and the dependency rules are imported from
`common/deployment/registry.py`, the same module the running application
enforces, so the two can never drift apart.

**Or fill the template in by hand.** Copy the template:

```bash
cp .env.example secrets/.env
chmod 600 secrets/.env
```

Generate strong secrets — never reuse a value from another environment:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'   # DJANGO_SECRET_KEY
openssl rand -base64 32                                          # each POSTGRES_*_PASSWORD
```

Values that decide behaviour rather than identity:

| Variable | Value | Why |
|---|---|---|
| `KARIZ_COMPOSE_PROJECT_NAME` | stable lowercase name | Renaming it orphans the running containers |
| `KARIZ_APP_IMAGE` / `KARIZ_POSTGRES_IMAGE` / `KARIZ_NGINX_IMAGE` | `repo@sha256:digest` | Pinning by digest, not tag |
| `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `KARIZ_PUBLIC_HOST` | domain, or the static IP | All three must agree — see [6](#6-domain-deployment) / [7](#7-static-ip-deployment) |
| `AUDIT_TRUSTED_PROXY_CIDRS` | the Compose frontend subnet | **Must not be empty.** See [1.9](#19-audit_trusted_proxy_cidrs) |
| `DJANGO_SECURE_HSTS_SECONDS` + `KARIZ_HSTS_HEADER` | `31536000` + `max-age=31536000`, **or** `0` + empty | Only these two combinations are accepted |
| `KARIZ_DEPLOYMENT_MANIFEST_PATH` | path to the signed manifest | See [1.10](#110-signed-deployment-manifest) |
| `KARIZ_DEPLOYMENT_MANIFEST_KEYS` | `key_id:base64_public_key` | Public key only. The private key never reaches this host |
| `KARIZ_TLS_CERT_PATH` / `KARIZ_TLS_KEY_PATH` | `secrets/tls/fullchain.pem` / `privkey.pem` | |
| `POSTGRES_*_USER` / `POSTGRES_DB` | any safe lowercase identifier | Fresh installs get `dolphin*` names from the template; an existing deployment keeps whatever it already has |
| `KARIZ_BILLING_INVOICE_AFFECTS_STOCK` | **leave unset** | See [1.11](#111-client-1-business-switches) |

> **Why the `DOLPHIN_` prefix is still there.** It is a compatibility contract, not
> branding: `compose.yml`, the nginx envsubst filter, `config/production_env.py`
> and every existing `.env` read these exact names. Renaming them would break a
> running deployment on upgrade for no functional gain. Everything a customer
> sees says Dolphin / دلفین.

### 1.9 `AUDIT_TRUSTED_PROXY_CIDRS`

The application believes the `X-Real-IP` header only from networks listed here.
nginx sets that header but reaches the application over Compose's own bridge, so
with this empty **every audit row records nginx's container address** — the same
address for every user, and an audit trail that identifies nobody.

The template ships `172.16.0.0/12`, which covers Docker's usual range. Narrow it
to the real subnet once the stack is up:

```bash
docker network inspect "${KARIZ_COMPOSE_PROJECT_NAME}_frontend" \
  --format '{{(index .IPAM.Config 0).Subnet}}'
```

`0.0.0.0/0` is refused by production validation — trusting every source would let
any client set its own audit address.

### 1.10 Signed deployment manifest

Feature availability comes from an Ed25519-signed manifest, not from `.env`.
Production refuses to start without one that verifies.

**Sign it on the platform owner's machine, never on the customer host.** The
private key must not travel.

No signing key yet, or not sure the one you have still matches what a
deployment trusts? Generate one and get its public key back safely — this
refuses to overwrite an existing key, and refuses to print anything but a
correctly-shaped public key, rather than the empty or truncated value a failed
manual `openssl` pipeline can silently produce:

```bash
python scripts/sign_deployment_manifest.py --generate-key <owner-private-key-path>
python scripts/sign_deployment_manifest.py --print-public-key \
  --private-key <owner-private-key-path> --key-id <key-id>
```

The second command prints exactly the `key_id:base64publickey` line that goes
into `KARIZ_DEPLOYMENT_MANIFEST_KEYS` — copy it as-is.

```bash
python scripts/sign_deployment_manifest.py \
  --private-key <owner-private-key-path> \
  --key-id <key-id> \
  --profile-id client-1 \
  --feature customers --feature leads --feature sales --feature sales_documents \
  --feature after_sales --feature inbound_sms --feature inventory --feature products \
  --feature orders --feature invoices --feature payments --feature customer_ledger \
  --feature reports --feature audit_log \
  --output manifest.json
```

This writes `manifest.json` at mode `0644` already — see why below before
changing it.

Copy `manifest.json` to `secrets/` on the host and point
`KARIZ_DEPLOYMENT_MANIFEST_PATH` at it. **Unlike everything else in `secrets/`,
this file must stay world-readable: `chmod 644 secrets/manifest.json`.** The
application runs as a non-root user inside the container and reads it as a
bind mount; a manifest copied in at `0600` reads back as
`PermissionError: [Errno 13] Permission denied` the first time anything
actually loads settings, not at copy time. It is safe to leave readable: a
signed manifest is a public, verifiable feature list, not a secret — hiding it
protects nothing, since anyone with host access can already read `secrets/.env`
sitting right next to it.

Two deliberate omissions from that list:

* **`quotations` is absent.** Client-1 raises an invoice first and never issues a
  pre-invoice. The module is also off in the application's own defaults, so it
  stays hidden even if a manifest is missing — but a manifest that *names* it
  would switch it back on. Leave it out.
* **`internal_it_role` is absent.** Client-1 policy is that only a Platform Admin
  administers users. Include it only against a written decision.

### 1.11 Client-1 business switches

**`KARIZ_BILLING_INVOICE_AFFECTS_STOCK` must stay unset (it defaults to false).**

The order owns the inventory lifecycle: stock leaves the warehouse when an order
is approved and returns when it is cancelled, exactly once each. If invoices also
deducted, the same goods would leave twice for one sale. Setting this to `true`
is correct only for a deployment that invoices straight out of stock with no
order step — which is not this one.

### 1.12 TLS certificate

Domain: see [6](#6-domain-deployment). Static IP: see [7](#7-static-ip-deployment).
Either way the files must end up at `secrets/tls/fullchain.pem` and
`secrets/tls/privkey.pem`, with:

```bash
chmod 600 secrets/tls/privkey.pem
chmod 644 secrets/tls/fullchain.pem
```

### 1.13 Bring the stack up, in this order

Validate the composition first — this catches a missing variable before anything
starts:

```bash
docker compose --env-file secrets/.env config --quiet
```

**Step 1 — database.**

```bash
docker compose --env-file secrets/.env up -d db
docker compose --env-file secrets/.env ps db
```

Wait for `healthy`.

**Step 2 — create the managed roles.** Interactive: it prompts for the migration,
application and backup passwords. Enter the same values you put in `.env`.

```bash
docker compose --env-file secrets/.env run --rm db-bootstrap
```

Ends with `PostgreSQL managed roles are ready.`

**Step 3 — migrations and static files.** One service does both.

```bash
docker compose --env-file secrets/.env run --rm migrate
```

**Step 4 — lock down grants.** Re-runs the bootstrap script, now that the tables
exist, to apply the per-table privilege contract.

```bash
docker compose --env-file secrets/.env run --rm db-finalize
```

**Step 5 — application and edge.**

```bash
docker compose --env-file secrets/.env up -d web nginx
docker compose --env-file secrets/.env ps
```

### 1.14 Verify before anyone logs in

```bash
export PUBLIC='crm.example.com'     # or the static IP
```

On a self-signed certificate add `-k` to every `curl` below.

Health:

```bash
curl -sf "https://${PUBLIC}/health/live/" && echo LIVE
curl -s -o /dev/null -w 'ready=%{http_code}\n' "https://${PUBLIC}/api/v1/health/ready/"
```

Static assets — run the CHECK STATIC ASSETS block from [section 0](#0-cheat-sheet).
All nine must be `200`.

Exposure — the admin plane must not be reachable, and plain HTTP must redirect:

```bash
curl -s -o /dev/null -w 'admin=%{http_code}\n' "https://${PUBLIC}/admin/"      # expect 404
curl -s -o /dev/null -w 'http=%{http_code}\n' "http://${PUBLIC}/"              # expect 308
ss -lntp | grep -E ':(80|443|5432)\b'                                          # 5432 must be absent
```

### 1.15 First Platform Admin

There is no self-service registration and no password-reset flow. The first
account is created from the server terminal:

```bash
docker compose --env-file secrets/.env run --rm web \
  python manage.py bootstrap_platform_admin --username <name>
```

It prompts for the password twice and enforces Django's password validators. It
has no password argument, so the value never reaches shell history, process
arguments or a log.

It refuses to run once **any** Platform Admin row exists — active *or inactive*.
The check is `User.objects.filter(role=PLATFORM_ADMIN).exists()`, with no
`is_active` condition, so deactivating the only administrator does not reopen
this path. That is the lockout case, and it is recovered with `changepassword`
below or by reactivating the row directly, never by bootstrapping a second one.

A username is never reused either, including one belonging to a deactivated
account. The account is created with CRM role `platform_admin` and stays outside
Django admin (`is_staff=false`, `is_superuser=false`). Creation and its audit row
commit in one transaction; the audit actor is null, because no CRM user exists
yet to have performed it, and it records field names and a password-set flag
rather than the password.

This is not a role-escalation or lockout-recovery tool. Ordinary user and role
work goes through the authorised CRM paths.

> **Password recovery is a host operation.** No interface anywhere changes a
> password, and the API refuses it. A user who forgets theirs is recovered with
> `docker compose --env-file secrets/.env run --rm web python manage.py changepassword <username>`.

### 1.16 Smoke check

1. Open `https://${PUBLIC}/` and sign in as the Platform Admin.
2. The dashboard renders with the dark sidebar, Persian RTL, and the Dolphin
   logo. If it is unstyled, go to [8.1](#81-the-panel-loads-unstyled-or-theme-assets-404).
3. The sidebar shows the current page highlighted, and **no پیش‌فاکتور entry**.
4. Create a customer, then a campaign (سرنخ), then add someone to its جامعه هدف.
5. Create a product, a warehouse, and an opening stock movement.
6. Create an order against that warehouse, approve it, and confirm the stock fell
   by exactly the ordered quantity.
7. Create an invoice, issue it, and confirm the stock did **not** move again.
8. Open the browser console: zero errors, zero 404s.

---

## 2. Start after a reboot

### What happens by itself

`db`, `web` and `nginx` carry `restart: unless-stopped`, so Docker restarts them
after a reboot **provided the Docker service itself is enabled at boot**. The
one-shot services (`db-bootstrap`, `migrate`, `db-finalize`) carry `restart: "no"`
and correctly stay stopped — they have already done their work.

`web` may briefly restart if it wins the race against PostgreSQL. That is normal
and self-correcting; the restart policy handles it.

### Server reboot checklist

```bash
# 1. Docker came back
systemctl is-active docker && systemctl is-enabled docker

# 2. Every long-running service is up
cd /srv/dolphin/client-1
docker compose --env-file secrets/.env ps

# 3. Reconcile anything that did not come back
docker compose --env-file secrets/.env up -d

# 4. Health
curl -sf "https://${PUBLIC}/health/live/" && echo LIVE
curl -s -o /dev/null -w 'ready=%{http_code}\n' "https://${PUBLIC}/api/v1/health/ready/"

# 5. Nothing is crash-looping
docker compose --env-file secrets/.env logs --since 10m web nginx db | grep -iE 'error|traceback|refused' | head
```

Expected in step 2: `db`, `web`, `nginx` all `running`, `db` and `nginx` also
`healthy`. Anything `restarting` means a crash loop — read its logs before doing
anything else.

Step 3 is safe to run at any time: it starts what is missing and leaves what is
already running alone.

---

## 3. Application update

### The short way

```bash
./scripts/deploy.sh v1.1.1
```

Run from the deployment directory — the one holding `compose.yml` and `.env`.
It performs the whole sequence below (back up, migrate, collect static files,
recreate) and **refuses to start** rather than half-applying when a precondition
fails. It blocks on the three that are silent when skipped:

* **`nginx/default.conf` has drifted from `origin/main`.** That file is
  bind-mounted from this checkout, not baked into the image, so a stale copy
  keeps the old limits in force with nothing in any log to say so. This is the
  one that bites: after the 1.1.1 release a stale copy still capped request
  bodies at 256 KB, so the spreadsheet imports worked with a small test file and
  failed on a real one.
* **Another Compose project already holds port 80.** Caught before anything
  starts, instead of leaving the database and application up with nginx refused.
* **Another running project mounts the same database volume.** Two PostgreSQL
  servers over one data directory is never intended; PostgreSQL's own lock turns
  it into a restart loop rather than corruption, but it is still wrong.

Afterwards it prints the version read out of the running container
(`/app/VERSION`), so "did the new image actually deploy" is answered by the tool
rather than from memory.

```bash
./scripts/deploy.sh --status
```

What is running now: project, image tag, database volume, and every Dolphin
container on the host with its ports. Use it when returning to a deployment you
have not touched for a while.

```bash
./scripts/deploy.sh --rollback
```

Back to the tag the script last replaced. It records that tag when it switches.
It does **not** reverse migrations — see
[why a database rollback is unsafe](#why-a-database-rollback-is-unsafe).

```bash
./scripts/deploy.sh v1.1.1 --no-backup
```

Proceed without a backup. For a deployment whose backup path is not working yet
— an unprepared volume, or database roles whose passwords do not match `.env` —
and never for one holding data you would miss. The release announces the skip
rather than performing it quietly.

A backup that fails with `password authentication failed for user
"<backup role>"` means the role's password in the database and
`POSTGRES_BACKUP_PASSWORD` in `.env` have diverged. `db-bootstrap` resets all
three managed role passwords from `.env`, and the script now runs it before the
backup for that reason:

```bash
docker compose run --rm -T db-bootstrap
```

This prints `Enter new password for user ...` three times. **That is expected.**
`bootstrap-postgres.sh` sets those roles through psql's `\password`, piping each
value in on stdin; psql echoes the prompt but reads what was piped. The
non-interactive alternative beside it is restricted to disposable proof
databases on a loopback high port, so a real deployment cannot use it.

The prompts appear with or without `-T`. If you want to know whether the values
actually landed, look at the backup that follows: it authenticates as the backup
role this step just configured, so a successful backup is the proof.

### One stack, not one per version

`KARIZ_COMPOSE_PROJECT_NAME` names a **stable** project, and
`POSTGRES_DATA_VOLUME` a single fixed volume. The version belongs to the image
tag, never to the project name.

Standing up `dolphin-v110` and `dolphin-v111` as parallel Compose projects
looks like a safe way to trial a release, and is not: both publish 80 and 443,
so the second cannot bind, and both name the same external database volume, so
two PostgreSQL servers fight over one data directory. Upgrading in place has
neither problem — Docker replaces the container, and there is only ever one
stack. To trial a release without touching production, use a separate host or a
separate volume set, not a second project beside the live one.

### The same sequence by hand

Use this when the script cannot run, or to understand what it does.

### Required every release

1. **Back up first, and prove the backup exists** — [4.2](#42-take-a-backup).
2. **Optionally stop writes at the edge** for a short window. Reads and health
   stay live:
   ```bash
   docker compose --env-file secrets/.env -f compose.yml -f compose.write-stop.yml config --quiet
   docker compose --env-file secrets/.env -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
   ```
3. **Load the new reviewed image** — [1.6](#16-images). Never build on this host.
4. **Record the digest you are leaving.** Rollback needs it:
   ```bash
   grep KARIZ_APP_IMAGE secrets/.env
   ```
5. **Point `.env` at the new digest**, then verify Compose agrees:
   ```bash
   docker compose --env-file secrets/.env config --quiet
   ```
6. **Update the runtime files** if the release changed `compose.yml`, the nginx
   configuration or the scripts:
   ```bash
   git -C /srv/dolphin/client-1 pull --ff-only
   ```
7. **Migrations and static files:**
   ```bash
   docker compose --env-file secrets/.env run --rm migrate
   ```
8. **Recreate the application and edge:**
   ```bash
   docker compose --env-file secrets/.env up -d web nginx
   ```
9. **Lift the write-stop** if you applied it:
   ```bash
   docker compose --env-file secrets/.env up -d --no-deps --force-recreate nginx
   ```
10. **Verify:** health, the nine static assets, a real login, and the browser
    console. Same checks as [1.14](#114-verify-before-anyone-logs-in).

### Only when the release says so

* **`db-bootstrap` / `db-finalize`** — only when the release changes database
  roles or the per-table grant contract. Running them otherwise is harmless but
  prompts for passwords unnecessarily.
* **New external volumes** — only when the release adds one.

### Rollback triggers

Stop and roll back ([section 5](#5-rollback)) if any of these is true after step 10:

* readiness does not return `200` within a few minutes;
* any of the nine static assets is not `200`;
* the login page renders unstyled;
* the browser console shows errors on the dashboard;
* `docker compose ps` shows `web` or `nginx` restarting.

---

## 4. Backup and restore

### 4.1 Prepare the backup volume (once)

The backup job refuses to write to a volume without its sentinel — that is what
stops it writing into the wrong place.

```bash
./scripts/prepare-backup-volume.sh --env-file secrets/.env
```

It is safe to run again later — on an already-prepared volume it just reports
that and exits, rather than failing the same way whether the volume is already
done or genuinely holds something unsafe, which is what the raw command it
wraps used to do (its own emptiness check treats the sentinel it just wrote as
"not empty" on a second run).

Doing this by hand is unusual enough to be worth understanding, not just
running: the `backup` service runs with `cap_drop: ALL`, and the script adds
only `CHOWN`. `chmod` on a path you do not own needs `CAP_FOWNER`, which is not
there — so every `chmod` has to happen while root still owns the path, before
the matching `chown`. `/backups` itself is handed over last, because once it
belongs to `postgres` at mode `0700` a root without `DAC_OVERRIDE` can no
longer write the sentinel into it.

### 4.2 Take a backup

```bash
docker compose --env-file secrets/.env --profile backup run --rm backup
```

It prints the archive name and nothing else. The job reads with
`POSTGRES_BACKUP_USER` only, writes a custom-format dump, verifies it with
`pg_restore --list`, writes a SHA-256 sidecar, and renames both files into place.
**A non-zero exit is a failed backup** — treat it as an incident.

The `backup` profile means a plain `docker compose up -d` never starts it.

### 4.3 Where the files are

Archives are named `dolphin-pg-<UTC timestamp>-<32 hex>.dump`, each beside its
`.sha256`, on the `backup_data` volume.

```bash
docker compose --env-file secrets/.env --profile backup run --rm --no-deps \
  --entrypoint sh backup -c 'ls -l /backups'
```

### 4.4 Schedule it

As the deployment user, `crontab -e`:

```
15 2 * * * cd /srv/dolphin/client-1 && docker compose --env-file secrets/.env --profile backup run --rm backup >> /var/log/dolphin-backup.log 2>&1
```

Retention is `POSTGRES_BACKUP_RETENTION_DAYS` in `.env`. `0` keeps everything —
correct until someone has decided the real policy in writing.

Also schedule expired-session cleanup. Django stops honouring expired sessions
but never deletes the rows, so `django_session` grows forever:

```
30 3 * * 0 cd /srv/dolphin/client-1 && docker compose --env-file secrets/.env --profile maintenance run --rm session-cleanup >> /var/log/dolphin-session-cleanup.log 2>&1
```

### 4.5 Verify a restore — into a disposable database

This is the only supported restore rehearsal. It restores into a throwaway
database and never touches the live one.

```bash
docker compose --env-file secrets/.env -f compose.restore-verify.yml --profile restore-verify config --quiet
docker compose --env-file secrets/.env -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify dolphin-pg-<timestamp>-<token>.dump
```

The script checks the sentinel, the exact archive name shape and the SHA-256
before restoring, then runs the schema verification in
`scripts/verify-postgres-schema.sql`.

### 4.6 Disaster restore

> **Never drop or overwrite the live database until a restore of the chosen
> archive has succeeded in the disposable path above.** Without that evidence you
> may be trading a damaged database for no database.

1. Stop the application so nothing writes: `docker compose --env-file secrets/.env stop nginx web`.
2. Verify the chosen archive with [4.5](#45-verify-a-restore--into-a-disposable-database).
3. Take a backup of the damaged database anyway — it is evidence, and it may hold
   rows the archive does not.
4. Restore into the live database, then run `db-finalize` to re-apply grants.
5. Bring the stack back up and run the [1.14](#114-verify-before-anyone-logs-in) checks.

Steps 4 and 5 change live data. Do them with the customer's explicit go-ahead.

---

## 5. Rollback

### Application image

The fastest and safest rollback, and the one to reach for first:

```bash
# Put the previous digest back in secrets/.env, then:
docker compose --env-file secrets/.env config --quiet
docker compose --env-file secrets/.env up -d web nginx
```

Then re-run the [1.14](#114-verify-before-anyone-logs-in) checks.

### Configuration

`compose.yml`, `nginx/` and `scripts/` are versioned. Roll back to the previous
reviewed tag and recreate only what changed:

```bash
git -C /srv/dolphin/client-1 checkout <previous-tag>
docker compose --env-file secrets/.env up -d --force-recreate nginx
```

`secrets/.env` is **not** versioned. Keep a dated copy before every edit.

### Static asset regression

Symptom: the panel loads unstyled after an update. Almost always a stale
`static_data` volume or a browser cache. Re-run `migrate` (which re-runs
`collectstatic`), recreate `nginx`, then hard-refresh:

```bash
docker compose --env-file secrets/.env run --rm migrate
docker compose --env-file secrets/.env up -d --force-recreate nginx
```

### Failed migration

If `migrate` fails, **the application is still on the old image and still
running**. Do not force anything.

1. Capture the full output — it names the migration that failed.
2. Do not re-run it blindly; a partially applied migration needs to be understood
   first.
3. Roll the image back to the previous digest so the running code matches the
   schema on disk.
4. Escalate with the captured output.

### Why a database rollback is unsafe

Restoring the database moves it back to the backup's moment and **discards every
row written since** — orders, invoices, payments, ledger entries. The ledger is
append-only precisely so history is never rewritten, and a restore is the one
operation that breaks that. Roll the image and the configuration back first;
restore the database only when the data itself is damaged and the loss has been
accepted in writing.

---

## 6. Domain deployment

**This is the recommended production shape.**

1. **DNS** — an `A` record for the public hostname pointing at the server's public
   IP. Confirm before issuing a certificate:
   ```bash
   dig +short crm.company.com
   ```
2. **`.env`** — all three must be the same hostname:
   ```
   DJANGO_ALLOWED_HOSTS=crm.company.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://crm.company.com
   KARIZ_PUBLIC_HOST=crm.company.com
   ```
   Exactly one host, no wildcard, no leading dot, no port, no trailing slash —
   production validation refuses all of those.
3. **Certificate** — a publicly trusted certificate for that hostname. Place the
   full chain at `secrets/tls/fullchain.pem` and the key at
   `secrets/tls/privkey.pem`, with the permissions from [1.12](#112-tls-certificate).
4. **HTTPS redirect** — automatic. Port 80 only issues a `308` to the configured
   host; there is no plain-HTTP mode.
5. **HSTS** — keep the default:
   ```
   DJANGO_SECURE_HSTS_SECONDS=31536000
   KARIZ_HSTS_HEADER=max-age=31536000
   ```
   These two must agree. Only one year (or more) and exactly `0` are accepted —
   a short pin looks like protection without being any.
6. **Renewal** — replace the two files and recreate the edge:
   ```bash
   docker compose --env-file secrets/.env up -d --no-deps --force-recreate nginx
   openssl x509 -in secrets/tls/fullchain.pem -noout -dates
   ```
   Diarise renewal well before expiry. Nothing in the stack renews automatically.

### 6a. Internal-only hostname with a private CA

A company's own `something.internal` name, reachable only inside its network,
with a certificate that a public CA will never issue for a name it cannot
verify anyone owns — because it does not resolve on the public Internet at
all. This is still the domain shape, not the static-IP one below: the
difference is *who signs the certificate*, not how HTTPS or HSTS behave.

1. **DNS** — an internal `A` record, on whatever resolves inside that network
   (central DNS is the goal; see the note at the end of this section).
   ```bash
   dig +short pannel.company.internal
   ```
2. **`.env`** — same as [step 2](#6-domain-deployment) above, with the
   internal name in all three.
3. **A private root CA, once, off this host if at all possible:**
   ```bash
   openssl genrsa -out Company-Root-CA.key 4096
   openssl req -x509 -new -sha256 -key Company-Root-CA.key -days 3650 \
     -out Company-Root-CA.crt -subj '/C=XX/O=Company/CN=Company Internal Root CA'
   ```
   The CA's private key (`Company-Root-CA.key`) is the whole trust chain for
   every certificate it will ever sign. It must not sit on the application
   host permanently — generate it, sign what you need, and move it to secure
   or offline custody. It is never distributed to anyone.
4. **A leaf certificate for the hostname, signed by that CA:**
   ```bash
   openssl req -new -nodes -newkey rsa:2048 \
     -keyout secrets/tls/privkey.pem -out server.csr \
     -subj '/CN=pannel.company.internal' \
     -addext 'subjectAltName=DNS:pannel.company.internal'
   openssl x509 -req -in server.csr -CA Company-Root-CA.crt -CAkey Company-Root-CA.key \
     -CAcreateserial -days 3650 -out secrets/tls/fullchain.pem \
     -extfile <(printf 'subjectAltName=DNS:pannel.company.internal')
   chmod 600 secrets/tls/privkey.pem
   chmod 644 secrets/tls/fullchain.pem
   ```
   `subjectAltName=DNS:` is not optional here either — the same browser rule
   from [section 7](#7-static-ip-deployment) applies.
5. **HSTS** — the domain policy, not the static-IP one: this is a real
   hostname, so keep `DJANGO_SECURE_HSTS_SECONDS=31536000` and
   `KARIZ_HSTS_HEADER=max-age=31536000`. HSTS only pins "always HTTPS for this
   host"; it does not pin which CA signed the certificate, so rotating the
   leaf certificate later — even re-issuing under a new CA — needs no HSTS
   change.
6. **Trust distribution.** Every machine that will use the panel needs
   `Company-Root-CA.crt` (never the `.key`) installed as a trusted root —
   otherwise every browser shows the same warning a self-signed certificate
   would. Two ways, in order of preference:
   * **Central: Group Policy / MDM.** Push the root CA to every managed
     machine at once; nothing per-user to run or maintain.
   * **Per-machine, until central distribution exists.** A reviewed onboarding
     script is shipped at
     `scripts/windows-employee-onboarding.ps1` — it verifies the CA
     certificate's SHA-256 against a value you set at the top of the script,
     installs it into `LocalMachine\Root`, optionally adds a hosts-file
     mapping, flushes DNS, confirms resolution, and opens the panel. It never
     bypasses a certificate warning; a warning it cannot clear is treated as
     "stop and check", not "click through". Give employees only the `.crt`/
     `.cer` file and this script — never the CA's private key.
7. **What public ACME (Let's Encrypt and similar) does not do here.** A public
   CA cannot and will not issue for a name that only resolves internally, so
   there is nothing to "switch to" later for this hostname short of moving to
   a real public domain (see [section 6](#6-domain-deployment) above, which
   this deployment can move to without changing anything else in the stack).
8. **Renewal and CA lifecycle.** Renewing the leaf certificate is step 6 in
   [section 6](#6-domain-deployment) above, unchanged. The root CA itself is
   good for as long as its `-days` said (10 years above) — diarise that
   separately, since letting it expire invalidates every certificate it ever
   signed at once, on every trusting machine, the same day.

State this in writing to the customer, the same way section 7 does for a
static IP: every employee machine needs the CA installed before the panel
works without a warning, and central DNS plus GPO/MDM distribution is the
target state — hosts-file edits and one-off imports are a bridge, not the
plan.

---

## 7. Static-IP deployment

**Staging and internal use only. This is not the recommended production shape,
and it is not evidence of production TLS readiness.**

TLS still applies: there is no plain-HTTP mode and cookies are secure-only.

1. **`.env`** — the static IP in all three:
   ```
   DJANGO_ALLOWED_HOSTS=203.0.113.10
   DJANGO_CSRF_TRUSTED_ORIGINS=https://203.0.113.10
   KARIZ_PUBLIC_HOST=203.0.113.10
   ```
2. **HSTS must be off.** A one-year pin on an address presenting a self-signed
   certificate stops anyone clicking through the warning for a year, on their own
   machine, with no server-side undo:
   ```
   DJANGO_SECURE_HSTS_SECONDS=0
   KARIZ_HSTS_HEADER=
   ```
   Both, together. The validator refuses one without the other.
3. **Certificate — generate it on the server** so the private key never travels:
   ```bash
   cd /srv/dolphin/client-1
   openssl req -x509 -nodes -newkey rsa:4096 -days 397 \
     -keyout secrets/tls/privkey.pem \
     -out    secrets/tls/fullchain.pem \
     -subj   "/CN=203.0.113.10" \
     -addext "subjectAltName=IP:203.0.113.10" \
     -addext "basicConstraints=critical,CA:FALSE" \
     -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
     -addext "extendedKeyUsage=serverAuth"
   chmod 600 secrets/tls/privkey.pem
   chmod 644 secrets/tls/fullchain.pem
   openssl x509 -in secrets/tls/fullchain.pem -noout -fingerprint -sha256 -dates
   ```
   **`subjectAltName=IP:` is not optional** — every current browser ignores `CN`
   and refuses a certificate that does not name the IP in a SAN.

### State these limitations to the customer in writing

1. Every browser shows a certificate warning until the certificate is installed
   as trusted on each machine.
2. No public CA issues certificates for bare IP addresses.
3. HSTS must stay off, so the stack is one downgrade weaker than the domain shape.
4. The certificate provides **encryption only, not identity** — nothing proves the
   IP belongs to this organisation.
5. The address is pinned to the IP; changing it invalidates the certificate and
   every bookmark.
6. Renewal is manual, on the 397-day expiry.

Moving to a domain later means: add DNS, obtain a real certificate, change the
three `.env` values, turn HSTS back on, recreate `nginx`. No data migration.

---

## 8. Troubleshooting

Every entry below has actually happened on a Linux deployment of this stack.

### 8.1 The panel loads unstyled, or theme assets 404

**Symptoms** — no dark sidebar, unstyled text, `404` for
`style.bundle.rtl.css`, `plugins.bundle.rtl.css` or `scripts.bundle.js`.

**Likely cause** — the `static_data` volume was never populated (`migrate` not
run, or it failed after the migration step), or the browser is holding a cache
from before the static filenames changed.

**Diagnose**

```bash
docker compose --env-file secrets/.env run --rm --no-deps --entrypoint sh web -c 'ls /app/staticfiles | head'
curl -s -o /dev/null -w '%{http_code}\n' "https://${PUBLIC}/static/css/style.bundle.rtl.css"
```

`/app/staticfiles` must contain `css/`, `js/`, `fonts/`, `plugins/` and `common/`.

**Remediate**

```bash
docker compose --env-file secrets/.env run --rm migrate
docker compose --env-file secrets/.env up -d --force-recreate nginx
```

Then hard-refresh the browser (`Ctrl+F5`). The application's own CSS and JS were
renamed to `dolphin.css` / `dolphin-app.js`; a cache holding the old names
renders the page unstyled even when the server is correct.

### 8.2 `collectstatic` fails or collects almost nothing

**Symptoms** — `migrate` completes the migration step then fails, or
`/app/staticfiles` holds only `admin/` and `rest_framework/`.

**Likely cause** — the image was built without the theme assets.

**Diagnose**

```bash
docker compose --env-file secrets/.env run --rm --no-deps --entrypoint sh web -c 'ls /app/assets/css /app/assets/js 2>&1 | head'
```

**Remediate** — the image is wrong. Rebuild it on the build machine and reload it;
nothing on the customer host can fix a missing file inside the image.

### 8.3 nginx cannot reach the application

**Symptoms** — `502` or `503`, nginx logs say `connect() failed` or
`host not found in upstream`.

**Diagnose**

```bash
docker compose --env-file secrets/.env ps
docker compose --env-file secrets/.env logs --tail 100 web
docker compose --env-file secrets/.env exec nginx wget -qO- http://web:8000/api/v1/health/live/
```

**Likely causes** — `web` is crash-looping (read its logs; usually a `.env`
validation failure), or `web` is still starting after a reboot.

**Remediate** — fix what the `web` log names, then
`docker compose --env-file secrets/.env up -d web nginx`.

### 8.4 Port 80 or 443 already in use

**Symptoms** — nginx fails to start, `bind: address already in use`.

**Diagnose**

```bash
sudo ss -lntp | grep -E ':(80|443)\b'
```

**Remediate** — usually a host nginx or Apache installed by default:

```bash
sudo systemctl disable --now nginx apache2 2>/dev/null || true
docker compose --env-file secrets/.env up -d nginx
```

### 8.5 Image missing or wrong digest

**Symptoms** — `manifest unknown`, `no such image`, or the running container is
not the release you expected.

**Diagnose**

```bash
grep KARIZ_APP_IMAGE secrets/.env
docker images --digests | grep <app-repository>
docker compose --env-file secrets/.env images
```

**Remediate** — load the correct image ([1.6](#16-images)) and make the digest in
`.env` match exactly. Never edit the digest to match whatever happens to be on the
host; that defeats the pinning.

### 8.6 Migration failure

**Symptoms** — `docker compose run --rm migrate` exits non-zero.

**Diagnose** — read the whole traceback; it names the migration and the SQL.

```bash
docker compose --env-file secrets/.env run --rm --entrypoint sh web -c 'python manage.py showmigrations | tail -40'
```

**Remediate** — see [Failed migration](#failed-migration) in section 5. Do not
re-run blindly and do not skip a migration.

### 8.7 Database role or grant failure

**Symptoms** — `permission denied for table …` at runtime, or `db-finalize`
fails.

**Likely cause** — `db-finalize` never ran after the migrations, so the new tables
carry no grants for the application role.

**Diagnose**

```bash
docker compose --env-file secrets/.env exec db \
  psql -U "$POSTGRES_INIT_USER" -d "$POSTGRES_DB" \
  -c "\dp" | head -30
```

**Remediate**

```bash
docker compose --env-file secrets/.env run --rm db-finalize
```

### 8.8 `db-bootstrap` password mismatch

**Symptoms** — bootstrap completes, then the application cannot authenticate:
`password authentication failed for user`.

**Likely cause** — the password typed at the interactive prompt differs from the
one in `.env`. The prompt sets the role's password; `.env` is what the application
presents. They must be identical.

**Remediate** — re-run `db-bootstrap` and type the exact values from `.env`:

```bash
grep -E 'POSTGRES_(MIGRATION|APP|BACKUP)_PASSWORD' secrets/.env
docker compose --env-file secrets/.env run --rm db-bootstrap
```

### 8.9 A container is unhealthy or restarting

**Diagnose**

```bash
docker compose --env-file secrets/.env ps
docker inspect --format '{{json .State.Health}}' "$(docker compose --env-file secrets/.env ps -q web)" | head -c 2000
docker compose --env-file secrets/.env logs --tail 200 web
```

**Likely causes** — `db` unhealthy: the data volume is missing or corrupt. `web`
restarting: a `.env` validation failure, printed on the first lines of its log.
`nginx` unhealthy: a certificate file is missing or unreadable.

### 8.10 Certificate warning in the browser

**Expected** on a static-IP deployment ([7](#7-static-ip-deployment)). Compare the
fingerprint with the one recorded at generation, then trust it on the machine.

**Not expected** on a domain deployment — check the chain is complete and the
name matches:

```bash
openssl x509 -in secrets/tls/fullchain.pem -noout -subject -ext subjectAltName -dates
echo | openssl s_client -connect "${PUBLIC}:443" -servername "${PUBLIC}" 2>/dev/null | openssl x509 -noout -subject -dates
```

A missing intermediate certificate is the usual cause: `fullchain.pem` must be the
full chain, not just the leaf.

### 8.11 Clock or NTP problems

**Symptoms** — Jalali dates wrong by hours or a day; TLS handshakes fail with
`certificate is not yet valid`; audit timestamps disagree with reality.

**Diagnose**

```bash
timedatectl status
```

**Remediate**

```bash
sudo timedatectl set-timezone Asia/Tehran
sudo systemctl enable --now systemd-timesyncd
timedatectl timesync-status
```

Restart the stack afterwards so every container picks up the corrected clock.

### 8.12 No PyPI or network access on the server

**Expected.** The customer host must never need PyPI: dependencies are baked into
the reviewed image. If a procedure appears to need `pip install` on the customer
host, that procedure is wrong. Use the offline image transfer in [1.6](#16-images).

### 8.13 پیش‌فاکتور (quotations) is visible when it should not be

**Symptoms** — a پیش‌فاکتورها entry in the sidebar, `/quotations/` returns `200`.

**Likely cause** — the signed manifest names the `quotations` feature. The
application's own default has the module off, so a manifest is the only thing
that can switch it back on.

**Diagnose**

```bash
python3 -c "import json;print(json.load(open('secrets/manifest.json'))['features'])"
```

**Remediate** — have the platform owner re-sign the manifest without
`--feature quotations` ([1.10](#110-signed-deployment-manifest)), copy it across,
and recreate `web`. It cannot be fixed by editing the manifest on the host: an
edited manifest fails its signature check and the application refuses to start,
which is the intended behaviour.

### 8.14 Every audit row shows the same IP

**Symptoms** — the activity log records one address, usually `172.x.x.x`, for
every user and every action.

**Likely cause** — `AUDIT_TRUSTED_PROXY_CIDRS` is empty or does not cover the
Compose network, so the application distrusts nginx's `X-Real-IP` and records the
proxy's own address.

**Diagnose**

```bash
docker compose --env-file secrets/.env exec db \
  psql -U "$POSTGRES_APP_USER" -d "$POSTGRES_DB" \
  -c "SELECT ip_address, count(*) FROM auditlog_activitylog GROUP BY 1 ORDER BY 2 DESC LIMIT 5;"
docker network inspect "${KARIZ_COMPOSE_PROJECT_NAME}_frontend" --format '{{(index .IPAM.Config 0).Subnet}}'
```

**Remediate** — set `AUDIT_TRUSTED_PROXY_CIDRS` to that subnet, then
`docker compose --env-file secrets/.env up -d --force-recreate web`. Historical
rows keep the wrong address; only new ones are correct.

---

## 9. Security and secrets

* **`secrets/` is never committed.** It holds `.env`, the TLS private key and the
  signed manifest. `chmod 700 secrets`, `chmod 600 secrets/.env`,
  `chmod 600 secrets/tls/privkey.pem`. **`secrets/manifest.json` is the one
  exception: `chmod 644`.** It is a signed, public feature list the
  non-root application container must read, not a secret — see
  [1.10](#110-signed-deployment-manifest).
* **Never reuse staging secrets in production.** Every `POSTGRES_*_PASSWORD` and
  `DJANGO_SECRET_KEY` is generated fresh per environment.
* **The manifest signing private key never reaches a customer host.** Only the
  public verification key goes in `.env`. Signing happens on the platform owner's
  machine.
* **PostgreSQL is not exposed.** It sits on an internal Docker network and
  publishes no port. `ss -lntp | grep 5432` must return nothing.
* **The reviewed image is the deployment artefact.** The customer host receives
  runtime files — Compose, nginx config, ops scripts — not application source,
  vendor theme sources or demo material.
* **Django Admin is refused at the edge and disabled in the application**, both
  independently. `https://${PUBLIC}/admin/` must return `404`.
* **Logs must not carry customer data.** PostgreSQL is configured to log no
  statements or parameters. Review any log before pasting it into a ticket.

---

## Related documents

This runbook is canonical for deployment and startup. These go deeper on one
subject each and do not restate the procedure:

| Document | Subject |
|---|---|
| the “PostgreSQL backup and restore verification” section of this document | Backup internals and the restore-verification contract |
| the “PostgreSQL role split” section of this document | The per-table privilege contract |
| the “TLS edge procedure” section of this document | Certificate handling detail |
| the “Rollback procedure” section of this document | Rollback detail |
| the “Incident response” section of this document | What to do during an incident |
| the “Synthetic UAT data” section of this document | Acceptance test script |
| the “Client-1 Linux staging guide” section of this document | The original Client-1 staging walkthrough |


---

# Appendix: consolidated ops reference

> Merged 2026-09-01 from the rest of `docs/ops/*.md` into this one file, per direct product-owner decision -- those files no longer exist separately. Each subsection below is one former file, heading levels shifted to nest under this appendix; content is otherwise unchanged. Where a former file's own banner said it "does not restate the procedure, the runbook is correct" -- that banner is removed here since the procedure it deferred to is now this same document.


## PostgreSQL backup and restore verification

*(from `docs/ops/BACKUP_RESTORE.md`)*

The bundled profile-only `backup` service creates verified custom-format PostgreSQL backups over the internal database network. It uses only the managed read-only backup login and one exact external backup volume. The host PowerShell tools remain available for a separately approved host-reachable database and for disposable restore verification. No tool accepts a password argument, overwrites a backup, or restores into a named business database.

### Prerequisites

- Complete `db-bootstrap` for the current role layout. The bundled job fails until the managed backup login exists.
- Set `POSTGRES_BACKUP_USER`, `POSTGRES_BACKUP_PASSWORD`, `POSTGRES_BACKUP_VOLUME`, `POSTGRES_BACKUP_RETENTION_DAYS`, and `POSTGRES_RESTORE_TMPFS_SIZE_BYTES` through the protected deployment environment. The role name must be unused and distinct; the secret must be random, private, at least 16 characters, and different from every other database secret. Size the restore tmpfs in bytes for the full expanded database plus safe headroom; a low value must fail the drill instead of spilling into a business volume.
- Choose one exact external Docker volume backed by protected storage outside the database volume and web/static paths. A remote or separately replicated protected store is preferred; one local Docker volume is not host-loss protection.
- Use PostgreSQL client tools compatible with the server for host-only backup or restore work. Put `pg_dump`, `pg_restore`, `psql`, `createdb`, and `dropdb` on `PATH`, or pass their directory with `-PostgresBin`.
- Supply host-tool authentication through the deployment secret mechanism or a protected PostgreSQL password file. Do not place a password in command history or a script argument.

### Prepare one exact external backup volume

For a reviewed new backup destination only, create the approved volume name and set that exact name as `POSTGRES_BACKUP_VOLUME`. Never guess an old name or substitute the PostgreSQL data volume.

```powershell
$approvedBackupVolume = Read-Host 'Approved new backup volume name'
docker volume create $approvedBackupVolume
```

After the protected environment points to that new empty volume, initialize its fixed sentinel and owner once. This command refuses a nonempty destination and refuses to replace a sentinel:

```powershell
docker compose --profile backup run --rm --no-deps --user root --cap-add CHOWN --entrypoint sh backup -c 'set -eu; test -z "$(find /backups -mindepth 1 -maxdepth 1 -print -quit)"; chown postgres:postgres /backups; chmod 0700 /backups; printf "%s\n" DOLPHIN_BACKUP_ROOT_V1 > /backups/.dolphin-backup-root; chown postgres:postgres /backups/.dolphin-backup-root; chmod 0600 /backups/.dolphin-backup-root'
```

Do not run the initializer to adopt an existing destination. Prove its exact volume record, sentinel, access, backup pairs, and recovery history instead. The backup service runs as `postgres`, has a read-only root filesystem and no Linux capabilities, and is the only service that mounts `backup_data`.

Existing destinations may keep the exact legacy `.dolphin-backup-root` sentinel and exact `dolphin-pg-...` archives as read-only compatibility input. New jobs always publish `dolphin-pg-...`. If both old and new sentinel files exist, both must carry their exact valid values or all backup and restore work fails closed.

### Run the bundled backup job

```powershell
docker compose --profile backup run --rm backup
```

The profile prevents a normal `docker compose up -d` from starting a backup. The explicit command joins only the backend network, waits for database health, reads with `POSTGRES_BACKUP_USER`, and receives no init, migration, or application password. The job validates the fixed mount and sentinel, writes a temporary custom-format archive, runs `pg_restore --list`, calculates SHA-256, writes the checksum sidecar, and renames both files to final names on the same volume. It prints only the generated backup filename. A nonzero exit is failure and must reach the approved alert path.

The job atomically creates the exact `/backups/.dolphin-backup.lock` directory before it connects to PostgreSQL. A second or overlapping run exits nonzero and publishes no archive. Normal exit and handled signals release the lock after exact temporary-file cleanup. An unhandled container kill can leave the lock in place and deliberately blocks later jobs until an operator proves that no backup runs.

Final names use only this form:

```text
dolphin-pg-YYYYMMDDTHHMMSSZ-32_lowercase_hex.dump
dolphin-pg-YYYYMMDDTHHMMSSZ-32_lowercase_hex.dump.sha256
```

Temporary or failed outputs are removed only by their exact generated paths.

### Explicit retention and schedule

`POSTGRES_BACKUP_RETENTION_DAYS` is required and accepts `0` through `3650`. `0` disables deletion and is the safe value for an isolated pre-migration recovery point. A positive value removes only direct, strictly named dump/checksum pairs old enough by file age and only after recalculating and matching the checksum. It never recurses or uses a caller path for deletion.

The repository supplies the runnable one-shot job, not a guessed production schedule. After a manual backup and disposable restore succeed, the deployment owner must record the exact release directory, scheduler identity, daily time, retention days, weekly/off-host copy rule, concurrency rule, timeout, failure alert, and missed-run alert. Schedule this exact noninteractive job from the reviewed release directory:

```powershell
docker compose --profile backup run --rm backup
```

Do not overlap jobs. Treat a lock failure as an alert, not as permission to retry in parallel. First inspect the exact Compose service state:

```powershell
docker compose --profile backup ps --all backup
```

Only after the job owner proves that no backup container or external scheduler run is active may an approved operator remove the one empty stale lock directory:

```powershell
docker compose --profile backup run --rm --no-deps --entrypoint sh backup -c 'set -eu; test -d /backups/.dolphin-backup.lock; test ! -L /backups/.dolphin-backup.lock; rmdir /backups/.dolphin-backup.lock'
```

`rmdir` refuses a nonempty lock. If it fails, preserve the directory and investigate; do not recursively delete it or any backup path. Record the failed run, process proof, approval, exact command, UTC time, and next successful backup/restore result. Docker/Compose does not provide the scheduler or alert system. Destination, schedule, retention, operator, recovery-time target, recovery-point target, alert path, and off-host replication remain explicit deployment inputs.

### Optional host-only backup tool

`scripts/backup-postgres.ps1` keeps the same sentinel, archive-list, checksum, atomic publication, and exact retention guards for a separately approved host that can already reach PostgreSQL. The bundled database publishes no host port, so this script is not the default path into the Compose database. Pass the real approved host, database, backup login, protected root, and compatible client-tool directory; never use the old illustrative `db.internal` name.

### Verify the bundled backup in an isolated disposable database

Use the exact archive leaf printed by the bundled backup. Do not pass a path, connection value, password, or caller-selected database name:

```powershell
$approvedArchive = Read-Host 'Exact archive leaf printed by the successful backup job'
docker compose -f compose.restore-verify.yml --profile restore-verify config --quiet
docker compose -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify $approvedArchive
```

The standalone definition has one service and one external read-only backup-volume mount. It has no business database volume, port, Compose network, database target, or password. The script accepts one strictly named archive, verifies the fixed sentinel, rejects links, matches the exact SHA-256 sidecar, and lists the custom archive before starting a new local cluster. PostgreSQL listens only on a generated Unix-socket directory inside the container. The restore uses owner and privilege replay disabled, one transaction, and a generated database in the bounded `/tmp` mount. Normal `--rm` completion removes the container and its tmpfs; never use a broad container or volume prune for cleanup.

One shared boolean SQL contract checks all nine core tables, exact migration heads, twelve true PostgreSQL constraints, and the two named partial unique phone indexes with their indexed columns and predicates. Both restore tools use this same file. The query returns only `1` or `0`; it does not print business rows.

If the run is interrupted, inspect only the exact stopped restore container from that command and remove only that reviewed container. It has no durable restore volume. Do not delete the backup volume or any database volume.

### Optional host-only restore verifier

For a separately approved backup root already accessible to the host, use only a disposable PostgreSQL server bound to a loopback IP on a high port other than `5432`. The PowerShell verifier rejects remote hosts, low ports, port `5432`, nonstandard backup names, missing or mismatched checksums, and files outside the sentinel root.

```powershell
.\scripts\verify-postgres-restore.ps1 `
  -BackupRoot 'D:\DolphinBackups' `
  -BackupFile 'D:\DolphinBackups\dolphin-pg-20260809T010203Z-0123456789abcdef0123456789abcdef.dump' `
  -TargetHost '127.0.0.1' `
  -TargetPort 55432 `
  -DatabaseUser 'dolphin_restore' `
  -PostgresBin 'C:\Program Files\PostgreSQL\17\bin'
```

The host verifier chooses a new database named `dolphin_restore_verify_<32_lowercase_hex>`. It first proves that name does not exist, creates it, restores with owner and privilege replay disabled, and runs the same shared SQL contract. It drops only that exact generated database in `finally` and refuses any caller-selected target database name.

Never point this verifier at production or staging, even through a tunnel. A successful local guard test is not a real restore drill; final evidence needs a live disposable PostgreSQL engine and recorded operator results without credentials.

### Recovery runbook

For a real recovery, do not overwrite the damaged database in place.

1. Declare the incident and stop business writes through the approved maintenance path.
2. Preserve the failed database and its logs.
3. Select a backup with its matching SHA-256 sidecar and verify the checksum.
4. Restore into a newly created recovery database with reviewed ownership and privileges.
5. Run migrations only when the selected application release requires them and its rollback path is approved.
6. Check health, schema, row counts, role isolation, core customer/lead/sale flows, and audit continuity.
7. Get owner approval before changing application database routing.
8. Keep the prior database and application release until acceptance and rollback windows close.

The live backup destination, daily and weekly retention, alert owner, recovery-time target, recovery-point target, and cutover authority remain deployment decisions.


## Client-1 Linux staging guide

*(from `docs/ops/CLIENT1_LINUX_STAGING_GUIDE.md`)*

Bring Dolphin up on a **fresh Linux amd64 server**, from nothing to a stack
you can hand to UAT. Follow it top to bottom; each section ends with something
you can check.

Two conventions used throughout:

* **FINAL INPUT** — a value or step that must come from the product owner or the
  customer. It is not a placeholder you may invent. Staging can proceed with a
  staging-only substitute where the step says so; production cannot.
* Every credential, host and key below is a placeholder. **Nothing real belongs
  in this file, in Git, or in a shell you did not clear afterwards.**

Related documents, not repeated here: the “Multi-server Docker deployment” section of this document (three
topologies and the split-server override), the “PostgreSQL backup and restore verification” section of this document, the “Rollback procedure” section of this document,
the “PostgreSQL role split” section of this document, the “TLS edge procedure” section of this document, the “Dependency lock” section of this document,
`../backend/DEPLOYMENT_PROFILE.md`.

---

### 0. What you are deploying

A single-host stack: PostgreSQL 17, the Django application under Gunicorn, and
Nginx. Compose starts them in a fixed order and each step must succeed before
the next runs:

```text
db (healthy) → db-bootstrap → migrate → db-finalize → web (healthy) → nginx
```

`db-bootstrap`, `migrate` and `db-finalize` are one-shot jobs. If any exits
non-zero, stop and read its log — the next job will not have run, and the state
is safe to correct.

The application **refuses to start without a valid signed deployment manifest**.
That is deliberate: there is no default feature set to fall back to.

---

### 1. Server assumptions

| Item | Expectation |
|---|---|
| OS | current, supported 64-bit Linux (`x86_64`) — Ubuntu 22.04/24.04 LTS or Debian 12 are the tested shapes |
| Architecture | `linux/amd64`. The image build refuses anything else; ARM is not supported |
| Privileges | a non-root user in the `docker` group, plus `sudo` for firewall and directory creation |
| Clock | NTP synchronised. Audit rows, document timestamps and backup names are evidence |
| Sizing | 2 vCPU / 4 GB RAM / 40 GB disk for one shop. Disk is the constraint: database volume + backup volume + images + logs |

```bash
docker --version            # 24.x or newer
docker compose version      # v2.x — "docker-compose" v1 is not supported
id -nG "$USER" | tr ' ' '\n' | grep -qx docker && echo "docker group: ok"
timedatectl show -p NTPSynchronized --value   # expect: yes
nproc; free -m; df -h /var/lib/docker
```

#### 1.1 Preparing a fresh Ubuntu 24.04 LTS server

Skip this if the four checks above already pass. Run it as a user with `sudo`.

```bash
# Packages and clock.
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get install -y ca-certificates curl openssl

# The application stores UTC and presents Tehran time, so the host clock only
# has to be correct — but matching the operational timezone makes container
# logs, backup filenames and user reports line up with what staff say.
sudo timedatectl set-timezone Asia/Tehran
sudo timedatectl set-ntp true
timedatectl                       # expect: NTP service: active, synchronized
```

Docker Engine and the Compose v2 plugin, from **Docker's own repository** —
Ubuntu's `docker.io` package is frequently too old for the Compose syntax used
here, and `docker-compose` v1 is not supported at all:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker "$USER"   # log out and back in for this to take effect
sudo systemctl enable --now docker
```

On Ubuntu 24.04 the codename resolves to `noble`. If `apt-get update` reports no
release file for it, the server has no route to `download.docker.com` — use the
air-gapped path in section 4 and install Docker from the packages your
organisation mirrors, rather than downgrading to the distribution package.

Log out, log back in, then re-run the four checks above. All four must pass
before section 3.

---

### 2. Network, DNS and TLS

The deployment has exactly one public identity — one hostname **or** one IP —
and it appears in four places that must agree: `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`, `KARIZ_PUBLIC_HOST`, and the certificate. The
application refuses to start if they disagree; that check is the reason a
mistake here fails at boot instead of at login.

Pick the scenario the customer is actually in.

#### Scenario A — the customer has a domain (production shape)

| Item | Value | Status |
|---|---|---|
| Public hostname | `<crm.example.com>` | **FINAL INPUT** |
| DNS A/AAAA record → this server | — | **FINAL INPUT** |
| TLS certificate chain + private key | `secrets/tls/fullchain.pem`, `secrets/tls/privkey.pem` | **FINAL INPUT** |
| VPN / private routing to the customer network | — | **FINAL INPUT** (see the “Target site survey” section of this document) |

```dotenv
DJANGO_ALLOWED_HOSTS=crm.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://crm.example.com
KARIZ_PUBLIC_HOST=crm.example.com
DJANGO_SECURE_HSTS_SECONDS=31536000
KARIZ_HSTS_HEADER=max-age=31536000
```

#### Scenario B — no domain, static public IP only

Supported, and the whole stack works, but read the limitations before promising
it to the customer. Everything below uses `203.0.113.10` as the placeholder for
**the IP users actually type**. Behind NAT that is the public address, not the
address `ip addr` shows on the server.

```dotenv
DJANGO_ALLOWED_HOSTS=203.0.113.10
DJANGO_CSRF_TRUSTED_ORIGINS=https://203.0.113.10
KARIZ_PUBLIC_HOST=203.0.113.10
# HSTS off — see the limitations below. These two must both be set.
DJANGO_SECURE_HSTS_SECONDS=0
KARIZ_HSTS_HEADER=
```

TLS still applies: the stack has no plain-HTTP mode, port 80 only redirects, and
cookies are secure-only. Without a domain the certificate must be self-signed,
generated **on the server** so the private key never travels:

```bash
cd /srv/dolphin/client-1
openssl req -x509 -nodes -newkey rsa:4096 -days 397 \
  -keyout secrets/tls/privkey.pem \
  -out    secrets/tls/fullchain.pem \
  -subj   "/CN=203.0.113.10" \
  -addext "subjectAltName=IP:203.0.113.10" \
  -addext "basicConstraints=critical,CA:FALSE" \
  -addext "keyUsage=critical,digitalSignature,keyEncipherment" \
  -addext "extendedKeyUsage=serverAuth"
chmod 600 secrets/tls/privkey.pem
chmod 644 secrets/tls/fullchain.pem

# Record the fingerprint. Staff compare it once, then trust the certificate.
openssl x509 -in secrets/tls/fullchain.pem -noout -fingerprint -sha256 -dates
```

The `subjectAltName=IP:` line is not optional — every current browser ignores
`CN` and will refuse a certificate that does not name the IP in a SAN.

**Limitations without a domain — state these to the customer in writing:**

1. **Every browser shows a certificate warning** until the certificate is
   installed as trusted on each machine. There is no way around this: no public
   CA issues certificates for an IP address on request, and Let's Encrypt issues
   for domains only. Either staff click through the warning each time a browser
   profile is new, or IT distributes the certificate through Windows Group
   Policy / a trusted-root deployment.
2. **HSTS is off, and must be.** Browsers ignore HSTS for IP hosts anyway, and a
   one-year pin on a self-signed host would leave staff unable to click past
   their own warning for a year, with no undo from the server side. Consequence:
   no protection against a downgrade to plain HTTP by an attacker on the path.
3. **No identity, only encryption.** A self-signed certificate proves the
   connection is encrypted, not who is on the other end. Users are trained to
   accept a warning, which is exactly the habit that makes an interception
   attack work later.
4. **The IP is the address.** Changing ISP or server changes the URL, every
   bookmark, and the certificate. A domain can be repointed in DNS; an IP cannot.
5. **Certificate renewal is manual.** `-days 397` is the browser-accepted
   maximum; put the expiry date in the operations calendar, because nothing on
   the server will remind you.
6. **This is not a production TLS readiness proof.** Record it in the run record
   as staging-only. Production sign-off needs scenario A.

#### Firewall — both scenarios

Ports reachable from users: **443**, and **80** only because it redirects.
Nothing else.

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow OpenSSH        # do not lock yourself out of a remote server
sudo ufw enable
sudo ufw status verbose
# 5432 is never published. Verify later in section 12.
```

---

### 3. Directory layout

```bash
sudo install -d -m 755 -o "$USER" -g "$USER" /srv/dolphin/client-1
cd /srv/dolphin/client-1
install -d -m 700 secrets secrets/tls
```

```text
/srv/dolphin/client-1/
├── compose.yml                  ── from the release artifact
├── compose.restore-verify.yml
├── compose.write-stop.yml
├── nginx/{default.conf,write-stop-off.conf,write-stop-on.conf}
├── scripts/{bootstrap-postgres.sh,backup-postgres.sh,
│            verify-postgres-restore.sh,verify-postgres-schema.sql}
└── secrets/                     ── 700, never in Git, never inside a backup
    ├── .env                     ── 600
    ├── manifest.json            ── signed by the platform owner
    └── tls/{fullchain.pem,privkey.pem}
```

**Do not clone this repository onto the server.** Only the files above plus the
images are deployed.

---

### 4. Release flow and image build

Build on your build machine, not the customer's. The Dockerfile is
hash-pinned and platform-pinned and refuses anything else.

```bash
git clone <repository-url> dolphin-src && cd dolphin-src
git checkout <reviewed-release-commit>

export PYTHON_BASE_IMAGE='python@sha256:<reviewed-64-hex-digest>'
docker build \
  --platform linux/amd64 \
  --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
  --tag dolphin:<release-version> .
```

#### Image-content validation — do not skip

Proves the image ships no documentation, tests, repository metadata, ops
scripts or signing material:

```bash
docker create --name dolphin-check dolphin:<release-version>
docker export dolphin-check | tar -t > /tmp/image-listing.txt
docker rm dolphin-check
python scripts/validate_image_content.py --listing /tmp/image-listing.txt   # expect IMAGE_CONTENT_PASS
```

Push and **record the digest** — the digest, not the tag, is what the deployment
pins:

```bash
docker push <registry>/dolphin:<release-version>
docker inspect --format='{{index .RepoDigests 0}}' <registry>/dolphin:<release-version>
```

Air-gapped alternative:

```bash
docker save dolphin:<release-version> | gzip > dolphin-<release-version>.tar.gz
# transfer, then on the server:
gunzip -c dolphin-<release-version>.tar.gz | docker load
```

#### Optional: server-side PDF

Invoice and quotation PDFs are produced by printing the application's own print
page with a headless browser. Without a browser in the image the feature stays
off and users still get correct Persian PDFs through their browser's
print / save-as-PDF — that is the supported day-one path.

To enable the server-side download, add Chromium to the image and set
`KARIZ_PDF_RENDERER=chromium`. The trade is real: about 300–400 MB and an `apt`
layer that is **not** hash-pinned the way `requirements.txt` is. Record the
installed version in the release notes if you take it.

---

### 5. Secrets and `.env`

Copy `.env.example` from the release artifact to `secrets/.env` and fill every
placeholder. Generate each value independently — never reuse one across roles,
never across deployments:

```bash
umask 077
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # one at a time
chmod 600 secrets/.env
```

| Key | Must be | Status |
|---|---|---|
| `KARIZ_COMPOSE_PROJECT_NAME` | stable, lowercase, unique on this host | — |
| `KARIZ_APP_IMAGE`, `KARIZ_POSTGRES_IMAGE`, `KARIZ_NGINX_IMAGE` | `repository@sha256:<digest>` — never a tag | — |
| `DJANGO_SECRET_KEY` | long random, unique to this deployment | **FINAL INPUT** for production |
| `DJANGO_ALLOWED_HOSTS`, `KARIZ_PUBLIC_HOST` | the hostname users type — or the public IP, §2 scenario B | **FINAL INPUT** |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` + that same hostname or IP | **FINAL INPUT** |
| `DJANGO_SECURE_HSTS_SECONDS`, `KARIZ_HSTS_HEADER` | `31536000` + `max-age=31536000` with a real certificate; `0` + empty for IP-only staging. Nothing in between is accepted | — |
| `AUDIT_TRUSTED_PROXY_CIDRS` | the Compose network nginx proxies from — **not empty**, see below | — |
| `POSTGRES_INIT/MIGRATION/APP/BACKUP_PASSWORD` | four independent values, ≥16 chars | **FINAL INPUT** for production |
| `KARIZ_TLS_CERT_PATH`, `KARIZ_TLS_KEY_PATH` | absolute paths under `secrets/tls/` | **FINAL INPUT** |
| `KARIZ_DEPLOYMENT_MANIFEST_PATH` | absolute path to `secrets/manifest.json` | — |
| `KARIZ_DEPLOYMENT_MANIFEST_KEYS` | `key-id:base64-ed25519-**public**-key` | **FINAL INPUT** |
| `POSTGRES_DATA_VOLUME`, `POSTGRES_BACKUP_VOLUME` | the external volume names from §6 | — |
| `POSTGRES_BACKUP_RETENTION_DAYS` | a deliberate whole-day number | — |
| `POSTGRES_SSLMODE` | leave **empty** on a single host; the database is only on an internal Docker network | — |

The manifest **signing private key never reaches a deployment host.** Only the
public verification key is configured here.

#### `AUDIT_TRUSTED_PROXY_CIDRS` — set it, or the audit trail names nobody

The application believes `X-Real-IP` only from a network listed here. nginx sets
that header, but it reaches the application over Compose's own bridge, so with
this left empty every audit row records **nginx's container address** — the same
address for every user, every action. The rows still exist; they just no longer
say who.

The placeholder `172.16.0.0/12` covers Docker's usual private range. Confirm the
real subnet once the stack is up and narrow it:

```bash
docker network inspect "${KARIZ_COMPOSE_PROJECT_NAME}_frontend" \
  --format '{{(index .IPAM.Config 0).Subnet}}'
```

Then check a real login records a real address:

```bash
docker compose --env-file secrets/.env exec -T db \
  psql -U "${POSTGRES_APP_USER}" -d "${POSTGRES_DB}" \
  -c "SELECT ip_address, count(*) FROM auditlog_activitylog GROUP BY 1 ORDER BY 2 DESC LIMIT 5;"
```

One address with every row on it means this is still wrong. `0.0.0.0/0` is
refused by production validation — trusting every source would let any client
set its own audit address.

---

### 6. External volumes

Compose will not create these, on purpose: an accidental new volume is an empty
database, and an empty database that starts cleanly is how data loss is missed.

```bash
docker volume create client1_postgres_data
docker volume create client1_postgres_backups
docker volume ls | grep client1
```

Put those exact names in `POSTGRES_DATA_VOLUME` / `POSTGRES_BACKUP_VOLUME`.

---

### 7. Client-1 deployment manifest

The manifest decides which features exist. It is signed by the platform owner
**off this server**, and the application refuses to start if it is missing,
altered, unsigned, signed by an unknown key, or names an unknown profile.

**Production signing key: FINAL INPUT.** For staging, generate a *staging-only*
key on your own machine and keep it out of Git and off this server.

On the platform owner's machine:

```bash
python scripts/sign_deployment_manifest.py \
  --profile-id client-1 \
  --private-key <path-outside-any-repository> \
  --key-id <key-id> \
  --output manifest.json \
  --feature customers       --feature products  --feature leads \
  --feature sales           --feature sales_documents \
  --feature after_sales     --feature inventory --feature quotations \
  --feature orders          --feature invoices  --feature payments \
  --feature customer_ledger --feature reports   --feature audit_log
```

That is the Client-1 day-one set: fourteen of the sixteen registered features.
Withheld on purpose — `inbound_sms` (no provider contract) and
`internal_it_role` (only a Platform Admin administers users here). Details in
`../backend/DEPLOYMENT_PROFILE.md`.

Transfer to `secrets/manifest.json`, then `chmod 600 secrets/manifest.json`.

---

### 8. Bring the stack up

```bash
cd /srv/dolphin/client-1
docker compose --env-file secrets/.env config >/dev/null   # validates; prints nothing secret
docker compose --env-file secrets/.env pull
```

`db-bootstrap` **prompts interactively** for each managed role's password — it
uses `psql \password`, so no plaintext password reaches the server. Run it
attached the first time:

```bash
docker compose --env-file secrets/.env up -d db
docker compose --env-file secrets/.env run --rm db-bootstrap
docker compose --env-file secrets/.env up -d
```

Confirm the ordered jobs all finished:

```bash
docker compose --env-file secrets/.env ps -a
```

`db-bootstrap`, `migrate`, `db-finalize` → `Exited (0)`.
`db`, `web`, `nginx` → `Up (healthy)`.

`migrate` runs `migrate --noinput` and then `collectstatic --noinput` into the
shared `static_data` volume. `db-finalize` re-applies the exact runtime
privilege grants after the schema exists.

---

### 9. Static files — check this before anything else

The static layer changed materially in this release and has only ever been
exercised on Windows. It is the single most likely thing to behave differently
here, so verify it before UAT rather than during it.

Sections 9, 10 and 12 use `$PUBLIC` for the identity you set in §2. Set it once
per shell. On a self-signed certificate (§2 scenario B) add `-k` to every `curl`
below — that tells curl to skip verification, which is exactly what the browser
warning is about, and is acceptable here only because you generated the
certificate yourself on this machine:

```bash
export PUBLIC='crm.example.com'     # or: export PUBLIC='203.0.113.10'
```

```bash
for path in \
  /static/css/style.bundle.rtl.css \
  /static/plugins/global/plugins.bundle.rtl.css \
  /static/js/scripts.bundle.js \
  /static/common/dolphin.css \
  /static/common/dolphin-app.js \
  /static/common/brand/favicon.ico \
  /static/common/brand/Logo.png \
  /static/fonts/IRANSansWeb.woff \
  /static/plugins/global/fonts/keenicons/keenicons-duotone.woff ; do
  printf '%s ' "$path"
  curl -s -o /dev/null -w '%{http_code}\n' "https://${PUBLIC}${path}"
done
```

All nine must be `200`. If the theme bundles 404 the UI renders unstyled; if
the fonts 404 the Persian text falls back and the sidebar icons vanish.

Expect roughly **197 files, ~11 MB** in the `static_data` volume — the theme's
demo imagery, unused icon families and LTR bundles are excluded by
`common/management/commands/collectstatic.py`.

---

### 10. Health and readiness

```bash
# Application + database, from inside the container.
docker compose --env-file secrets/.env exec -T web python -c \
"import os,urllib.request;h=os.environ['DJANGO_ALLOWED_HOSTS'].split(',')[0].strip();\
r=urllib.request.Request('http://127.0.0.1:8000/api/v1/health/ready/',headers={'Host':h,'X-Forwarded-Proto':'https'});\
print(urllib.request.urlopen(r,timeout=3).status)"

# The edge over plain HTTP — the only non-redirect HTTP route.
curl -fsS http://127.0.0.1/health/live/ && echo

# The edge over TLS, as a user reaches it.
curl -fsS "https://${PUBLIC}/api/v1/health/ready/" && echo
```

---

### 11. First Platform Admin

Once, on a database with no Platform Admin row:

```bash
docker compose --env-file secrets/.env exec web \
  python manage.py bootstrap_platform_admin --username <approved-username>
```

It prompts twice for the password, takes no password argument, applies the
configured validators, creates a CRM `platform_admin` **without** Django staff
or superuser flags, and writes an audit event. It refuses to run again once a
Platform Admin exists. Do not use `createsuperuser`.

Every other account is then created from the UI by that Platform Admin.

---

### 12. Exposure check

```bash
docker compose --env-file secrets/.env ps --format '{{.Service}}\t{{.Ports}}'
sudo ss -ltnp | grep -E ':(5432|8000)\b' \
  && echo "EXPOSED — stop and fix" || echo "database and app not published: ok"

curl -s -o /dev/null -w 'admin=%{http_code}\n' "https://${PUBLIC}/admin/"
```

Only `nginx` may map `0.0.0.0:80` and `0.0.0.0:443`. `/admin/` must return
**404** — the Django admin is unregistered in production independently of
`DEBUG`, and Nginx denies the prefix. A 200 there is a misconfiguration.

---

### 13. UAT

Sign in as each persona and confirm the shape of what they see. Use synthetic
data only.

**platform_admin**
- Full sidebar including رویدادهای سامانه and user administration.
- Create a user; change a role; open the sessions panel and end a session — the
  user is signed out but the account stays active.
- The role selector offers Sales Agent / Sales Manager / Platform Admin and
  **not** مدیر فنی مشتری (`internal_it_role` is not in the Client-1 manifest).

**sales_manager**
- Customers → create one, filter, export XLSX.
- Leads → assign, follow up. Interactions → log a call.
- Products, categories, warehouses, stock movement, transfer.
- Quotation → Order → Invoice → issue. Stock drops by the invoiced quantity.
- Payment → allocate → invoice shows تسویه جزئی.
- Reports: مطالبات, سود ناخالص, ارزش موجودی, دفتر حساب مشتری, عملکرد. Each XLSX
  downloads and its dates are Jalali.

**sales_agent**
- Sees اسناد بازرگانی and انبار و موجودی; does **not** see صندوق و دریافت or the
  financial reports.
- `/payments/` reached directly returns a Persian 403 card, not a blank page.
- Can prepare a quotation; cannot issue an invoice or move stock.

**Presentation**, on every page: Persian RTL, Dolphin branding, dates Jalali
(`۱۴۰۵/۰۵/۲۵`), no English UI text, no theme or language switcher, no social
sign-in, no placeholder control.

---

### 14. Print and PDF

```text
/invoices/<id>/print/     → Persian RTL sheet, no navigation, Jalali dates
browser print / save-PDF  → correct Persian shaping in the produced file
/invoices/<id>/print.pdf  → 200 only if §4's optional Chromium layer was built;
                            otherwise 503 with a Persian message pointing at
                            browser print. Both are correct behaviour.
```

---

### 15. Performance smoke

Not a load test — a sanity check that nothing is pathological:

```bash
for path in / /customers/ /invoices/ /reports/receivables/ ; do
  printf '%s ' "$path"
  curl -s -o /dev/null -w '%{time_total}s\n' -b <session-cookie> "https://${PUBLIC}${path}"
done
```

Expect well under a second each on an idle staging box. Then open the browser
devtools network panel on the customers list and confirm the page issues a
small, constant number of requests — list endpoints are paginated and
`select_related`/`prefetch_related` are covered by query-growth tests, so a
count that climbs with row count means something regressed.

---

### 16. Reboot and persistence

```bash
sudo systemctl enable --now docker
docker compose --env-file secrets/.env restart web    # web returns healthy
sudo reboot
# after it comes back:
docker compose --env-file secrets/.env ps             # db, web, nginx Up (healthy)
```

Services use `restart: unless-stopped`, so they return with the host. The
one-shot jobs are `restart: "no"` and correctly do not re-run. Confirm a record
created before the reboot is still present.

---

### 17. Backup, restore, rollback

```bash
# Backup (behind a Compose profile, so it never runs on its own)
docker compose --env-file secrets/.env --profile backup run --rm backup
docker run --rm -v client1_postgres_backups:/backups alpine ls -la /backups

# Off-host copy — a backup on the same disk is not a backup
docker run --rm -v client1_postgres_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dolphin-backups-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /backups .
gpg --symmetric --cipher-algo AES256 dolphin-backups-*.tar.gz
scp dolphin-backups-*.tar.gz.gpg <operator>@<backup-destination>:<path>/
shred -u dolphin-backups-*.tar.gz

# A backup is only real once restored — isolated, network_mode: none
docker compose --env-file secrets/.env -f compose.restore-verify.yml \
  --profile restore-verify run --rm restore-verify
```

**Rollback** turns on whether the release applied a migration:

* **No migration** — put the previous image digest back in `.env`, `pull`,
  `up -d`. The database is untouched.
* **A migration applied** — code alone cannot go back, because the old code does
  not know the new schema. Restore the pre-upgrade backup, then redeploy the
  previous digest. This is why the backup in §17 is taken *before* any upgrade.

Full procedures: the “PostgreSQL backup and restore verification” section of this document, the “Rollback procedure” section of this document.

---

### 18. Logs

Every service is capped at 5 × 10 MB JSON files, so logs cannot fill the disk.
PostgreSQL is configured not to log statements, parameters or connections —
customer data must not reach a log file.

```bash
docker compose --env-file secrets/.env logs --tail 200 web
docker compose --env-file secrets/.env logs --since 1h nginx
```

Application logs are structured JSON with a request id. Review any log for
customer data before pasting it into a ticket.

#### Expired sessions — schedule this

Django stops honouring an expired session but never deletes its row, so
`django_session` grows for the life of the deployment and keeps expired session
data at rest indefinitely. Nothing in the stack removes them on its own.

```bash
docker compose --env-file secrets/.env --profile maintenance run --rm session-cleanup
```

The service exists only under the `maintenance` profile, so it never starts with
the stack. Put it on a weekly timer as the deployment user:

```bash
# crontab -e   — 03:30 every Sunday
30 3 * * 0 cd /srv/dolphin/client-1 && docker compose --env-file secrets/.env --profile maintenance run --rm session-cleanup >> /var/log/dolphin-session-cleanup.log 2>&1
```

It is safe to run at any time: it deletes only rows whose expiry has already
passed, so no signed-in user is affected. Check the table is not growing without
bound:

```bash
docker compose --env-file secrets/.env exec -T db \
  psql -U "${POSTGRES_APP_USER}" -d "${POSTGRES_DB}" -c "SELECT count(*) FROM django_session;"
```

---

### 19. Stop, start, update

```bash
# Ordered stop (not `down`, which is where external volumes get detached)
docker compose --env-file secrets/.env stop nginx web db

# Start
docker compose --env-file secrets/.env up -d

# Update: back up and disposable-restore first (§17), enable the edge
# write-stop, set the new digest, then:
docker compose --env-file secrets/.env pull
docker compose --env-file secrets/.env up -d
# re-check §9 static, §10 health, then lift the write-stop
```

Keep the previous image digest written down. It is what rollback needs.

---

### 20. Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| `web` restarts immediately | manifest missing, altered, or signed by an unknown key — fail-closed by design | `docker compose logs web \| tail -40` |
| `must be one reviewed repository@sha256:digest` | a tag was used where a digest is required | the three `*_IMAGE` values in `.env` |
| `external volume not found` | §6 skipped, or the name does not match | `docker volume ls` |
| `db-bootstrap` appears to hang | it prompts interactively and was started detached | re-run with `run --rm`, attached |
| `migrate` exits non-zero | bootstrap incomplete, or the role contract failed | `docker compose logs migrate db-bootstrap` |
| 400 on every request | `DJANGO_ALLOWED_HOSTS` lacks the hostname in use | `.env` vs the browser URL |
| CSRF failure on login | `DJANGO_CSRF_TRUSTED_ORIGINS` missing the `https://` origin | `.env` |
| Nginx will not start | certificate or key path wrong or unreadable | `docker compose logs nginx`; `ls -l secrets/tls/` |
| `KARIZ_HSTS_HEADER must exactly match` | the edge header and `DJANGO_SECURE_HSTS_SECONDS` disagree | §2 — both on, or both off |
| `DJANGO_SECURE_HSTS_SECONDS must be between…` | a value between 0 and one year was set | §2 — only `0` or `31536000`+ |
| Browser warns about the certificate on an IP deployment | expected, self-signed | §2 scenario B limitation 1 |
| Browser refuses to open the site at all, no click-through | HSTS was once enabled on this host name and the browser still holds the pin | clear the pin in the browser's HSTS settings; keep §2 scenario B's `0` |
| Page renders unstyled | theme bundles 404 | §9 |
| Persian text falls back, sidebar icons blank | IRANSans or keenicons 404 | §9 |
| PDF button absent | no renderer configured — expected unless §4's optional step was taken | `KARIZ_PDF_RENDERER` |
| Dates show Gregorian | you are looking at the API or the XLSX `filters` sheet, both canonical by design | `../backend/DATE_AND_CALENDAR.md` |

First move for any start-up failure — every gate reports its own reason:

```bash
docker compose --env-file secrets/.env ps -a
docker compose --env-file secrets/.env logs --tail 60 db-bootstrap migrate db-finalize web
```

---

### 21. Uninstall

**This destroys customer data. Take and verify a final backup first (§17) and
copy it off the host.**

```bash
cd /srv/dolphin/client-1
docker compose --env-file secrets/.env down --remove-orphans   # keeps volumes
docker volume rm client1_postgres_data                         # irreversible
docker volume rm client1_postgres_backups                      # irreversible
sudo rm -rf /srv/dolphin/client-1
docker image rm <app-digest> <postgres-digest> <nginx-digest>
```

On a host with several deployments, every command must name the one deployment.
`docker system prune -a` and `docker volume prune` do **not** distinguish
between customers — do not use them there.

Finally revoke what outlived the host: the TLS certificate, the database
credentials, and the manifest key if it was deployment-specific.

---

### Sign-off checklist

- [ ] §2 scenario recorded (A domain / B IP-only), and if B, the limitations sent to the customer in writing
- [ ] §4 image-content validation: `IMAGE_CONTENT_PASS`
- [ ] §8 `db-bootstrap`, `migrate`, `db-finalize` all `Exited (0)`
- [ ] §9 all eight static assets return 200
- [ ] §10 readiness 200 from inside and through TLS
- [ ] §11 first Platform Admin created; command refuses a second run
- [ ] §12 5432 and 8000 not published; `/admin/` returns 404
- [ ] §13 all three personas behave as described
- [ ] §14 print correct; PDF route behaves per the chosen build
- [ ] §16 survives reboot with data intact
- [ ] §17 backup taken, restored in isolation, rollback rehearsed
- [ ] FINAL INPUT still outstanding, listed explicitly in the run record


## PostgreSQL role split

*(from `docs/ops/DATABASE_ROLES.md`)*

The production stack uses four distinct PostgreSQL logins. It does not use the application or backup login as a cluster superuser or schema owner.

| Environment name | Scope | Rights |
| --- | --- | --- |
| `POSTGRES_INIT_USER` | `db`, `db-bootstrap`, and `db-finalize` only | Existing cluster superuser used only by the two one-shot database jobs to create roles, transfer first-party ownership, and set grants |
| `POSTGRES_MIGRATION_USER` | One-shot database jobs and `migrate` only | Database and `public` schema owner; no superuser, role creation, database creation, replication, or inherited role rights |
| `POSTGRES_APP_USER` | One-shot database jobs and long-running `web` only | Exact table row rights and sequence use; no schema creation, cluster rights, or inherited role rights |
| `POSTGRES_BACKUP_USER` | One-shot database jobs and profile-only `backup` job | Read-only dump login with database connect, schema use, and `SELECT` on current/future public tables and sequences; no row writes, routine execution, schema creation, cluster rights, or inherited role rights |

The four names must be safe lowercase PostgreSQL identifiers and must differ. Each password must be private, random, at least 16 characters, and different from the other passwords. Compose passes only the application password to `web`, only the migration password to `migrate`, and only the backup password to `backup`. All four passwords go only to the two role-management jobs. It does not spread the whole `.env` into application containers.

`db-bootstrap` runs before migration. It prepares roles/passwords, then locks one owner/ACL transaction that removes runtime default privileges. `db-finalize` repeats that guarded flow after migration and reapplies the exact table/sequence/routine policy before `web` may start. Owner transfer and every database/schema/table/sequence/routine/default-ACL change run inside the locked unit. Any SQL error closes the session and rolls back that unit.

Role passwords are set with psql's `\password`, which hashes on the client so no plaintext password ever reaches the server or its log. That meta-command reads the console device, so the isolated PostgreSQL proof harness cannot drive it; the script carries one opt-in branch that derives the identical SCRAM-SHA-256 verifier locally instead. It refuses to act unless the database and role names are disposable proof identifiers on loopback, it never falls back, and no Compose file or `.env.example` sets its flag. Deployment behaviour is unaffected. See `docs/backend/POSTGRES_TESTING.md`.

The exact runtime map gives:

- `SELECT, INSERT` only to ActivityLog, LeadAssignmentHistory, Interaction, and Django admin log;
- `SELECT, INSERT, UPDATE` to mutable CRM and account rows;
- `SELECT, INSERT, UPDATE, DELETE` to Django sessions;
- only the exact extra group-table verbs needed by Django group administration;
- `SELECT` only to migration metadata, content types, and permissions.

Future tables, sequences, and routines receive no runtime rights by default. Existing public-schema routines lose implicit `PUBLIC` and application-role execution rights. `db-finalize` grants sequence use only when its owning table has an exact `INSERT` grant. No runtime routine grant is approved today. Any schema change that needs runtime table or routine access must add an explicit reviewed decision to `scripts/bootstrap-postgres.sh`; the static grant-map test fails when a managed model table is missing.

The backup role is separate from the runtime map. It receives only read rights needed by `pg_dump`: `SELECT` on current public tables and sequences, plus matching migration-owner default privileges for future tables and sequences. It gets no `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, DDL, routine execution, role membership, or row-security bypass. Run a real dump after every schema or PostgreSQL security change; source ACL checks cannot prove `pg_dump` against the target engine.

### New database

Set all names and secrets through the protected deployment secret process. Create one approved, explicitly named Docker volume, set that exact name as `POSTGRES_DATA_VOLUME`, and record it as durable infrastructure. Compose marks this volume external and refuses to create it. This prevents a changed checkout path or Compose project name from silently starting an empty database.

```powershell
$approvedVolume = Read-Host 'Approved new PostgreSQL volume name'
docker volume create $approvedVolume
```

Do this only for a reviewed new installation. Do not run it while adopting an existing database. On the empty named volume, the PostgreSQL image creates `POSTGRES_INIT_USER`. `db-bootstrap` creates the migration, application, and backup roles and prepares narrow defaults, `migrate` builds the schema as its owner, and `db-finalize` applies the exact runtime and backup policy. `web` cannot start until all three one-shot steps succeed.

The long-running `web` container has a read-only root filesystem and a read-only static mount. Only its bounded `/tmp` mount is writable. The `migrate` container keeps the static mount writable for collection.

### Existing named volume

Do not delete, replace, or reinitialize `postgres_data`.

The bundled backup login does not exist before the first in-place role job. The recovery point required below must use the already approved database-owner or legacy backup path. Do not run bootstrap first merely to make the new backup role; that would mutate ownership and ACLs before the recovery gate. After adoption succeeds, use the bundled job in [BACKUP_RESTORE.md](#postgresql-backup-and-restore-verification).

1. Make and verify a fresh recovery point using [BACKUP_RESTORE.md](#postgresql-backup-and-restore-verification).
2. Resolve the exact existing Docker volume from the approved deployment record and inspect that exact name. Do not choose by a likely project prefix, create a replacement, or copy raw database files. Set the proven name as `POSTGRES_DATA_VOLUME`. Because it is external, Compose stops if that exact volume is absent instead of creating an empty substitute.
3. From protected deployment records, identify the exact current PostgreSQL superuser login and its current password. Do not print them.
4. Set that existing login and password as `POSTGRES_INIT_USER` and `POSTGRES_INIT_PASSWORD`. A new name in these fields cannot bootstrap an already initialized volume because the PostgreSQL image does not create roles again.
5. Choose three new, unused, distinct names and secrets for `POSTGRES_MIGRATION_USER`, `POSTGRES_APP_USER`, and `POSTGRES_BACKUP_USER`. The job marks roles it creates and refuses to repurpose an existing unmarked role.
6. Parse the configuration without printing expansion, start `db`, then run the in-place role job:

```powershell
docker compose config --quiet
docker compose up -d db
docker compose ps db
docker compose run --rm db-bootstrap
```

The job does not drop a database, table, row, or volume. It transfers first-party `public` relations and routines owned by the init login to the migration owner, preserves extension-owned objects, and fails if a first-party public relation still has an unapproved owner. Stop on any failure. Do not work around the check with a volume reset.

7. Review the migration plan with the migration role, not the application role:

```powershell
docker compose run --rm --no-deps migrate python manage.py migrate --plan
```

8. Apply the reviewed release through normal Compose startup. Prove `db-bootstrap`, `migrate`, and `db-finalize` exited with code 0, then prove readiness and role-bound business smoke.

### Secret rotation

The one-shot database jobs rotate the migration, application, and backup passwords to the protected values and reapply their attributes and grants. The PostgreSQL image does not rotate the init login on an existing volume. Rotate that credential through a separately approved database-owner procedure, then update the protected secret in the same maintenance change. Never put a password in a command argument, migration, log, ticket, or repository file.

### Evidence boundary

Source tests prove the intended Compose secret scope, transaction boundary, table map, backup-read map, and grant policy only. A real PostgreSQL run must still prove role creation, ownership, advisory-lock serialization, injected-failure rollback, migration success, session login/logout, allowed CRM writes, a complete backup-role dump, denied backup writes/DDL/routine execution, denied application DDL and routine execution, denied audit/history update-delete, restart behavior, and in-place upgrade against a disposable copy of production-like data.


## Dependency lock

*(from `docs/ops/DEPENDENCIES.md`)*

> This document records the dependency contract and dated evidence, not live project status. Current progress, blockers, evidence, and exact next action exist only in `DOLPHIN_PROJECT_HANDOFF.md`.

### Files

- `requirements-direct.txt` holds human-set compatibility ranges for direct production packages.
- `requirements.txt` is the exact version-and-SHA-256 runtime lock installed by the container.
- Runtime-only transitive packages are pinned and every allowed wheel is hashed, so package selection and package bytes fail closed.

### Current target and evidence

- Container target: CPython 3.13 on `linux/amd64`. The Dockerfile rejects another target platform, accepts no mutable base default, and requires `PYTHON_BASE_IMAGE` as one reviewed `repository@sha256:...` input.
- Lock audit date: 2026-08-10.
- Installed metadata used for the lock reports Django 5.2.17 supports Python 3.10 or newer and lists Python 3.13 as supported.
- Each locked package reports Python 3.13 compatibility in installed package metadata.
- `psycopg[binary]` and its binary distribution use the same exact version.
- `tzdata` is locked behind a Windows marker; the Linux container does not install it.
- The lock contains reviewed CPython 3.13 Linux-amd64 hashes. The three platform wheels also contain Windows-amd64 hashes so the guarded local setup remains usable.
- `pip download --require-hashes --only-binary=:all:` passed for both `manylinux_2_17_x86_64/cp313` and `win_amd64/cp313` on 2026-08-10. This proves lock resolution and hashes, not a container build.

### Safe update flow

1. Change direct ranges only when an upgrade is approved.
2. Resolve the full tree in a clean Linux-amd64 container using the same Python 3.13 base.
3. Replace every version and every Linux-amd64 artifact hash in `requirements.txt`; do not merge a partial resolver result. Refresh the Windows-amd64 hashes for compiled wheels in the same review.
4. Prove both target sets with `pip download --require-hashes --only-binary=:all:` and run `python -m pip check` plus the dependency contract test.
5. Run the full backend test suite, schema checks, and a clean container build.
6. Review package release and security notes before deployment.

Validate all four release image inputs before a build or deploy. The check prints no reference value:

```powershell
python scripts/validate_release_images.py
docker build --platform linux/amd64 --build-arg PYTHON_BASE_IMAGE=$env:PYTHON_BASE_IMAGE --tag dolphin-review-build .
```

Push the reviewed application build, resolve its registry digest, and set that exact digest as `KARIZ_APP_IMAGE`. Both `migrate` and `web` use that one image. Production Compose never builds local source.

### Open reproducibility gaps

- No digest value is guessed or committed. Release input validation requires exact application, Python-base, PostgreSQL, and Nginx digest references supplied by the approved artifact process.
- A clean Linux-amd64 container build still needs a host with the container tool installed.
- Registry digest review, artifact scan, and software-bill evidence still belong to the exact release artifact gate.


## Deployment procedure

*(from `docs/ops/DEPLOYMENT.md`)*

> This document defines an operations procedure, not live project status. Current progress, blockers, evidence, and exact next action exist only in `DOLPHIN_PROJECT_HANDOFF.md`.

Procedure snapshot: repository procedure was complete at its recorded release reference; use `DOLPHIN_PROJECT_HANDOFF.md` for the current proof state.

This guide uses the current [Compose definition](../../compose.yml), [production settings](../../config/production_settings.py), [database-role guide](#postgresql-role-split), health routes, and [backup guide](#postgresql-backup-and-restore-verification). It does not prove that a host is ready.

### Current topology and limits

- `KARIZ_COMPOSE_PROJECT_NAME` fixes one reviewed Compose project identity across release directories. The standalone restore verifier derives a separate `<project>-restore-verify` identity. Never change the base project name during deploy, restart, or rollback.
- `db` is PostgreSQL 17 on an internal Compose network and a named `postgres_data` volume. No database port is published.
- `db-bootstrap` waits for database health, creates or repairs distinct migration-owner, application, and backup roles in place, prepares narrow grants, and exits.
- `migrate` receives only the migration-owner secret, waits for `db-bootstrap`, runs `migrate --noinput`, then runs `collectstatic --noinput` into `static_data`.
- `db-finalize` waits for migration, then reapplies the locked exact table grant map and exits. Only the two role-management jobs receive all four database secrets.
- `web` starts only after `db-finalize` succeeds. It receives only the application secret, runs non-root Gunicorn on a read-only root filesystem, mounts static files read-only, and exposes port 8000 only inside Compose.
- `db`, `db-bootstrap`, `migrate`, `db-finalize`, profile-only `backup`, and `web` share an internal backend network. `web` and `nginx` share a separate frontend network. `nginx` cannot join or resolve the database network. The standalone restore verifier has no network.
- `nginx` terminates TLS on port 443, serves `/static/`, proxies the application, and owns `/health/live/`. Port 80 keeps that exact local health route and redirects all other traffic to the fixed approved HTTPS host.
- Base Compose mounts the `off` edge write-stop include. The reviewed `compose.write-stop.yml` override swaps in the `on` include and blocks `POST`, `PUT`, `PATCH`, and `DELETE`; reads and Nginx liveness stay live.
- Application `/api/v1/health/live/` proves process response. `/api/v1/health/ready/` also runs `SELECT 1` against PostgreSQL.
- All seven base Compose services use bounded JSON-file logs: 10 MB per file and five files.
- PostgreSQL disables statement, sampled/slow statement, parameter, connection, disconnection, and duration logging and uses terse error detail. Django framework/root faults use bounded fixed-field JSON without message or exception text. Nginx sends query-free access JSON to stdout and process-level alert errors to stderr, so container caps own those streams.
- Static paths are not content-versioned. Nginx therefore marks them for revalidation instead of a long freshness lifetime; release and rollback never depend on a stale browser copy.
- Production removes `/api/v1/schema/` and `/api/v1/docs/`. A 404 is expected there; validate the OpenAPI document before deployment with the repository command instead of exposing the interactive remote-asset UI.
- TLS paths and the public host are required Compose inputs. Nginx mounts the chain/key read-only, allows TLS 1.2/1.3, and sends a fixed HTTPS scheme to Django. Certificate, hostname, renewal, scanner, and browser proof still need the target host procedure in [TLS.md](#tls-edge-procedure).

### Required release inputs

Do not begin a live change until all items exist:

- exact reviewed release reference and prior release artifact;
- exact stable lowercase `KARIZ_COMPOSE_PROJECT_NAME`, unchanged from the current deployment record;
- exact reviewed `repository@sha256:...` references for the application, Python build base, PostgreSQL, and Nginx; the application ref must be shared by `migrate` and `web`;
- protected `.env` owned by the deployment operator, never committed or printed;
- exact approved existing external PostgreSQL volume name, or explicit new-install approval to create one;
- approved hostname, certificate chain/key paths, renewal owner, and exact trusted proxy CIDR;
- approved database and backup operators;
- a fresh verified recovery point made before migration;
- reviewed migration plan and application/schema compatibility decision;
- rollback decision owner, maintenance window, and user notice path.
- approved write-stop owner plus enable, probe, disable, and reopen criteria.

The production environment must provide every required name from [`.env.example`](../../.env.example). `KARIZ_COMPOSE_PROJECT_NAME` must use the Compose lowercase name rules and must stay identical across release directories and rollback artifacts. `DJANGO_SECRET_KEY` must be private and at least 50 characters. Each database password must be private and at least 16 characters. The init, migration, application, and backup role names must be safe, lowercase, pairwise distinct, and use pairwise distinct passwords. `POSTGRES_RESTORE_TMPFS_SIZE_BYTES` must be an approved capacity for a full disposable restore. `DJANGO_ALLOWED_HOSTS` must contain only `KARIZ_PUBLIC_HOST`; `DJANGO_CSRF_TRUSTED_ORIGINS` must contain only `https://` plus that exact host, with no wildcard, dot prefix, sibling, port, slash, or extra entry. A trusted-proxy list may be empty or contain reviewed CIDRs, but IPv4 and IPv6 `/0` are rejected. SSL redirect must be true and HSTS must be at least one year. TLS chain/key host paths are mandatory. Boolean and numeric settings fail closed. Do not display the environment file to collect evidence.

For an existing `postgres_data` volume, read and complete the in-place upgrade steps in the [database-role guide](#postgresql-role-split) before starting the new stack. Never delete or recreate the volume to adopt the role split.

### Repository proof

Run from a reviewed worktree. These checks use test settings and do not prove the target stack:

```powershell
git status --short
git diff --check
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test --settings=config.test_settings -v 1
python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
python -m pip check
```

Record command, release reference, time, exit code, and reviewer. Do not copy secret-bearing output into the release record.

### Current-compatible write-stop and recovery point

For every existing database, complete this section from the currently deployed compatible release and its current protected inputs before replacing `.env`, loading candidate image references, pulling candidate images, or starting any candidate service. Record the current application and PostgreSQL image digests without printing secrets.

Enable and prove the current release write-stop through its approved override. Keep it on through candidate acceptance:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
```

If the current database already has the managed backup role and bundled job, create the recovery point with the current PostgreSQL image and retention disabled for this run:

```powershell
docker compose --profile backup run --rm -e POSTGRES_BACKUP_RETENTION_DAYS=0 backup
```

Record the exact archive leaf printed by that job. From the reviewed candidate source, load only the current PostgreSQL image digest, exact backup-volume name, and approved restore tmpfs size into the process environment. Do not place candidate database credentials or candidate image values yet. Run the no-network verifier against that exact current-compatible archive:

```powershell
$approvedArchive = Read-Host 'Exact archive leaf printed by the successful backup job'
docker compose -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify $approvedArchive
```

For a legacy database without the managed backup role or bundled job, use the already approved owner/legacy backup path and host-only verifier from [the database-role guide](#postgresql-role-split). Do not run candidate `db-bootstrap` merely to create the backup role. For a proven empty new installation, record explicit new-install approval instead of inventing a recovery point.

The gate passes only with the matching SHA-256 sidecar, successful archive list, protected destination, and successful disposable restore. Guard tests or an archive list alone do not pass. Stop before candidate input changes if any proof fails.

### Target preflight

Only after the current-compatible gate passes, place the candidate protected `.env` through the approved host secret process. Never copy over an existing file without separate review. Load the same four approved candidate image digest references into the command process environment; process values must match the release record and the protected `.env`. Do not print or bulk-load the full secret file into evidence. Then run only quiet configuration validation:

```powershell
Test-Path -LiteralPath '.env'
python scripts/validate_release_images.py
docker compose config --quiet
docker compose pull
docker compose run --rm --no-deps web python manage.py check --deploy --settings=config.production_settings
```

The digest-ref check, quiet Compose parse, and pull do not print reference values through the validator. They prove only exact reference shape and registry fetch, not review, scan, architecture, database, edge, or TLS readiness. Production Compose has no local-build path.

Start only the candidate database service and wait for its health state. The compatible recovery point now exists, but do not run `db-bootstrap`, `migrate`, or `db-finalize` yet.

```powershell
docker compose up -d db
docker compose ps db
```

Stop if the database is not healthy or the exact volume differs from the approved record.

### Preserve edge write-stop

The current-compatible gate already enabled the stop for an existing deployment. Base candidate Compose is the off state; validate both candidate source states without printing expanded configuration:

```powershell
docker compose -f compose.yml config --quiet
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
```

Show current runtime state:

```powershell
docker compose exec -T nginx grep -E '^# dolphin-write-stop: (on|off)$' /etc/nginx/write-stop.conf
```

If the candidate edge must be recreated before application acceptance, recreate it only with the write-stop override and prove the on mount:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
```

Run the safe health and write probes in [INCIDENT_RESPONSE.md](#incident-response). Reopen writes only after the release owner passes the required data, readiness, role, audit, TLS, and browser gates.

Do not run the base off-state recreation yet. Never use a volume-removing teardown for this control. Source and static tests do not prove native Nginx parse, mount replacement, response behavior, or target-host TLS; those remain external gates.

### Recovery point gate

Confirm the current-compatible gate above passed before the candidate `.env`, image pull, or database start. Do not replace it with a new dump made after candidate image or role mutation. Keep the recorded archive, sidecar, restore result, current image references, operator, and UTC time tied to this release.

### Role and migration-plan gate

Only after the compatible recovery point and disposable restore pass may the candidate mutate database roles or ownership and inspect the migration plan with the managed owner:

```powershell
docker compose run --rm db-bootstrap
docker compose run --rm --no-deps migrate python manage.py migrate --plan
```

Stop if role bootstrap fails, the plan differs from review, or a migration lacks a compatible recovery path. Keep writes stopped. Do not continue merely because rerunning the one-shot job might succeed.

### Apply release

After approval, let Compose run the one-shot migration/static service and start the application:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-build
docker compose ps --all
docker compose logs --no-color --tail 200 db-bootstrap migrate db-finalize
```

The `db-bootstrap`, `migrate`, and `db-finalize` services must show exit code 0. `db`, `web`, and `nginx` must become healthy. Treat logs as restricted operational data; review them locally and do not paste raw output into public tickets.

### First Platform Admin

For a new database with no Platform Admin row, active or inactive, run the guarded interactive command exactly once:

```powershell
$approvedUsername = Read-Host 'Approved username'
docker compose exec web python manage.py bootstrap_platform_admin --username $approvedUsername
```

The command prompts twice for the password, accepts no password argument, applies configured password validators, creates a CRM `platform_admin` without staff or superuser flags, and appends a safe audit event. It refuses any later bootstrap when a Platform Admin row already exists. Do not use `createsuperuser` as a substitute.

### Health and smoke gates

Prove application and database readiness from inside `web` without printing environment values:

```powershell
docker compose exec -T web python -c "import os, urllib.request; host=os.environ['DJANGO_ALLOWED_HOSTS'].split(',')[0].strip(); request=urllib.request.Request('http://127.0.0.1:8000/api/v1/health/ready/', headers={'Host': host, 'X-Forwarded-Proto': 'https'}); print(urllib.request.urlopen(request, timeout=3).status)"
```

Prove only the local Nginx process path. This exact HTTP path is the sole non-redirect edge route:

```powershell
Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1/health/live/'
```

After the approved certificate is mounted, replace the placeholder and prove readiness through that edge:

```powershell
$approvedHost = Read-Host 'Approved HTTPS host'
Invoke-WebRequest -UseBasicParsing -Uri "https://$approvedHost/api/v1/health/ready/"
```

Then run controlled browser smoke for `/`, `/login/`, login/logout with CSRF, one safe read per CRM role, static delivery, RTL/Persian output, Dolphin branding, responsive viewports, and clean console/network behavior. Never use production customer data for smoke fixtures.

`/admin/` is **not** part of the smoke path and must return 404: the Django
admin is unregistered in production (`ENABLE_DJANGO_ADMIN` defaults false,
independently of `DEBUG`) and Nginx denies the prefix as well. A 200 there is
a misconfiguration, not a passing check.

Only after every acceptance gate and reopen approval passes, recreate just Nginx from base Compose and prove the off mount:

```powershell
docker compose -f compose.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml exec -T nginx grep -F '# dolphin-write-stop: off' /etc/nginx/write-stop.conf
```

This recreates only `nginx`; it does not stop `web` or `db`.

### Safe full-stack stop and same-release restart

Use this only for an approved full outage after the current release jobs completed successfully. First enable and prove write-stop. Prove that `db-bootstrap`, `migrate`, `db-finalize`, and any prior `backup` job are not running; abort if one is active or a current release job failed. Then create and disposable-restore a fresh retention-disabled backup by the exact procedures above. Record the stable Compose project name, archive leaf, restore result, owner, and UTC time. Stop each long-running service in dependency order; do not use `down`:

```powershell
$approvedProjectName = Read-Host 'Unchanged approved Compose project name'
$restoreProjectName = "${approvedProjectName}-restore-verify"
$approvedProtectedEnv = (Resolve-Path (Read-Host 'Approved protected environment file')).Path
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml --profile backup ps --all db-bootstrap migrate db-finalize backup
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml --profile backup run --rm -e POSTGRES_BACKUP_RETENTION_DAYS=0 backup
$approvedArchive = Read-Host 'Exact archive leaf printed by the successful backup job'
docker compose --project-name $restoreProjectName --env-file $approvedProtectedEnv -f compose.restore-verify.yml --profile restore-verify config --quiet
docker compose --project-name $restoreProjectName --env-file $approvedProtectedEnv -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify $approvedArchive
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml stop --timeout 30 nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml stop --timeout 60 web
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml stop --timeout 120 db
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml ps --all
```

The database, backup, and static volumes remain. Resume the same reviewed release in dependency order, keep the edge write-stop on, and wait for each health gate:

```powershell
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml up -d --no-build --no-deps --wait db
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml up -d --no-build --no-deps --wait web
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml -f compose.write-stop.yml up -d --no-build --no-deps --wait nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
```

Repeat database readiness, role, static, HTTPS, and business smoke before the approved base-Compose Nginx recreation reopens writes. If any service fails, keep writes stopped and use the rollback guide. Never change `KARIZ_COMPOSE_PROJECT_NAME`, delete a container volume, or start a second project as a recovery shortcut.

### Evidence boundary

Repository tests, deploy checks, migration plans, and source review are repository proof. Container health, PostgreSQL migration/restore, Nginx routing, HTTPS/HSTS, browser behavior, capacity, and restart recovery are external proof. Record each separately. Never call a release production-ready from repository proof alone.

Use the [release checklist](#release-checklist) for go/no-go and the [rollback guide](#rollback-procedure) for a failed gate.


## Incident response

*(from `docs/ops/INCIDENT_RESPONSE.md`)*

Status: repository response guide complete; contacts, external secret systems, host controls, and live drills remain deployment inputs.

### Roles and first actions

Assign one incident commander, operations owner, security owner, business owner, and evidence custodian. One person may hold several roles, but ownership must be explicit.

For every incident:

1. record UTC start time, detection source, release reference, affected routes, request IDs, and known user impact;
2. restrict evidence access and preserve original logs/audit data;
3. stop risky releases and business writes through the approved maintenance path when integrity is uncertain;
4. do not destroy containers, volumes, databases, backups, or Git history;
5. choose containment from evidence, not from guess;
6. keep status claims split into observed, inferred, and proved.

The repository has a reversible edge write-stop. Base Compose keeps it off; the approved override turns it on. It is an edge write block, not a maintenance page or database lock.

### Safe first checks

```powershell
docker compose ps --all
docker compose logs --no-color --tail 200 web nginx db db-bootstrap migrate db-finalize
```

Application `/api/v1/health/live/` proves process response only. `/api/v1/health/ready/` runs a database query. Nginx `/health/live/` proves only the edge process path. A green liveness result does not prove database, TLS, authentication, or business-flow health.

Treat all command output as restricted. Do not print `.env`, database connection strings, cookies, headers, request bodies, customer fields, or raw audit rows into shared tickets.

### Reversible edge write-stop

The stop blocks `POST`, `PUT`, `PATCH`, and `DELETE` at both Nginx listeners with stable JSON `503` output and a response/body request ID. `GET`, `HEAD`, and the Nginx `/health/live/` read path stay live. It does not stop database access, shell commands, or direct internal application traffic.

Show the state mounted in the running edge:

```powershell
docker compose exec -T nginx grep -E '^# dolphin-write-stop: (on|off)$' /etc/nginx/write-stop.conf
```

Enable it without restarting the application or database:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
```

Use a non-business probe path. Send no cookie, token, or body:

```powershell
$approvedHost = Read-Host 'Approved HTTPS host'
curl.exe --silent --show-error --include "https://$approvedHost/health/live/"
curl.exe --silent --show-error --head "https://$approvedHost/health/live/"
foreach ($method in 'POST','PUT','PATCH','DELETE') {
    curl.exe --silent --show-error --include --request $method "https://$approvedHost/api/v1/write-stop-probe/"
}
```

Health `GET`/`HEAD` must respond normally. Each write probe must return `503`, `X-Request-ID`, and JSON `error.code` `server_error`; the body request ID must match the header. Stop and inspect if any write reaches Django.

Disable it with base Compose, then prove the off marker:

```powershell
docker compose -f compose.yml config --quiet
docker compose -f compose.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml exec -T nginx grep -F '# dolphin-write-stop: off' /etc/nginx/write-stop.conf
curl.exe --silent --show-error --include --request POST "https://$approvedHost/api/v1/write-stop-probe/"
```

The final probe must no longer return the edge write-stop response; the unused path normally returns application `404`. Never test release by sending a real business write. Record owner, UTC enable/disable times, reason, request IDs, and both state checks.

### Suspected credential exposure

1. Do not copy, quote, test, or transmit the suspected value.
2. Restrict access to the source location and preserve path, time, actor, and access metadata without preserving the value in the ticket.
3. Identify the exact credential owner, service, environment, privileges, and possible exposure window.
4. Have the owner rotate or revoke it in the real secret/database/certificate provider. The repository cannot prove external rotation.
5. Update the protected deployment source, restart only affected services through the approved change path, and test health plus authentication.
6. Verify that the old credential is rejected and the new credential works before marking rotation complete.
7. Decide whether sessions, certificates, database roles, or other dependent credentials also need invalidation.
8. If source or Git may contain the value, preserve evidence and get an approved history-remediation plan. Do not rewrite history during triage.

Local scans, file edits, or service restart are not credential rotation. Never state that rotation is done without provider-side proof.

### Database outage or readiness failure

1. Compare Nginx liveness, application liveness, and application readiness.
2. Inspect `db` health, recent database/application logs, host disk capacity, memory pressure, network state, and credential validity through approved host tools.
3. Determine whether failure is availability-only or whether data integrity may be affected.
4. Do not recreate PostgreSQL, remove `postgres_data`, rerun initialization, or restore over the database.
5. If restart is approved, first prove storage and recovery-point safety. Preserve pre-restart logs.
6. After recovery, require readiness, migration state, role isolation, core business flow, audit continuity, and fresh backup checks.

If integrity is unclear, keep writes stopped and use the new-database recovery path in [BACKUP_RESTORE.md](#postgresql-backup-and-restore-verification).

### Bad deploy or migration

1. Freeze further release work and use the approved edge write-stop if writes may worsen impact.
2. Record current/prior release references, migration service exit, and migration state.
3. Inspect the read-only migration plan:

```powershell
docker compose run --rm --no-deps migrate python manage.py showmigrations --plan
```

4. Decide between a forward fix, schema-compatible prior application, reviewed migration rollback, or restore into a new recovery database.
5. Follow [ROLLBACK.md](#rollback-procedure). Do not issue a generic reverse migration or change migration-table rows.
6. Reopen traffic only after readiness, role, business, audit, report, static, TLS, and browser acceptance gates pass.

### Backup failure

1. Keep the last known good dump and checksum. Do not delete it to make space without the approved retention rule.
2. Preserve the failure time and safe error text; never record passwords or full connection strings.
3. Check required client tools without reading secrets:

```powershell
Get-Command pg_dump,pg_restore,psql,createdb,dropdb -ErrorAction Stop
```

4. Check the exact sentinel-protected root, free space, permissions, database reachability, and alert delivery through approved host controls.
5. Do not bypass sentinel, filename, archive-list, checksum, loopback, high-port, or generated-database guards.
6. After repair, create a new uniquely named backup with retention omitted, verify its checksum/archive list, and run a disposable restore check.
7. Mark recovery complete only after a verified new recovery point and alert-path proof exist.

### Audit and log handling

- Application request logs contain only event, request ID, method, path, status, and duration. The production Django/root fallback stream uses only UTC time, fixed event, logger, level, request ID, method, path, and exception type; it drops record messages, arguments, exception text, and tracebacks. Both streams omit query, body, headers, and client IP.
- Nginx request logs are structured on container stdout and omit query, referrer, and browser-agent data, but contain peer address and timing. Alert-level Nginx errors go to container stderr. Treat both streams as restricted.
- PostgreSQL runs with statement, sampled/slow statement, parameter, connection, disconnection, and duration logging disabled; only panic-level statements can be included in error logs. Preserve a reviewed copy of the effective command with runtime evidence, but never weaken these controls during incident triage.
- ActivityLog is append-only through the application and may contain actor, object, safe changes, request ID, and trusted IP. Do not edit or delete it during response.
- Correlate edge, application, and ActivityLog records by request ID and UTC time. Keep source timestamps and timezone clear.
- Compose log caps are finite. Preserve relevant evidence promptly in an approved restricted store before rotation, with access record and integrity hash.
- Do not place raw logs, customer data, credentials, cookies, or headers in chat, email, or public issue systems.

No central log archive or incident evidence store is configured by this repository. Its retention, access, and deletion rules are external production requirements.

### Recovery and closure

Before closure, record:

- impact window and affected data/users;
- confirmed cause and contributing controls;
- containment and recovery actions with owners and times;
- credential provider proof when rotation occurred;
- database readiness and business acceptance evidence;
- latest verified backup and restore result;
- audit/log preservation location and access owner;
- follow-up fixes, tests, deadlines, and decision owners.

Use [RELEASE_CHECKLIST.md](#release-checklist) before any recovery release. Do not call the incident closed while data integrity, credential status, or recovery-point validity remains unknown.


## Read-only readiness load check

*(from `docs/ops/LOAD_TEST.md`)*

This procedure measures only the edge, application-liveness, or database-readiness health path. It never sends a business request and does not prove Customer, Lead, Sale, report, browser, or full production capacity.

The harness is fail-closed. It sends only `GET`, follows no redirect, uses no environment proxy, and accepts no query, request body, cookie, authorization value, caller header, or credential-bearing URL. It prints one aggregate JSON object and no target host, response body, per-request value, or exception text.

### Required approval and target

Before a non-loopback run, record:

- exact release reference and application image digest;
- exact approved HTTPS origin and the same host entered again as confirmation;
- target environment, owner, UTC window, observer, and abort authority;
- one approved path from `/health/live/`, `/api/v1/health/live/`, or `/api/v1/health/ready/`;
- exact request count, concurrency, request timeout, wall limit, maximum p95 latency, and minimum successful requests per second;
- current error budget and infrastructure saturation limits observed outside this repository.

Do not aim the harness at production without the environment owner and capacity owner approving those exact values. The readiness path reaches PostgreSQL, so treat `/api/v1/health/ready/` as database load. Start with a separately approved low run and stop if host monitoring reaches its abort limit. The script itself cannot see CPU, memory, connection-pool, database-lock, or upstream saturation.

Plain HTTP is accepted only for a literal loopback host. Any other target must use HTTPS with normal certificate and hostname verification. The base URL must be only a canonical origin, with no path, query, fragment, user name, or password. `--confirm-host` must exactly repeat its lowercase host.

### Bounds and pass rule

Every workload and threshold value is required; the script has no guessed load target.

| Input | Accepted bound |
|---|---:|
| Requests | 1 through 2,000 |
| Concurrency | 1 through 32, and no more than requests |
| Per-request timeout | 0.1 through 10 seconds |
| Whole-run wall limit | 1 through 300 seconds |
| Maximum nearest-rank p95 | 1 through 10,000 milliseconds |
| Minimum successful rate | 0.01 through 100,000 requests/second |

A pass requires every requested response to finish with HTTP 200, successful nearest-rank p95 at or below the caller threshold, successful request rate at or above the caller threshold, and wall time within the caller limit. A redirect, non-200 response, transport failure, unfinished request, or threshold miss exits nonzero.

### Exact run

Run from the reviewed release root. Enter no secret in any prompt:

```powershell
$approvedBaseUrl = Read-Host 'Exact approved HTTPS origin, or loopback HTTP origin'
$confirmedHost = Read-Host 'Repeat the exact lowercase host only'
$approvedPath = Read-Host 'Exact allowed health path'
$approvedRequests = Read-Host 'Approved request count'
$approvedConcurrency = Read-Host 'Approved concurrency'
$approvedTimeout = Read-Host 'Approved per-request timeout seconds'
$approvedWall = Read-Host 'Approved whole-run wall limit seconds'
$approvedP95 = Read-Host 'Approved maximum p95 milliseconds'
$approvedRate = Read-Host 'Approved minimum successful requests per second'
python scripts/load_readiness.py `
  --sentinel DOLPHIN_READ_ONLY_LOAD_V1 `
  --base-url $approvedBaseUrl `
  --confirm-host $confirmedHost `
  --path $approvedPath `
  --requests $approvedRequests `
  --concurrency $approvedConcurrency `
  --timeout-seconds $approvedTimeout `
  --max-wall-seconds $approvedWall `
  --max-p95-ms $approvedP95 `
  --min-requests-per-second $approvedRate
if ($LASTEXITCODE -ne 0) { throw 'Read-only readiness load gate failed.' }
```

Run one path per command so the result stays attributable. Do not run the three paths concurrently. Do not add application paths, HTTP methods, headers, login state, CSRF tokens, query values, or request bodies to this tool.

### Safe result and evidence

The one-line result contains only:

- fixed event name and allowed endpoint path;
- requested, completed, successful, error, transport-error, and unfinished counts plus aggregate error rate;
- numeric HTTP status counts;
- wall time, successful request rate, and aggregate successful latency values;
- caller thresholds and final pass boolean.

It does not contain the origin, confirmed host, response content, raw error, timestamp, credential, or request sample. Capture stdout and the process exit code through the approved restricted evidence runner. Bind the evidence record to the release reference, image digest, environment, approved target record, external CPU/memory/database metrics, UTC start/end time, runner/tool version, and named reviewer. Apply the approved evidence access, integrity-hash, retention, and deletion policy. Do not paste raw host monitoring, customer data, environment output, or secrets into a ticket.

Repository tests exercise the bounds and a local loopback server only. They do not prove public TLS, the deployed edge, PostgreSQL capacity, a production-shaped host, or any approved service-level target.


## Multi-server Docker deployment

*(from `docs/ops/MULTI_SERVER_DOCKER_DEPLOYMENT.md`)*

How to bring Dolphin up on **clean Linux servers**, in three topologies:

1. one server running the application and PostgreSQL together;
2. the application and PostgreSQL on separate servers;
3. several isolated customer deployments on shared infrastructure.

This document is the *from nothing* runbook. It does not replace the existing
operational documents and deliberately does not repeat them:

| For | Read |
|---|---|
| Upgrading an already-running deployment | the “Deployment procedure” section of this document |
| Backup and restore procedure and evidence | the “PostgreSQL backup and restore verification” section of this document |
| Rollback procedure | the “Rollback procedure” section of this document |
| Database roles and the privilege contract | the “PostgreSQL role split” section of this document |
| Certificate issuance and TLS policy | the “TLS edge procedure” section of this document |
| Dependency lock rules | the “Dependency lock” section of this document |
| Feature manifest design | `../backend/DEPLOYMENT_PROFILE.md` |

**No real secret, key, certificate, password, hostname, or customer identifier
belongs in this file or anywhere else in Git.** Every value below is a
placeholder. Commands that would print a secret are written so they do not.

---

### 0. What the shipped Compose file actually is

Read this before planning, because it decides what each topology costs.

* `compose.yml` has **no `build:` section**. It only *pulls* images by digest
  (`KARIZ_APP_IMAGE`, `KARIZ_POSTGRES_IMAGE`, `KARIZ_NGINX_IMAGE`). Building is
  a separate, earlier step (§3) and is not done on the customer's server.
* The `backend` network is `internal: true`. The database is reachable only
  from containers on that network — never from the host or the outside.
* Only `nginx` publishes ports, `80` and `443`. Nothing else is published.
* `postgres_data` and `backup_data` are **external** volumes: Compose will not
  create them, and refuses to start until they exist (§5).
* Start-up order is enforced by conditions, not by timing:
  `db` (healthy) → `db-bootstrap` → `migrate` → `db-finalize` → `web`
  (healthy) → `nginx`. Each job must exit zero or the next never runs.
* `web` and `backup` run `read_only: true` with a small tmpfs. The application
  cannot write to its own image.
* The application **refuses to start without a valid signed manifest**. That is
  deliberate (`PROFILE-001`): there is no default feature set to fall back to.

---

### 1. Prerequisites on every server

Target: a current, supported 64-bit Linux (`x86_64`). The application image is
built for `linux/amd64`; an ARM host is not a supported target.

```bash
# Docker Engine and the Compose v2 plugin, from Docker's own repository.
# Distribution packages are frequently too old for the Compose syntax used here.
docker --version            # expect 24.x or newer
docker compose version      # expect v2.x — "docker-compose" v1 is NOT supported
```

Also confirm, before going further:

```bash
id -nG "$USER" | tr ' ' '\n' | grep -qx docker && echo "docker group: ok"
timedatectl show -p NTPSynchronized --value    # expect "yes" — audit timestamps
df -h /var/lib/docker                          # see the sizing note below
free -m
nproc
```

**Sizing.** The application runs three Gunicorn workers. A single-server
deployment for one shop is comfortable at 2 vCPU / 4 GB RAM / 40 GB disk.
Disk is the one to watch: it holds the database volume, the backup volume, and
Docker's own images and logs.

**Clock.** Audit rows, document timestamps, and backup names are all in UTC and
are evidence. An unsynchronised clock corrupts that evidence quietly.

**Firewall.** Only 443 (and 80, which redirects) should be reachable by users.
Never publish 5432. See §8.

---

### 2. Directory layout on the deployment host

Use one directory per deployment. Everything outside Git lives here.

```text
/srv/dolphin/<deployment-name>/
├── compose.yml                  # copied from the release artifact
├── compose.restore-verify.yml   # copied from the release artifact
├── compose.write-stop.yml       # copied from the release artifact
├── nginx/                       # copied from the release artifact
│   ├── default.conf
│   ├── write-stop-off.conf
│   └── write-stop-on.conf
├── scripts/                     # only the ops scripts Compose mounts
│   ├── bootstrap-postgres.sh
│   ├── backup-postgres.sh
│   ├── verify-postgres-restore.sh
│   └── verify-postgres-schema.sql
├── secrets/                     # chmod 700, never in Git, never in a backup
│   ├── .env                     # chmod 600
│   ├── manifest.json            # signed by the platform owner
│   └── tls/
│       ├── fullchain.pem        # chmod 644
│       └── privkey.pem          # chmod 600
```

```bash
sudo install -d -m 755 -o "$USER" -g "$USER" /srv/dolphin/<deployment-name>
cd /srv/dolphin/<deployment-name>
install -d -m 700 secrets secrets/tls
```

The application source tree is **not** deployed. Only the files above plus the
images. Do not clone this repository onto a customer server.

---

### 3. Build the application image (on your build machine, not the customer's)

The build is hash-pinned and platform-pinned; the Dockerfile refuses anything
else. `PYTHON_BASE_IMAGE` must be a digest reference for CPython 3.13.

```bash
# On a Linux amd64 build host, from a checkout of the reviewed commit.
export PYTHON_BASE_IMAGE='python@sha256:<reviewed-64-hex-digest>'

docker build \
  --platform linux/amd64 \
  --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
  --tag dolphin:<release-version> \
  .
```

Then prove the image ships nothing it should not — no docs, no tests, no
repository metadata, no scripts, no signing key:

```bash
docker create --name dolphin-check dolphin:<release-version>
docker export dolphin-check | tar -t > /tmp/image-listing.txt
docker rm dolphin-check
python scripts/validate_image_content.py --listing /tmp/image-listing.txt
```

Push to the registry the customer host can reach, then **record the digest** —
the digest, not the tag, is what the deployment pins:

```bash
docker push <registry>/dolphin:<release-version>
docker inspect --format='{{index .RepoDigests 0}}' <registry>/dolphin:<release-version>
```

For an air-gapped site, move the image as a file instead:

```bash
docker save dolphin:<release-version> | gzip > dolphin-<release-version>.tar.gz
# transfer, then on the target:
gunzip -c dolphin-<release-version>.tar.gz | docker load
```

#### Optional: server-generated PDF

Invoice and quotation PDFs are produced by printing the application's own print
page with a headless browser (`common/pdf.py`). Without a browser in the image,
the feature stays off and users still get correct PDFs through their own
browser's print / save-as-PDF — that is the supported day-one path.

To enable server-side download, the image needs a Chromium binary. Understand
the trade before doing it: it adds roughly 300–400 MB and an `apt` layer that is
**not** hash-pinned the way `requirements.txt` is, which weakens the
reproducible-build property this repository otherwise maintains. Record the
exact installed version in the release notes if you take this path.

```dockerfile
# Added after the pip install layer, before `COPY . .`
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*
```

Then set in `.env`: `KARIZ_PDF_RENDERER=chromium`. Leave
`KARIZ_PDF_CHROMIUM_BINARY` empty so the binary is found on `PATH`. The download
button appears in the UI only when the server confirms a working renderer.

---

### 4. Secrets and the `.env` file

Copy `.env.example` from the release artifact to `secrets/.env`, then fill every
placeholder. Generate each password independently — never reuse one across
roles, and never across deployments:

```bash
umask 077
# One value at a time, so nothing lands in shell history in a reusable block.
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`DJANGO_SECRET_KEY` gets its own long random value. The four database roles
(`init`, `migration`, `app`, `backup`) each get their own; passwords shorter
than 16 characters are refused at start-up.

```bash
chmod 600 secrets/.env
```

Values that must match reality rather than being invented:

| Key | Must be |
|---|---|
| `KARIZ_COMPOSE_PROJECT_NAME` | stable, lowercase, unique per deployment on the host |
| `KARIZ_APP_IMAGE` / `KARIZ_POSTGRES_IMAGE` / `KARIZ_NGINX_IMAGE` | `repository@sha256:<digest>` — never a tag |
| `DJANGO_ALLOWED_HOSTS`, `KARIZ_PUBLIC_HOST` | the real hostname users type |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` + that hostname |
| `KARIZ_TLS_CERT_PATH` / `KARIZ_TLS_KEY_PATH` | absolute paths under `secrets/tls/` |
| `KARIZ_DEPLOYMENT_MANIFEST_PATH` | absolute path to `secrets/manifest.json` |
| `KARIZ_DEPLOYMENT_MANIFEST_KEYS` | `key-id:base64-ed25519-public-key` — the **public** key only |
| `POSTGRES_DATA_VOLUME` / `POSTGRES_BACKUP_VOLUME` | the external volume names from §5 |
| `POSTGRES_BACKUP_RETENTION_DAYS` | a deliberate whole-day number |

Never place the manifest **signing** private key on a deployment host. It stays
with the platform owner. Only the public verification key is configured here.

---

### 5. Create the external volumes

Compose will not create these, on purpose: an accidental new volume is an empty
database, and an empty database that starts cleanly is how data loss gets
missed.

```bash
docker volume create <deployment>_postgres_data
docker volume create <deployment>_postgres_backups
docker volume ls | grep <deployment>
```

Put those exact names in `POSTGRES_DATA_VOLUME` and `POSTGRES_BACKUP_VOLUME`.

---

### 6. Obtain the signed deployment manifest

The manifest decides which features exist in this deployment. It is signed by
the platform owner **off the customer's host**, and the application refuses to
start if it is missing, altered, unsigned, signed by an unknown key, or names an
unknown profile or feature.

On the platform owner's machine (never on the server):

```bash
python scripts/sign_deployment_manifest.py \
  --profile-id client-1 \
  --private-key <path-outside-any-repository> \
  --key-id <key-id> \
  --output manifest.json \
  --feature customers       --feature products  --feature leads \
  --feature sales           --feature sales_documents \
  --feature after_sales     --feature inventory --feature quotations \
  --feature orders          --feature invoices  --feature payments \
  --feature customer_ledger --feature reports   --feature audit_log
```

The Client-1 day-one feature set, and the one module deliberately withheld, are
recorded in `../backend/DEPLOYMENT_PROFILE.md`. Transfer `manifest.json` to
`secrets/manifest.json` on the server (`chmod 600`).

---

### 7. Topology 1 — one server, application and database together

The shipped `compose.yml` describes exactly this. Recommended for a single site.

```bash
cd /srv/dolphin/<deployment-name>
docker compose --env-file secrets/.env config >/dev/null   # validates, prints nothing secret
docker compose --env-file secrets/.env pull
docker compose --env-file secrets/.env up -d
```

`db-bootstrap` will **prompt interactively** for each managed role's password
(it uses `psql \password` so plaintext never reaches the server). Run it
attached the first time:

```bash
docker compose --env-file secrets/.env up db
docker compose --env-file secrets/.env run --rm db-bootstrap
```

Watch the ordering complete, then confirm every job exited zero:

```bash
docker compose --env-file secrets/.env ps -a
```

`db-bootstrap`, `migrate`, and `db-finalize` must all show `Exited (0)`; `db`,
`web`, and `nginx` must show `Up (healthy)`.

Continue at §10 (health), §11 (first admin).

---

### 8. Topology 2 — application and database on separate servers

Use this when the database must live on its own hardware or a hardened host.

**Read this first.** The override below uses the `!reset` and `!override` merge
keywords, which need Compose **v2.24.4 or newer**; check `docker compose version`
before relying on them. The shipped `compose.yml` is written for a single host: it
pins `POSTGRES_HOST: db` and marks the `backend` network `internal: true`. A
split deployment therefore needs a small, explicit override — and it needs
transport security, because the connection now crosses a real network instead of
a Docker bridge that never leaves the machine.

#### 8.1 Database server (server B)

Run PostgreSQL 17 with **TLS enabled** and reachable only from the application
server's address. Create `compose.db.yml` on server B:

```yaml
name: ${KARIZ_COMPOSE_PROJECT_NAME}-db

services:
  db:
    image: ${KARIZ_POSTGRES_IMAGE}
    restart: unless-stopped
    command:
      - postgres
      - -c
      - ssl=on
      - -c
      - ssl_cert_file=/tls/server.crt
      - -c
      - ssl_key_file=/tls/server.key
      - -c
      - log_statement=none
      - -c
      - log_min_error_statement=panic
      - -c
      - log_connections=off
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_INIT_USER}
      POSTGRES_PASSWORD: ${POSTGRES_INIT_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./secrets/db-tls:/tls:ro
    ports:
      # Bind to the private interface only. Never 0.0.0.0.
      - "<server-B-private-ip>:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
    external: true
    name: ${POSTGRES_DATA_VOLUME}
```

Restrict access at the firewall as well as the bind address:

```bash
sudo ufw allow from <server-A-private-ip> to any port 5432 proto tcp
sudo ufw deny 5432
```

Require TLS and SCRAM in `pg_hba.conf` — `hostssl` only, never `host`:

```text
hostssl  all  all  <server-A-private-ip>/32  scram-sha-256
```

#### 8.2 Application server (server A)

Create `compose.split.yml` next to `compose.yml`:

```yaml
# Application-only deployment: the database lives on another host.
services:
  db: !reset null            # the local database service is not used here

  migrate:
    depends_on: !override []
    environment:
      POSTGRES_HOST: ${POSTGRES_REMOTE_HOST}
      POSTGRES_SSLMODE: verify-full
      POSTGRES_SSLROOTCERT: /tls/db-ca.pem
    volumes:
      - ./secrets/tls/db-ca.pem:/tls/db-ca.pem:ro
    networks: !override [frontend]

  web:
    depends_on: !override []
    environment:
      POSTGRES_HOST: ${POSTGRES_REMOTE_HOST}
      POSTGRES_SSLMODE: verify-full
      POSTGRES_SSLROOTCERT: /tls/db-ca.pem
    volumes:
      - ./secrets/tls/db-ca.pem:/tls/db-ca.pem:ro
    networks: !override [frontend]
```

`verify-full` is the only mode that authenticates the database server as well as
encrypting the link; `require` encrypts but would accept an impostor.
`POSTGRES_SSLROOTCERT` is mandatory whenever the mode verifies — the application
refuses to start without it, rather than silently downgrading.

Role bootstrap runs against the remote host from server A:

```bash
docker compose --env-file secrets/.env -f compose.yml -f compose.split.yml \
  run --rm -e POSTGRES_HOST="${POSTGRES_REMOTE_HOST}" db-bootstrap
docker compose --env-file secrets/.env -f compose.yml -f compose.split.yml up -d
```

**Honest limits of this topology.** The private network between A and B is now
part of the trust boundary. The repository's proofs (`P0R.2`) were executed
against a single host; the split shape is configuration this document specifies,
not something this repository has yet exercised end to end. Prove it on staging
before a customer depends on it: connect, migrate, run the privilege verifier,
and take one backup and one restore.

---

### 9. Topology 3 — several isolated customer deployments

One host, several customers, no shared state. Isolation comes from giving each
deployment its own everything:

| Per deployment | How |
|---|---|
| Directory | `/srv/dolphin/<customer>/` |
| Compose project | distinct `KARIZ_COMPOSE_PROJECT_NAME` |
| Database volume | distinct `POSTGRES_DATA_VOLUME` |
| Backup volume | distinct `POSTGRES_BACKUP_VOLUME` |
| Database name and all four role passwords | distinct |
| `DJANGO_SECRET_KEY` | distinct |
| Signed manifest | distinct — this is what makes feature sets differ |
| Hostname and certificate | distinct |
| Published port | see below |

Compose names networks and containers per project, so two deployments never
share a network or reach one another's database.

Only one deployment can hold ports 80/443. For the others, publish on distinct
loopback ports and put a single host-level reverse proxy in front, routing by
hostname:

```yaml
# compose.ports.yml for each additional deployment
services:
  nginx:
    ports: !override
      - "127.0.0.1:<unique-port>:80"
```

**Never** copy a `.env` between customers and edit it. A shared
`DJANGO_SECRET_KEY` means sessions forged in one deployment are valid in
another; a shared database password means one customer's credentials open
another's data. Generate every value fresh.

Feature differences between customers belong in the **manifest**, never in a
code branch or a per-customer image. One image serves every deployment.

---

### 10. Health, static assets, and port exposure

```bash
# Application readiness, including the database, from inside the container.
docker compose --env-file secrets/.env exec -T web python -c \
"import os,urllib.request;h=os.environ['DJANGO_ALLOWED_HOSTS'].split(',')[0].strip();\
r=urllib.request.Request('http://127.0.0.1:8000/api/v1/health/ready/',headers={'Host':h,'X-Forwarded-Proto':'https'});\
print(urllib.request.urlopen(r,timeout=3).status)"

# The edge, over plain HTTP: this is the only non-redirect HTTP route.
curl -fsS http://127.0.0.1/health/live/ && echo

# The edge, over TLS, as a user reaches it.
curl -fsS "https://<public-host>/api/v1/health/ready/" && echo

# Static assets are served by Nginx from the shared volume.
curl -fsS -o /dev/null -w '%{http_code}\n' "https://<public-host>/static/common/dolphin.css"
```

Prove nothing sensitive is published:

```bash
docker compose --env-file secrets/.env ps --format '{{.Service}}\t{{.Ports}}'
sudo ss -ltnp | grep -E ':(5432|8000)\b' && echo "EXPOSED — fix before going further" || echo "database and app not published: ok"
```

Expected: only `nginx` maps `0.0.0.0:80` and `0.0.0.0:443`. `/admin/` is
returned as 404 by Nginx and the Django admin is disabled in production
settings; both layers would have to change to expose it.

---

### 11. First Platform Admin

Once, on a database with no Platform Admin row:

```bash
docker compose --env-file secrets/.env exec web \
  python manage.py bootstrap_platform_admin --username <approved-username>
```

It prompts twice for the password, takes no password argument, applies the
configured validators, creates a CRM `platform_admin` **without** Django staff
or superuser flags, and writes an audit event. It refuses to run again once a
Platform Admin exists. Do not use `createsuperuser`.

Every other account is then created from the UI by that Platform Admin. Only a
Platform Admin can create, edit, deactivate, or reset a user.

---

### 12. Persistence across restart

Prove the volume, not the container, holds the data:

```bash
docker compose --env-file secrets/.env restart web
docker compose --env-file secrets/.env ps          # web healthy again
# Then, in the UI, confirm a record created before the restart is still present.
```

For a full-stack restart, follow the ordered stop procedure in the “Deployment procedure” section of this document
(§"Safe full-stack stop") rather than `docker compose down`, which is where
external volumes get detached by accident.

---

### 13. Backups and restore

The `backup` service is behind a Compose profile, so it never runs on its own:

```bash
docker compose --env-file secrets/.env --profile backup run --rm backup
docker run --rm -v <deployment>_postgres_backups:/backups alpine ls -la /backups
```

Copy archives off the host — a backup on the same disk as the database is not a
backup:

```bash
docker run --rm -v <deployment>_postgres_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/dolphin-backups-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /backups .
# Encrypt before it leaves the host; keep the passphrase in your secret manager.
gpg --symmetric --cipher-algo AES256 dolphin-backups-*.tar.gz
scp dolphin-backups-*.tar.gz.gpg <operator>@<backup-destination>:<path>/
shred -u dolphin-backups-*.tar.gz
```

**A backup is only real once restored.** The repository ships an isolated
verifier that restores into a throwaway database with `network_mode: none` and
checks the schema contract:

```bash
docker compose --env-file secrets/.env -f compose.restore-verify.yml \
  --profile restore-verify run --rm restore-verify
```

Run it on a schedule, not only at install. Full procedure and evidence
requirements: the “PostgreSQL backup and restore verification” section of this document.

---

### 14. Logging

Every service is capped at 5 × 10 MB JSON files, so logs cannot fill the disk.
PostgreSQL is configured not to log statements, parameters, or connections —
customer data must not end up in a log file.

```bash
docker compose --env-file secrets/.env logs --tail 200 web
docker compose --env-file secrets/.env logs --since 1h nginx
```

Application logs are structured JSON with a request id. Never paste raw logs
into a ticket without reviewing them for customer data first.

---

### 15. Start on boot

Services use `restart: unless-stopped`, so Docker restarts them with the host.
Make sure Docker itself starts:

```bash
sudo systemctl enable --now docker
sudo systemctl is-enabled docker
```

The one-shot jobs (`db-bootstrap`, `migrate`, `db-finalize`) are
`restart: "no"` and correctly do not re-run on reboot.

For a reboot-time ordering guarantee, add a unit that runs `docker compose up -d`
for each deployment directory after `docker.service`.

---

### 16. Upgrade

Follow the “Deployment procedure” section of this document for the full gated procedure. In outline:

1. Take a fresh backup **and disposable-restore it** (§13). Do not skip this.
2. Enable the edge write-stop (`compose.write-stop.yml`) so no write lands
   mid-upgrade.
3. Update `KARIZ_APP_IMAGE` to the new **digest** in `secrets/.env`.
4. `docker compose --env-file secrets/.env pull`
5. `docker compose --env-file secrets/.env up -d` — the ordered jobs re-run and
   `migrate` applies new migrations.
6. Prove health (§10), then lift the write-stop.

Keep the previous image digest written down. It is what rollback needs.

---

### 17. Rollback

Full procedure in the “Rollback procedure” section of this document. The decisive question is whether the release
applied a migration:

* **No migration applied** — put the previous digest back in `.env`, `pull`,
  `up -d`. The database is untouched.
* **A migration applied** — code alone cannot go back, because the old code does
  not know the new schema. Restore the pre-upgrade backup taken in §16 step 1,
  then redeploy the previous digest. This is why that step is not optional.

---

### 18. Disaster recovery

Rebuilding on new hardware needs exactly four things, and losing any one of them
is unrecoverable by itself:

1. the `secrets/.env` values (especially `DJANGO_SECRET_KEY` and the role
   passwords);
2. the signed `manifest.json` — or the platform owner's ability to reissue it;
3. the most recent verified backup archive;
4. the image digests for the release being restored.

```bash
# On the replacement host: §1, §2, §5, then restore before first start.
docker volume create <deployment>_postgres_data
docker compose --env-file secrets/.env up -d db
# Restore per BACKUP_RESTORE.md, then bring up the rest:
docker compose --env-file secrets/.env up -d
```

Store items 1, 2 and 4 in your secret manager, and item 3 off-site. Rehearse
this at least once before a customer relies on it.

---

### 19. Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| `web` restarts immediately | manifest missing, altered, or signed by an unknown key — this is fail-closed by design | `docker compose logs web \| tail -40` |
| `must be one reviewed repository@sha256:digest` | a tag was used where a digest is required | the three `*_IMAGE` values in `.env` |
| `external volume not found` | §5 was skipped or the name does not match | `docker volume ls` |
| `db-bootstrap` hangs | it prompts interactively; it was started detached | run it with `run --rm`, attached |
| `migrate` exits non-zero | bootstrap did not complete, or the role contract failed | `docker compose logs migrate db-bootstrap` |
| 400 on every request | `DJANGO_ALLOWED_HOSTS` does not contain the hostname used | `.env` vs. the URL in the browser |
| CSRF failures on login | `DJANGO_CSRF_TRUSTED_ORIGINS` missing the `https://` origin | `.env` |
| Nginx will not start | certificate or key path wrong, or unreadable | `docker compose logs nginx`, then `ls -l secrets/tls/` |
| Static assets 404 | `migrate` (which runs `collectstatic`) did not complete | re-run it, then check the `static_data` volume |
| PDF download button absent | no renderer configured — expected unless §3's optional step was taken | `KARIZ_PDF_RENDERER` |
| Split topology cannot connect | TLS, `pg_hba.conf`, firewall, or bind address | §8 |

A useful first move for any start-up failure, since every gate reports its own
reason:

```bash
docker compose --env-file secrets/.env ps -a
docker compose --env-file secrets/.env logs --tail 60 db-bootstrap migrate db-finalize web
```

---

### 20. Complete uninstall

**This destroys customer data. Take and verify a final backup first (§13), and
copy it off the host.** Then confirm you are in the right directory and
targeting the right project — the volume names are the point of no return.

```bash
cd /srv/dolphin/<deployment-name>
docker compose --env-file secrets/.env config --format json | grep -o '"name": *"[^"]*"' | head -1

docker compose --env-file secrets/.env down --remove-orphans   # keeps volumes
docker volume rm <deployment>_postgres_data                    # irreversible
docker volume rm <deployment>_postgres_backups                 # irreversible

sudo rm -rf /srv/dolphin/<deployment-name>
docker image rm <app-image-digest> <postgres-image-digest> <nginx-image-digest>
docker system prune -f
```

On a host with several deployments (§9), every command above must name the one
deployment. `docker system prune -a` and `docker volume prune` do **not**
distinguish between customers — do not use them there.

Finally, revoke what outlived the host: the TLS certificate, the database
credentials, and the deployment's manifest key if it was deployment-specific.


## Release checklist

*(from `docs/ops/RELEASE_CHECKLIST.md`)*

Status values: `PASS`, `FAIL`, `BLOCKED_EXTERNAL`, `BLOCKED_DECISION`, or `NOT_RUN`. Every `PASS` needs dated evidence tied to one exact release reference.

Any `FAIL`, missing recovery point, unresolved P0/P1 defect, or unapproved data/credential/TLS decision is no-go.

### Release identity and ownership

- [ ] Exact commit/release artifact recorded and reviewed.
- [ ] Prior release artifact exists outside the live worktree.
- [ ] One approved `KARIZ_COMPOSE_PROJECT_NAME` is recorded and unchanged across current, restart, rollback, and prior-artifact commands; restore verification uses only its derived `-restore-verify` project.
- [ ] Release, database, security, business, rollback, and evidence owners named.
- [ ] Maintenance window, user notice, success window, and abort threshold approved.
- [ ] Known limitations and open decisions reviewed for this release.

### Repository gates

Run fresh from the exact release:

```powershell
git status --short
git diff --check
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py test --settings=config.test_settings -v 1
python manage.py spectacular --validate --fail-on-warn --settings=config.test_settings
python manage.py collectstatic --dry-run --noinput --settings=config.test_settings -v 0
python -m pip check
```

- [ ] Commands, exit codes, time, and reviewer recorded.
- [ ] No unexpected migration drift.
- [ ] Schema validates with active routes.
- [ ] Dependency/source/security scan evidence current; raw suspected secret values never copied into evidence.
- [ ] The exact-commit source-secret scan, locked-dependency advisory scan, per-image SBOM and vulnerability scans for the exact application, PostgreSQL, and Nginx digests, recorded Python build-base digest, and public TLS scan passed review through [SECURITY_SCANS.md](#security-scan-evidence-runbook); all evidence is digest-bound and sealed.
- [ ] Diff and staged-file review has no forbidden secret, database, backup, generated, or excluded archive artifact.

Repository gates do not prove PostgreSQL, containers, proxy, TLS, or browser behavior.

### Environment and security gates

- [ ] Protected `.env` exists through the approved secret process and is not printed or committed.
- [ ] Exact external backup volume, managed backup role/secret, explicit retention-days value, and disposable-restore tmpfs byte limit are approved; no other base service receives the backup password or mounts the backup volume.
- [ ] Required secret, host, HTTPS CSRF origin, database, timeout, HSTS, and proxy inputs pass strict production validation.
- [ ] Allowed hosts contain only `KARIZ_PUBLIC_HOST`; CSRF origins contain only `https://KARIZ_PUBLIC_HOST`, with no wildcard, dot prefix, sibling, port, slash, or extra entry.
- [ ] Approved certificate chain/key files are mounted read-only and pass the [TLS procedure](#tls-edge-procedure).
- [ ] Exact trusted proxy CIDR matches the approved one-proxy topology; no wildcard host or broad trust range.
- [ ] Trusted proxy validation rejects both IPv4 and IPv6 `/0` networks.
- [ ] HTTPS termination and forwarded-scheme behavior proved before secure session/CSRF smoke.
- [ ] HSTS value approved only after stable HTTPS proof; preload has separate explicit approval.
- [ ] Database is not published to the host or public network.
- [ ] Application runs as the non-root image user.
- [ ] Django/root default logs use the bounded safe formatter; application and edge logs omit query/body/header secrets and retain request-ID correlation.
- [ ] Nginx access logs reach container stdout, Nginx error logs reach stderr, and PostgreSQL statement, sampled/slow statement, parameter, connection, disconnection, and duration logging are disabled by the reviewed Compose command.
- [ ] Container log caps, external log retention, access, and alert path proved.

### Database and recovery gates

- [ ] Current-compatible write-stop, backup, and disposable restore passed before candidate protected-input replacement, image pull, database start, role/ACL work, or migration.
- [ ] Migration plan reviewed against the exact target database state.
- [ ] Every migration has application compatibility, data effect, lock/runtime, and recovery review.
- [ ] Native PostgreSQL zero/upgrade migration proof passed on an isolated engine.
- [ ] Fresh pre-migration custom-format backup exists under an exact protected sentinel root.
- [ ] Backup archive list and SHA-256 sidecar verify.
- [ ] Profile-only bundled backup job exited 0 with only the backup login, internal database network, and exact external backup volume.
- [ ] Backup login can complete `pg_dump` but cannot write rows, execute public routines, run DDL, inherit roles, or bypass row security.
- [ ] Standalone no-network restore service consumed the exact backup-volume archive read-only, received no database secret or target, and exited 0 after a tmpfs restore.
- [ ] Shared restore SQL proved all nine core tables, exact `accounts.0002`, `auditlog.0002`, and `sales.0010` heads, twelve true constraints, and two exact partial unique phone indexes without printing business rows.
- [ ] Live backup destination, schedule, retention, alert owner, recovery-time target, and recovery-point target approved.
- [ ] No in-place restore, business-database target, or volume deletion is part of the plan.

Use [BACKUP_RESTORE.md](#postgresql-backup-and-restore-verification). Guard/parser tests alone do not pass the real backup/restore gates.

### Container and edge gates

```powershell
docker compose config --quiet
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.restore-verify.yml --profile restore-verify config --quiet
python scripts/validate_release_images.py
docker compose pull
docker compose run --rm --no-deps web python manage.py check --deploy --settings=config.production_settings
docker compose up -d db
docker compose ps db
docker compose run --rm db-bootstrap
docker compose run --rm --no-deps migrate python manage.py migrate --plan
```

- [ ] Quiet Compose parse passed without exposing expanded values.
- [ ] All four exact reviewed digest references passed validation and every production service image pulled without a local build path.
- [ ] Production deploy check passed inside the image.
- [ ] Database health passed before migration.
- [ ] Migration plan matches review.
- [ ] Full Compose start completed; `db-bootstrap`, `migrate`, and `db-finalize` exited 0; `db`, `web`, and `nginx` became healthy.
- [ ] Normal Compose start did not run the profile-only `backup` service; the approved scheduler invokes it explicitly, and the atomic exact lock rejects overlapping runs.
- [ ] Standalone restore Compose had one no-network service, mounted only the backup volume read-only plus bounded tmpfs, and left no restore container after `--rm`.
- [ ] Runtime role can update mutable CRM rows and delete sessions, but cannot update/delete audit or history rows and cannot run DDL.
- [ ] Static files served through Nginx and unversioned asset paths revalidate instead of receiving a stale multi-day freshness lifetime.
- [ ] Nginx rate, timeout, request-ID, and safe error behavior proved.
- [ ] Base Compose mounted `# dolphin-write-stop: off`; override Compose mounted `# dolphin-write-stop: on` at `/etc/nginx/write-stop.conf`.
- [ ] With stop on, edge health `GET`/`HEAD` stayed live and safe-path `POST`/`PUT`/`PATCH`/`DELETE` each returned stable JSON `503` with matching header/body request IDs.
- [ ] With stop off again, the safe write probe no longer returned the edge write-stop response.
- [ ] Restart-policy and bounded-log behavior proved.

Do not use a Compose teardown that removes volumes or remove `postgres_data`/`static_data` during release testing.

### Initial access gate

- [ ] Existing active Platform Admin confirmed, or first-install bootstrap explicitly approved.

For a first installation only:

```powershell
$approvedUsername = Read-Host 'Approved username'
docker compose exec web python manage.py bootstrap_platform_admin --username $approvedUsername
```

- [ ] Password entered only at the two hidden prompts; no password argument, shell history value, or ticket copy.
- [ ] Command success and `user.platform_admin_bootstrapped` audit event verified.
- [ ] Created CRM account is not Django staff/superuser.
- [ ] Second bootstrap refusal verified by command behavior/tests, not by creating another account.

### Health, authorization, and product gates

- [ ] Nginx `/health/live/` passed through the deployed edge.
- [ ] Application `/api/v1/health/live/` passed.
- [ ] Database-backed `/api/v1/health/ready/` passed.
- [ ] HTTPS, certificate, fixed-host redirect, secure cookies, CSRF, HSTS, old-protocol denial, and scanner behavior passed through the real public path.
- [ ] Login/logout/inactive denial passed.
- [ ] Sales Agent, Sales Manager, Company IT, and Platform Admin list/detail/write/action/filter scope passed with approved non-production fixtures.
- [ ] Customer/phone uniqueness, Lead assignment/history, Interaction append-only, positive Product, Sale create/cancel, and audit critical paths passed.
- [ ] Report JSON/XLSX scope, formulas, non-enumerating Product filter, exact money text, parity, cache, and download passed.
- [ ] Persian/RTL root/admin, Dolphin brand, static assets, target viewports, and clean browser console/network passed.
- [ ] Capacity/load target passed on production-shaped infrastructure through the bounded read-only procedure in [LOAD_TEST.md](#read-only-readiness-load-check), or through one separately approved exact tool and contract, with external resource and abort evidence.

### Rollback and incident gates

Run this exact reversible edge drill only on the approved target. Use the no-body safe probes from [INCIDENT_RESPONSE.md](#incident-response), not a business route:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
docker compose -f compose.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml exec -T nginx grep -F '# dolphin-write-stop: off' /etc/nginx/write-stop.conf
```

- [ ] Prior application artifact can be selected without live Git reset or file overwrite.
- [ ] Application-only rollback compatibility is explicit.
- [ ] Application-only rollback was rehearsed with the explicit stable project name, protected environment, write-stop proof, prior digest pull, static refresh, and web-only recreate sequence.
- [ ] Edge/config-only rollback was rehearsed from a complete prior reviewed artifact while recreating only Nginx and retaining write-stop until edge acceptance.
- [ ] Safe full-stack stop/restart uses the exact write-stop, fresh backup/restore, `nginx` then `web` then `db` stop order, reverse start order, health waits, and no `down` or volume removal.
- [ ] Any migration rollback has exact target, reverse/data review, recovery point, owners, and acceptance plan.
- [ ] New-database recovery and cutover path approved; no in-place restore.
- [ ] Edge write-stop owner, UTC on/off times, reason, state output, safe probe request IDs, and reopen approval recorded.
- [ ] Credential, database outage, bad deploy/migration, backup failure, and audit/log incident paths have named owners.
- [ ] Rollback and incident tabletop completed against [ROLLBACK.md](#rollback-procedure) and [INCIDENT_RESPONSE.md](#incident-response).

### Evidence result

Record each gate under one of these proof classes:

| Proof class | Examples | Can repository-only work pass it? |
|---|---|---|
| Repository | tests, schema, drift, source/config review | Yes |
| PostgreSQL | migrations, constraints, backup, restore | No |
| Docker/Nginx | digest pull, boot, health, static, rate, restart, logs | No |
| TLS | hostname, certificate, forwarded scheme, HSTS | No |
| Browser/UAT | role flows, CSRF, RTL, brand, console/network | No |
| Operations | schedule, alerts, recovery targets, ownership, drill | No |

Final decision must name every blocked or not-run external gate. Allowed claim before those gates pass: `production candidate; external verification pending` only after all repository and decision gates pass. Otherwise claim `work in progress`.

Use [DEPLOYMENT.md](#deployment-procedure) for execution. Use [ROLLBACK.md](#rollback-procedure) and [INCIDENT_RESPONSE.md](#incident-response) for abort and recovery.


## Rollback procedure

*(from `docs/ops/ROLLBACK.md`)*

Status: decision-safe procedure complete; immutable release values and live recovery proof remain external.

This guide never deletes a volume, rewrites the live worktree, reverses a migration by guess, or restores over a business database.

### Required rollback inputs

Before release, record:

- current and prior exact release references;
- a separately stored prior release artifact or image;
- the unchanged approved `KARIZ_COMPOSE_PROJECT_NAME` and protected environment path;
- current and prior reviewed Compose, write-stop, and Nginx configuration artifacts;
- migration plan and compatibility review;
- fresh verified pre-migration backup and checksum;
- recovery and cutover decision owners;
- health, role-scope, and business-flow acceptance tests.

The current [Compose definition](../../compose.yml) requires one immutable application image digest for both `migrate` and `web`; it has no production local-build path. Do not reset/rewrite the live worktree, use broad checkout, or replace live files as a rollback mechanism. Prepare and review the prior digest through the approved artifact system first.

### Triage without mutation

Capture the release reference, request IDs, UTC time window, affected routes, and observed status. Inspect state without changing schema or data:

```powershell
docker compose ps --all
docker compose logs --no-color --tail 200 db-bootstrap migrate db-finalize web nginx db
docker compose run --rm --no-deps migrate python manage.py showmigrations --plan
```

Keep raw logs restricted. Do not paste credentials, environment output, request bodies, customer data, or audit rows into tickets.

### Choose one recovery path

#### Application-only rollback

Use this only when review proves the deployed schema is backward-compatible with the prior application. First enable and prove the edge write-stop. Through the approved protected-secret process, atomically replace only `KARIZ_APP_IMAGE` in the durable deployment input with the separately recorded prior digest. Do not use a broad text rewrite, display the protected file, or rely on a temporary shell value as the rollback record. Load the same prior digest plus the other three unchanged reviewed image references into the command process without printing them, then validate and pull:

```powershell
$approvedProjectName = Read-Host 'Unchanged approved Compose project name'
$approvedProtectedEnv = (Resolve-Path (Read-Host 'Approved protected environment file')).Path
$currentCompose = (Resolve-Path '.\compose.yml').Path
$currentWriteStop = (Resolve-Path '.\compose.write-stop.yml').Path
$env:KARIZ_APP_IMAGE = Read-Host 'Prior approved application repository@sha256 digest'
python scripts/validate_release_images.py
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose config --quiet
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose pull web migrate
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose stop --timeout 30 nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose run --rm --no-deps migrate python manage.py collectstatic --clear --noinput
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose up -d --no-build --no-deps --force-recreate --wait web
if ($LASTEXITCODE -ne 0) { throw 'Prior application failed its health gate.' }
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose ps web
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
```

The explicit one-off command overrides the `migrate` service command and runs only `collectstatic` from the prior image. Stopping Nginx first prevents clients from seeing a half-regenerated shared static volume. If static collection or web health fails, keep Nginx stopped and writes closed; regenerate from the reviewed current or prior image according to the rollback decision. Do not run a schema migration during an application-only rollback.

After prior-image web health, start Nginx with the write-stop override, prove static files and business smoke, and reopen writes only through the approved write-stop procedure. In a new shell with no image override, run quiet Compose validation and prove the durable protected input still selects the prior application release. Record the protected-input change, compatibility review, prior digest, pull, static regeneration, recreate, health, and smoke. This path does not alter the database volume.

#### Edge/config-only rollback

Use this when review isolates the fault to Compose-controlled Nginx image or edge configuration and proves that the prior edge artifact still matches the running application, certificates, public host, and Compose schema. Keep the current application and database images unchanged. Obtain the prior release directory from the approved artifact store; do not rewrite the live worktree or copy one loose configuration file over it.

First enable and prove write-stop with the current reviewed configuration by running the first two Compose commands below. If the edge image also changes, then atomically restore the prior `KARIZ_NGINX_IMAGE` in the protected deployment input. Validate and select the complete prior Compose plus write-stop pair under the same stable project name with the remaining commands:

```powershell
$approvedProjectName = Read-Host 'Unchanged approved Compose project name'
$approvedProtectedEnv = (Resolve-Path (Read-Host 'Approved protected environment file')).Path
$currentCompose = (Resolve-Path '.\compose.yml').Path
$currentWriteStop = (Resolve-Path '.\compose.write-stop.yml').Path
$priorReleaseRoot = (Resolve-Path (Read-Host 'Approved prior release artifact directory')).Path
$priorCompose = Join-Path $priorReleaseRoot 'compose.yml'
$priorWriteStop = Join-Path $priorReleaseRoot 'compose.write-stop.yml'
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose -f $priorWriteStop config --quiet
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose pull nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose -f $priorWriteStop up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose -f $priorWriteStop exec -T nginx grep -F '# dolphin-write-stop: on' /etc/nginx/write-stop.conf
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose ps nginx web db
```

Prove edge liveness, HTTPS/TLS, request IDs, safe errors, static revalidation, and routing while writes stay closed. After owner approval, reopen writes only from the prior base Compose file and prove its off mount:

```powershell
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose exec -T nginx grep -F '# dolphin-write-stop: off' /etc/nginx/write-stop.conf
```

Record both artifact paths, their release reference, the stable project name, protected-input change if any, and all health/smoke evidence. These commands recreate only `nginx`; they do not recreate `web`, run migrations, or alter database/static volumes. If the prior configuration changes a database or application contract, this path is forbidden; choose a separately reviewed application or database recovery plan.

#### Forward fix

Prefer a reviewed forward fix when the current schema is valid and the defect is isolated in application or configuration code. Run the full repository, image, migration-plan, backup, health, and smoke gates again. Do not patch files inside a running container.

#### Migration rollback

Migration rollback needs all of these before any schema command:

1. exact target migration and dependency graph;
2. review of forward and reverse migration code, including data migrations;
3. proof that the target application can read the target schema;
4. proof that no accepted business data would be lost or reinterpreted;
5. fresh verified recovery point and disposable restore result;
6. database owner, business owner, and rollback approver sign-off;
7. maintenance/write-stop path and post-change acceptance plan.

Generate reverse SQL for review only:

```powershell
$appLabel = Read-Host 'Reviewed app label'
$migrationName = Read-Host 'Reviewed migration name'
docker compose run --rm --no-deps migrate python manage.py sqlmigrate $appLabel $migrationName --backwards
```

This command prints a plan; it does not authorize execution. This guide intentionally gives no generic reverse-`migrate` command. The approved change record must name the exact target and recovery point. If compatibility or data effect is unclear, do not reverse the migration.

#### Database recovery

Use database recovery when schema/data cannot be safely repaired forward. Follow [BACKUP_RESTORE.md](#postgresql-backup-and-restore-verification): verify checksum, restore into a new recovery database, validate ownership and core tables, run release-compatible migrations only after review, perform role/business/audit checks, and obtain owner approval before routing the application to it.

Never restore into the damaged database in place. Keep the prior database and release intact until acceptance and rollback windows close.

### Validation after rollback

Repeat all applicable deployment gates:

- `migrate` job exit code 0 for the selected release;
- application liveness and database readiness;
- Nginx liveness and routing;
- login/logout and CSRF;
- one scoped read per fixed CRM role;
- Customer, Lead assignment, Product, Sale, audit, report, and XLSX critical paths using approved fixtures;
- static, Persian/RTL, Dolphin brand, browser console/network, and HTTPS checks;
- backup job and alert path.

Keep the incident open if any gate lacks proof.

### Forbidden rollback actions

- no Compose teardown that removes volumes, database-directory deletion, or broad filesystem delete;
- no live-worktree reset, broad checkout, or history rewrite on the live host;
- no manual edit of applied migration files or migration-table rows;
- no direct production SQL repair without an exact reviewed change and recovery point;
- no in-place restore over the current business database;
- no claim that a rollback worked from process liveness alone.

Use [INCIDENT_RESPONSE.md](#incident-response) for ownership, evidence, and incident closure.


## Security scan evidence runbook

*(from `docs/ops/SECURITY_SCANS.md`)*

Status: repository procedure complete; registry, advisory-service, container-engine, public-network, and reviewer proof remains external.

This procedure creates evidence for one immutable source commit, all three exact runtime images, and the exact Python build-base digest. It covers source-secret detection, the locked Python dependency set, per-image SBOMs and vulnerabilities for the application, PostgreSQL, and Nginx, the recorded Python base input, and the real public TLS endpoint. A completed command is not a passing review. The security owner must review every report and record the result against the same release reference.

### Trust and evidence boundary

- Run this from a clean checkout at the approved release commit on an isolated evidence host. Do not run the image scanners through a production container engine.
- Use only scanner images whose exact released tool version was reviewed and resolved to an immutable registry digest. `latest`, branch, tag-only, or locally named references are forbidden.
- Use the exact deployable `KARIZ_APP_IMAGE`, `KARIZ_POSTGRES_IMAGE`, and `KARIZ_NGINX_IMAGE` `repository@sha256:digest` references. Record the exact `PYTHON_BASE_IMAGE` digest from the approved build record. Do not scan a local build tag as release proof.
- Pre-create one approved, encrypted, restricted evidence root outside the repository, checkout parent, temporary directories, and shared or synchronized user folders. The commands create one new child and never overwrite a prior run.
- Registry authentication, when needed, must already exist in the host's approved credential helper. Never put a registry password or token in a command, environment variable, report, or transcript.
- The source report is a deliberately reduced report. It stores rule, repository path, line range, and commit only. It never stores the matched line or suspected value.
- SBOM, package, file-path, certificate, and vulnerability data can still be sensitive. Keep all output restricted even when no finding exists.
- The SBOM scanner receives the local container-engine socket. That socket is equivalent to control of that isolated engine. Approve the scanner image first, keep production workloads off that engine, and remove host access after the run.

Before the run, record the evidence owner, security reviewer, retention class and end condition, approved external TLS client label, approved release commit, three exact runtime image references, exact Python build-base reference, approved source-to-image build record, and all five exact scanner image references in the release record. Do not record secrets.

### Exact inputs and protected run directory

Open a new PowerShell session at the repository root. Enter only non-secret identifiers at the prompts.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath '.').Path
$approvedReleaseCommit = (Read-Host 'Approved 40-hex release commit').Trim().ToLowerInvariant()
$appImage = (Read-Host 'Approved application image repository@sha256:digest').Trim()
$postgresImage = (Read-Host 'Approved PostgreSQL image repository@sha256:digest').Trim()
$nginxImage = (Read-Host 'Approved Nginx image repository@sha256:digest').Trim()
$pythonBaseImage = (Read-Host 'Approved Python build-base repository@sha256:digest').Trim()
$gitleaksImage = (Read-Host 'Approved Gitleaks image repository@sha256:digest').Trim()
$pipAuditImage = (Read-Host 'Approved pip-audit image repository@sha256:digest').Trim()
$syftImage = (Read-Host 'Approved Syft image repository@sha256:digest').Trim()
$grypeImage = (Read-Host 'Approved Grype image repository@sha256:digest').Trim()
$testsslImage = (Read-Host 'Approved testssl.sh image repository@sha256:digest').Trim()
$publicHost = (Read-Host 'Approved lowercase public hostname').Trim()
$externalClientLabel = (Read-Host 'Approved non-secret external TLS client label').Trim()
$evidenceRootInput = (Read-Host 'Approved restricted external evidence root').Trim()

if ($approvedReleaseCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Release commit must be exactly 40 lowercase hexadecimal characters.'
}

$actualReleaseCommit = (git rev-parse --verify HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $actualReleaseCommit -ne $approvedReleaseCommit) {
    throw 'Checkout does not match the approved release commit.'
}

$sourceState = @(git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $sourceState.Count -ne 0) {
    throw 'Release checkout must be clean, including untracked files.'
}

$pinnedImagePattern = '^[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9][a-z0-9._-]*)+@sha256:[a-f0-9]{64}$'
$runtimeImages = [ordered]@{
    application = $appImage
    postgresql = $postgresImage
    nginx = $nginxImage
}
$scannerImages = [ordered]@{
    gitleaks = $gitleaksImage
    pip_audit = $pipAuditImage
    syft = $syftImage
    grype = $grypeImage
    testssl = $testsslImage
}

foreach ($value in @($runtimeImages.Values) + @($pythonBaseImage) + @($scannerImages.Values)) {
    if ($value -notmatch $pinnedImagePattern) {
        throw 'Every runtime, build-base, and scanner image must use one exact repository@sha256 registry digest.'
    }
}

if ($publicHost.Length -gt 253 -or $publicHost -notmatch '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$') {
    throw 'Public host must be one lowercase DNS hostname with no scheme, port, path, or wildcard.'
}
if ([string]::IsNullOrWhiteSpace($externalClientLabel) -or $externalClientLabel.Length -gt 128) {
    throw 'External client label is required and must be at most 128 characters.'
}

$evidenceRoot = (Resolve-Path -LiteralPath $evidenceRootInput).Path
$evidenceRootItem = Get-Item -Force -LiteralPath $evidenceRoot
if (-not $evidenceRootItem.PSIsContainer -or ($evidenceRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Evidence root must be a real directory, not a link or reparse point.'
}

$repoPrefix = $repoRoot.TrimEnd('\') + '\'
$repoParent = (Split-Path -Parent $repoRoot).TrimEnd('\')
$repoParentPrefix = $repoParent + '\'
$evidencePrefix = $evidenceRoot.TrimEnd('\') + '\'
if (
    $evidenceRoot -eq $repoRoot -or
    $evidenceRoot -eq $repoParent -or
    $evidencePrefix.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $evidencePrefix.StartsWith($repoParentPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $repoPrefix.StartsWith($evidencePrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw 'Evidence root must be outside the repository and its parent path.'
}

$appDigest = ($appImage -split '@sha256:', 2)[1]
$runStartedUtc = [DateTime]::UtcNow.ToString('o')
$runLeaf = '{0}-{1}-{2}' -f [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'), $approvedReleaseCommit, $appDigest.Substring(0, 16)
$evidenceDir = Join-Path $evidenceRoot $runLeaf
if (Test-Path -LiteralPath $evidenceDir) {
    throw 'Evidence run directory already exists.'
}
New-Item -ItemType Directory -Path $evidenceDir | Out-Null
Set-Content -LiteralPath (Join-Path $evidenceDir 'run-state.txt') -Value 'INCOMPLETE' -Encoding utf8

$requirementsSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repoRoot 'requirements.txt')).Hash.ToLowerInvariant()
$tlsTarget = "${publicHost}:443"
```

Stop if the evidence owner has not checked the inherited access controls on the new directory. Only the evidence custodian, security reviewer, and named release owner may read it; only the evidence custodian may modify it.

### Pull and prove immutable images

Pull each exact reference for the production target. The registry validates the requested manifest digest. The later local check rejects any runtime, build-base, or scanner reference that is not present under that digest.

```powershell
$allImages = @($runtimeImages.Values) + @($pythonBaseImage) + @($scannerImages.Values)
foreach ($image in $allImages) {
    docker pull --platform linux/amd64 $image
    if ($LASTEXITCODE -ne 0) {
        throw 'Exact image pull failed.'
    }
}

function Assert-LocalDigest([string]$image) {
    $digest = ($image -split '@', 2)[1]
    $repoDigests = @(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' $image)
    if ($LASTEXITCODE -ne 0 -or -not ($repoDigests | Where-Object { $_.Trim().EndsWith("@$digest", [StringComparison]::OrdinalIgnoreCase) })) {
        throw 'Local image does not expose the approved registry digest.'
    }
}

foreach ($image in $allImages) {
    Assert-LocalDigest $image
}

$imagePlatforms = [ordered]@{}
foreach ($entry in $runtimeImages.GetEnumerator()) {
    $platform = (docker image inspect --format '{{.Os}}/{{.Architecture}}' $entry.Value).Trim()
    if ($LASTEXITCODE -ne 0 -or $platform -ne 'linux/amd64') {
        throw 'A runtime image is not the approved linux/amd64 target.'
    }
    $imagePlatforms[$entry.Key] = $platform
}
$pythonBasePlatform = (docker image inspect --format '{{.Os}}/{{.Architecture}}' $pythonBaseImage).Trim()
if ($LASTEXITCODE -ne 0 -or $pythonBasePlatform -ne 'linux/amd64') {
    throw 'Python build-base image is not the approved linux/amd64 target.'
}
```

Record runtime tool version output from the already digest-pinned scanner images. The approved pip-audit scanner image must contain its named tool and Python entry point; do not install a scanner during this release run.

```powershell
$gitleaksVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $gitleaksImage --version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitleaksVersion)) { throw 'Gitleaks version probe failed.' }

$pipAuditVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --entrypoint python $pipAuditImage -m pip_audit --version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pipAuditVersion)) { throw 'pip-audit version probe failed.' }

$syftVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $syftImage version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($syftVersion)) { throw 'Syft version probe failed.' }

$grypeVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $grypeImage version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($grypeVersion)) { throw 'Grype version probe failed.' }

$testsslVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $testsslImage --version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($testsslVersion)) { throw 'testssl.sh version probe failed.' }

$toolVersions = [ordered]@{
    gitleaks = $gitleaksVersion
    pip_audit = $pipAuditVersion
    syft = $syftVersion
    grype = $grypeVersion
    testssl = $testsslVersion
}
$toolVersions | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $evidenceDir 'tool-versions.json') -Encoding utf8
```

### Source-secret scan

The clean commit is the source-artifact binding. The scan covers reachable Git history, including the approved commit. Do not add a release-time baseline or allowlist. Any exception must already be a reviewed source-controlled scanner rule.

Create a report template that cannot emit the matching line or value:

```powershell
$safeGitleaksTemplate = @'
[
{{- range $index, $finding := . }}{{ if $index }},{{ end }}
{"rule_id":{{ quote .RuleID }},"file":{{ quote .File }},"start_line":{{ .StartLine }},"end_line":{{ .EndLine }},"commit":{{ quote .Commit }}}
{{- end }}
]
'@
$gitleaksTemplatePath = Join-Path $evidenceDir 'gitleaks-safe-report.tmpl'
Set-Content -LiteralPath $gitleaksTemplatePath -Value $safeGitleaksTemplate -Encoding ascii

docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=64m `
    --mount "type=bind,source=$repoRoot,target=/src,readonly" `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    $gitleaksImage git /src `
    --no-banner --no-color --redact=100 `
    --report-format template `
    --report-template /evidence/gitleaks-safe-report.tmpl `
    --report-path /evidence/source-secrets.redacted.json
$gitleaksExit = $LASTEXITCODE

if ($gitleaksExit -notin @(0, 1)) { throw 'Gitleaks execution failed.' }
$null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir 'source-secrets.redacted.json') | ConvertFrom-Json
```

Exit `0` means no finding under this scanner version and rule set. Exit `1` is a no-go finding until the security owner investigates. Never copy the suspected value into a ticket, message, exception list, or release record. Preserve only the reduced report and refer to its file and line under restricted access.

### Locked Python dependency scan

This scan binds to the SHA-256 of the exact `requirements.txt` in the approved commit. `--require-hashes` and `--disable-pip` prevent dependency resolution or package installation. The advisory service is live external state, so its name and the run time are part of the evidence; a later release decision may require a fresh run.

```powershell
$pipAuditCache = Join-Path $evidenceDir 'pip-audit-cache'
New-Item -ItemType Directory -Path $pipAuditCache | Out-Null

docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=128m `
    --mount "type=bind,source=$repoRoot,target=/src,readonly" `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    --entrypoint python `
    $pipAuditImage -m pip_audit `
    --require-hashes --disable-pip --strict `
    --vulnerability-service pypi `
    --progress-spinner off --desc off --aliases on `
    --cache-dir /evidence/pip-audit-cache `
    --format json --output /evidence/python-dependencies.json `
    --requirement /src/requirements.txt
$pipAuditExit = $LASTEXITCODE

if ($pipAuditExit -notin @(0, 1)) { throw 'pip-audit execution failed.' }
$null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir 'python-dependencies.json') | ConvertFrom-Json
```

Exit `0` means no known vulnerability was returned at that time. Exit `1` is no-go pending report review; it can mean a finding or a scan failure, so the report and command state must both be checked. Do not suppress a vulnerability ID in this command. A risk acceptance belongs in the separately approved release record.

### Exact runtime-image SBOMs

The local digest proof above binds each Docker source to its exact runtime manifest. Syft scans each squashed deployable filesystem, not deleted content from older layers. It writes a CycloneDX release SBOM and a native report for each runtime-image vulnerability scan. The application filesystem includes its Python base layers; the separately recorded base digest must still match the approved source-to-image build record.

```powershell
$syftExitCodes = [ordered]@{}
foreach ($entry in $runtimeImages.GetEnumerator()) {
    $artifactName = $entry.Key
    $cycloneContainerPath = "/evidence/${artifactName}-sbom.cdx.json"
    $syftContainerPath = "/evidence/${artifactName}-sbom.syft.json"
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
        --tmpfs /tmp:rw,noexec,nosuid,size=128m `
        --volume /var/run/docker.sock:/var/run/docker.sock `
        --mount "type=bind,source=$evidenceDir,target=/evidence" `
        $syftImage "docker:$($entry.Value)" --scope squashed `
        --output "cyclonedx-json=$cycloneContainerPath" `
        --output "syft-json=$syftContainerPath"
    $syftExitCodes[$artifactName] = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'Runtime-image SBOM generation failed.' }
    $null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir "${artifactName}-sbom.cdx.json") | ConvertFrom-Json
    $null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir "${artifactName}-sbom.syft.json") | ConvertFrom-Json
}
```

An SBOM is inventory evidence, not vulnerability or license approval. The reviewer must confirm that each report identifies the expected exact image source and contains the expected operating-system and application package families before accepting it.

### Exact runtime-image vulnerability scans

Update the Grype database into this run directory, capture its schema, build time, checksum, and status, then disable updates for the actual scans. Each scan consumes the SBOM made from one exact runtime image. It reports fixed and unfixed findings; do not use `--only-fixed` and do not provide ignore or VEX input here.

```powershell
$grypeDbDir = Join-Path $evidenceDir 'grype-db'
New-Item -ItemType Directory -Path $grypeDbDir | Out-Null

docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=128m `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    --env GRYPE_DB_CACHE_DIR=/evidence/grype-db `
    --env GRYPE_CHECK_FOR_APP_UPDATE=false `
    $grypeImage db update
if ($LASTEXITCODE -ne 0) { throw 'Grype database update failed.' }

$grypeDbStatus = @(
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
        --tmpfs /tmp:rw,noexec,nosuid,size=64m `
        --mount "type=bind,source=$evidenceDir,target=/evidence" `
        --env GRYPE_DB_CACHE_DIR=/evidence/grype-db `
        --env GRYPE_DB_AUTO_UPDATE=false `
        --env GRYPE_CHECK_FOR_APP_UPDATE=false `
        $grypeImage db status
) -join "`n"
if ($LASTEXITCODE -ne 0 -or $grypeDbStatus -notmatch '(?im)^Status:\s+valid\s*$') {
    throw 'Grype database is not valid.'
}
Set-Content -LiteralPath (Join-Path $evidenceDir 'grype-db-status.txt') -Value $grypeDbStatus -Encoding utf8

$grypeExitCodes = [ordered]@{}
foreach ($entry in $runtimeImages.GetEnumerator()) {
    $artifactName = $entry.Key
    $sbomContainerPath = "/evidence/${artifactName}-sbom.syft.json"
    $vulnerabilityContainerPath = "/evidence/${artifactName}-vulnerabilities.json"
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
        --tmpfs /tmp:rw,noexec,nosuid,size=128m `
        --mount "type=bind,source=$evidenceDir,target=/evidence" `
        --env GRYPE_DB_CACHE_DIR=/evidence/grype-db `
        --env GRYPE_DB_AUTO_UPDATE=false `
        --env GRYPE_CHECK_FOR_APP_UPDATE=false `
        $grypeImage "sbom:$sbomContainerPath" `
        --output json --file $vulnerabilityContainerPath `
        --fail-on high
    $grypeExitCodes[$artifactName] = $LASTEXITCODE
    $null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir "${artifactName}-vulnerabilities.json") | ConvertFrom-Json
}
```

For each runtime image, exit `0` means the pinned Grype version did not cross the High threshold. Any nonzero exit is no-go for that image until the reviewer uses that exact pinned version's documented exit contract and the matching parsed report to distinguish a threshold match from execution failure. This avoids treating a changed scanner exit-code contract as a pass. Exit `0` does not waive lower-severity review, false-negative review, or the need to refresh an old vulnerability database.

### Real public TLS scan

Run this section only from the approved external client, outside the target host and internal proxy path. The hostname must resolve through public DNS and the route must terminate at the same edge users reach. The scanner gets no certificate private key, cookie, account, header, or client credential.

```powershell
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=128m `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    $testsslImage `
    --quiet --warnings batch --color 0 `
    --jsonfile /evidence/tls-public.json `
    --logfile /evidence/tls-public.log `
    $tlsTarget
$testsslExit = $LASTEXITCODE

if (-not (Test-Path -LiteralPath (Join-Path $evidenceDir 'tls-public.json'))) {
    throw 'TLS scanner did not create JSON evidence.'
}
$null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir 'tls-public.json') | ConvertFrom-Json
```

A TLS scanner exit code alone is not acceptance. The reviewer must confirm the observed hostname/IP path, certificate name and chain, validity, TLS 1.0/1.1 denial, TLS 1.2/1.3 support, cipher/protocol findings, HSTS through HTTPS, and absence of a release-blocking result. Record the scanner exit code even when the JSON is valid. Browser, renewal, redirect, secure-cookie, CSRF, and port-exposure proof remains required by [TLS.md](#tls-edge-procedure).

### Bind, seal, and review the evidence

Write factual run metadata from this PowerShell session. `COMPLETE_REVIEW_REQUIRED` means every expected artifact exists and parses; it never means that findings passed review.

```powershell
$runFinishedUtc = [DateTime]::UtcNow.ToString('o')
$metadata = [ordered]@{
    schema_version = 2
    state = 'COMPLETE_REVIEW_REQUIRED'
    release_commit = $approvedReleaseCommit
    requirements_sha256 = $requirementsSha256
    runtime_images = $runtimeImages
    runtime_platforms = $imagePlatforms
    python_build_base_image = $pythonBaseImage
    python_build_base_platform = $pythonBasePlatform
    scanner_images = $scannerImages
    scanner_versions = $toolVersions
    dependency_advisory_service = 'pypi'
    grype_fail_on = 'high'
    public_tls_host = $publicHost
    external_tls_client_label = $externalClientLabel
    run_started_utc = $runStartedUtc
    run_finished_utc = $runFinishedUtc
    exit_codes = [ordered]@{
        gitleaks = $gitleaksExit
        pip_audit = $pipAuditExit
        syft = $syftExitCodes
        grype = $grypeExitCodes
        testssl = $testsslExit
    }
}
$metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceDir 'run-metadata.json') -Encoding utf8
Set-Content -LiteralPath (Join-Path $evidenceDir 'run-state.txt') -Value 'COMPLETE_REVIEW_REQUIRED' -Encoding utf8

$reparseEntries = @(Get-ChildItem -Force -Recurse -LiteralPath $evidenceDir | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
if ($reparseEntries.Count -ne 0) {
    throw 'Evidence tree contains a link or reparse point.'
}

$integrityPath = Join-Path $evidenceDir 'integrity.sha256'
$integrityAnchorPath = Join-Path $evidenceDir 'integrity.sha256.anchor'
$evidenceFiles = @(
    Get-ChildItem -Force -Recurse -File -LiteralPath $evidenceDir |
        Where-Object { $_.FullName -notin @($integrityPath, $integrityAnchorPath) } |
        Sort-Object FullName
)
$integrityLines = foreach ($file in $evidenceFiles) {
    $relativePath = $file.FullName.Substring($evidenceDir.Length + 1).Replace('\', '/')
    $fileHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    '{0}  {1}' -f $fileHash, $relativePath
}
$integrityLines | Set-Content -LiteralPath $integrityPath -Encoding ascii
$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $integrityPath).Hash.ToLowerInvariant()
Set-Content -LiteralPath $integrityAnchorPath -Value ("$manifestHash  integrity.sha256") -Encoding ascii

Write-Output "Record this out-of-band evidence anchor in the approved release record: sha256:$manifestHash"
```

The evidence custodian must copy only the final manifest SHA-256 to the separately controlled release record or write-once evidence index. The in-directory anchor is convenient but is not an independent trust anchor. Do not modify, rename, append to, or regenerate any file after the manifest is sealed; a rerun gets a new directory and time.

Verify the sealed directory at review, transfer, incident use, and retention expiry. Supply the anchor from the separately controlled release record, not from `integrity.sha256.anchor`:

```powershell
$sealedEvidenceDir = (Resolve-Path -LiteralPath (Read-Host 'Sealed evidence run directory')).Path
$approvedManifestHash = (Read-Host 'Out-of-band approved integrity.sha256 SHA-256').Trim().ToLowerInvariant()
if ($approvedManifestHash -notmatch '^[0-9a-f]{64}$') { throw 'Approved manifest hash is invalid.' }

$sealedPrefix = $sealedEvidenceDir.TrimEnd('\') + '\'
$sealedManifest = Join-Path $sealedEvidenceDir 'integrity.sha256'
$actualManifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sealedManifest).Hash.ToLowerInvariant()
if ($actualManifestHash -ne $approvedManifestHash) { throw 'Evidence manifest hash mismatch.' }

$manifestPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($line in Get-Content -LiteralPath $sealedManifest) {
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Malformed integrity manifest row.' }
    $expectedHash = $Matches[1]
    $relativePath = $Matches[2]
    if ([IO.Path]::IsPathRooted($relativePath) -or $relativePath -match '(^|/)\.\.(/|$)') {
        throw 'Unsafe integrity manifest path.'
    }
    if (-not $manifestPaths.Add($relativePath)) { throw 'Duplicate integrity manifest path.' }
    $candidatePath = (Resolve-Path -LiteralPath (Join-Path $sealedEvidenceDir $relativePath.Replace('/', '\'))).Path
    if (-not $candidatePath.StartsWith($sealedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Integrity manifest path escaped the evidence directory.'
    }
    $candidateItem = Get-Item -Force -LiteralPath $candidatePath
    if ($candidateItem.PSIsContainer -or ($candidateItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Integrity manifest target is not one regular file.'
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidatePath).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw "Evidence file hash mismatch: $relativePath" }
}

$unexpectedLinks = @(Get-ChildItem -Force -Recurse -LiteralPath $sealedEvidenceDir | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
if ($unexpectedLinks.Count -ne 0) { throw 'Sealed evidence tree contains a link or reparse point.' }

$sealedFiles = @(
    Get-ChildItem -Force -Recurse -File -LiteralPath $sealedEvidenceDir |
        Where-Object { $_.FullName -notin @($sealedManifest, (Join-Path $sealedEvidenceDir 'integrity.sha256.anchor')) }
)
if ($sealedFiles.Count -ne $manifestPaths.Count) { throw 'Sealed evidence file set changed.' }
foreach ($file in $sealedFiles) {
    $relativePath = $file.FullName.Substring($sealedEvidenceDir.Length + 1).Replace('\', '/')
    if (-not $manifestPaths.Contains($relativePath)) { throw 'Sealed evidence contains an unlisted file.' }
}
```

### Retention, access, and release result

- Keep the sealed run under the approved security-evidence retention class. The end condition must cover the release lifetime, rollback window, vulnerability remediation, audit requirement, and any legal or incident hold. A calendar date alone must not shorten an active hold.
- Encrypt evidence at rest and in transfer. Use named access, least privilege, multi-factor access where available, and access logging. Do not publish reports or use unrestricted ticket attachments or links.
- Review access at release close and at each retention review. Remove access when an owner leaves the role. Preserve access-log and integrity-anchor history separately from the run directory.
- Do not edit a finding out of a report. Store remediation, false-positive analysis, expiry, compensating control, owner, and approval as a separate record tied to the release commit, affected runtime digest, report hash, finding ID, and evidence anchor.
- Do not delete evidence while a release, rollback, investigation, audit, or hold still needs it. At approved expiry, the evidence custodian must verify the out-of-band anchor, record disposal approval, and use the storage system's exact-object disposal workflow. This runbook provides no broad or recursive delete command.
- Any missing report, parse failure, unexpected scanner exit, invalid or stale Grype database, unreviewed result, High/Critical image finding, secret finding, vulnerable locked dependency, or release-blocking TLS result is no-go.
- A passing record needs the exact commit, all three runtime digests, Python build-base digest, approved source-to-image build record, exact scanner digests and observed versions, requirements hash, Grype database status/checksum, public hostname and external-client label, UTC times, per-image exit codes and report hashes, out-of-band evidence anchor, reviewer, and disposition of every finding.

Repository parsing cannot close this gate. Only execution on the approved scan host against the exact release artifact and real public endpoint creates external scan proof.


## Target site survey (phase P0R.1)

*(from `docs/ops/TARGET_SITE_SURVEY.md`)*

Fill this in before any deployment design is finalised. Every field is
currently **unanswered**; the reported values in `DOLPHIN_PROJECT_HANDOFF.md` §10
are customer claims, not verified facts, and must not be designed against.

This phase is `BLOCKED_EXTERNAL`: it needs answers from the customer and the
infrastructure owner. It does not block P1, P2, or P4, but P14 and P15 cannot
start without it.

**Never paste a password, key, certificate, or connection string into this
file.** Record hostnames, versions, models, and owners only. If a command's
output contains a licence key or serial number, redact it before sharing.

### 1. Host operating system — the single most important item

The customer reports "Windows Server 2008" on the Parand host. That phrase is
ambiguous and has three very different meanings. Resolve it first.

Run on the target host and paste the output:

```text
winver
```

```text
systeminfo
```

If PowerShell is available, this is more precise and easier to redact:

```powershell
Get-ComputerInfo -Property OsName, OsVersion, OsBuildNumber, OsArchitecture, CsName, WindowsProductName, OsServicePackMajorVersion
```

| Question | Answer |
|---|---|
| Does "2008" refer to the Windows Server edition, the SQL Server version, or the accounting software version? | |
| Exact `winver` version and build | |
| Windows edition (Standard / Enterprise / Datacenter / Foundation) | |
| Service Pack level | |
| Architecture (x86 / x64) | |
| Physical or already virtualised? | |
| Can the host run Hyper-V or another hypervisor? | |
| Total RAM and free disk (reported: 16 GB / ~2 TB SSD) | |

**Decision gate:** Windows Server 2008 and 2008 R2 are out of vendor support
and are not an accepted production target. If the evidence confirms 2008/2008
R2, the deployment cannot proceed on that OS. Two supported paths exist:

- **Path 1 — dedicated appliance/server:** a separate supported machine
  (Linux host recommended, since the application image is `linux/amd64`) used
  only for Dolphin.
- **Path 2 — OS upgrade:** upgrade the existing host to a supported Windows
  Server release with a container/virtualisation layer.

| Question | Answer |
|---|---|
| Which path is approved? | |
| Who pays for and owns the hardware/licence? | |

### 2. Co-hosted software constraints

| Question | Answer |
|---|---|
| Which accounting software runs on this host, and which version? | |
| What other application(s) run on it? | |
| Do any of them require a specific OS version, blocking an upgrade? | |
| Do any of them already bind ports 80, 443, 5432, or 8000? | |
| Is a maintenance window available, and when? | |

### 3. Network and routing

| Question | Answer |
|---|---|
| Tehran router brand / model / firmware version | |
| Parand router brand / model / firmware version | |
| Does each router support IPsec (or WireGuard) site-to-site VPN? | |
| Tehran public IP — static confirmed? | |
| Parand public IP — static confirmed? | |
| ISP name at each site, and any CGNAT or port-blocking in effect | |
| Internal subnet ranges at each site (must not overlap for site-to-site VPN) | |
| Uplink bandwidth at Parand (the server side) | |

Intended design, to be confirmed against the answers above: a router-to-router
site-to-site VPN carrying HTTPS, with individual VPN peers reserved for
management and for staff genuinely working outside the Tehran office.
PostgreSQL, the application port, Django Admin, SSH, RDP, container management,
and backup services are never published publicly.

### 4. Naming and certificates

| Question | Answer |
|---|---|
| Is there an Active Directory domain? If so, its name | |
| Is there a public internet domain for this system? | |
| Who owns/controls DNS, and can they create records on request? | |
| Internal hostname to be used for the application | |
| Will TLS use a public CA certificate or an internal/private CA? | |
| If internal CA: who distributes the trust root to client machines? | |

A private-network-only deployment can still use a real certificate, but the
chosen approach changes both the TLS runbook and the client rollout.

### 5. Users and load

| Question | Answer |
|---|---|
| Total number of application accounts expected in year one | |
| Peak number of simultaneously active users | |
| Number of marketers/sales agents (each needs an individual account) | |
| Are any users outside the Tehran office, now or planned? | |
| Expected sales/interaction records per day | |

Shared accounts are prohibited by decision, so the account count must equal the
headcount.

### 6. Power, endpoint security, and physical access

| Question | Answer |
|---|---|
| Is the Parand host on a UPS? Model and tested runtime | |
| Is there a generator or only battery backup? | |
| Antivirus / EDR product in use on the host | |
| Will antivirus exclusions be needed for the database/container directories? | |
| Who has physical access to the machine? | |
| Is the host in a locked room or rack? | |

### 7. Backup, restore, and ownership

| Question | Answer |
|---|---|
| Off-site backup destination (device, service, or location) | |
| Always-on Tehran destination for a second copy | |
| Available free space at each destination | |
| Required RPO (maximum acceptable data loss) | |
| Required RTO (maximum acceptable downtime) | |
| Backup retention period | |
| Who owns routine backup verification? | |
| Who is authorised to perform a restore? | |
| Who is the first-line incident contact, and what are their working hours? | |
| Who approves a maintenance window? | |

Backup and restore ownership must be a named person, not a role in the
abstract. the “PostgreSQL backup and restore verification” section of this document describes the mechanism; this table
records who is accountable for running it.

### 8. Commercial and support policy

| Question | Answer |
|---|---|
| Agreed support hours and response times | |
| Update/upgrade policy and who authorises a version change | |
| Is the source-protection and confidentiality contract signed? | |
| Who at the customer signs UAT acceptance? | |

### Completion

This survey is complete when every table above is filled and the OS decision
gate in section 1 has an approved path. Record the outcome in
`DOLPHIN_PROJECT_HANDOFF.md` §10 and §14, replacing the current unverified
claims with verified facts. Then P14 (real network/TLS/VPN build-out) may start.


## TLS edge procedure

*(from `docs/ops/TLS.md`)*

Status: repository TLS configuration is fail closed; certificate, hostname, Nginx runtime, and public scanner proof remain external.

The production Compose stack terminates TLS at its own Nginx service. Port 80 serves only the local liveness route and a permanent redirect to the one approved host. Application, admin, API, and static traffic use port 443. Nginx sends a fixed `X-Forwarded-Proto: https` value to the unexposed application service.

### Required inputs

Before starting the stack, the deployment owner must approve:

- one lowercase public hostname (or, with no domain, one static public IP — the certificate must then carry `subjectAltName=IP:`);
- a certificate chain valid for that hostname;
- its matching private key;
- protected host paths for the chain and key;
- the renewal owner and renewal test date.

Set `KARIZ_PUBLIC_HOST` to the exact host. `DJANGO_ALLOWED_HOSTS` must contain only that one value. `DJANGO_CSRF_TRUSTED_ORIGINS` must contain only `https://` plus that exact host, with no wildcard, dot prefix, sibling, port, slash, or extra entry. Set `KARIZ_TLS_CERT_PATH` and `KARIZ_TLS_KEY_PATH` to the approved host files. Compose mounts both read-only at fixed Nginx paths. Never place certificate or key content in the repository, image, command line, log, or evidence record.

Production validation rejects SSL redirect off, HSTS below one year, unsafe host values, host/origin mismatch, and any edge HSTS text that differs from the Django settings. The single exception is an explicit `DJANGO_SECURE_HSTS_SECONDS=0` with an empty `KARIZ_HSTS_HEADER`, which turns HSTS off entirely — intended for a staging or IP-only deployment on a self-signed certificate, where a one-year pin would leave the operator unable to click past their own warning; see the “Client-1 Linux staging guide” section of this document §2 scenario B. Off must be off at both layers: subdomain and preload HSTS are refused alongside it, and Nginx emits no header for an empty value. Nginx owns that checked header on every HTTPS status, including static and edge-generated errors; it hides the upstream copy to prevent duplicate policy headers. Subdomain HSTS and preload stay off unless the owner proves every affected subdomain is HTTPS and approves the wider scope.

### Preflight

Confirm the approved chain and key files exist and are readable only through the deployment secret process. Do not display file content. Then run:

```powershell
docker compose config --quiet
python scripts/validate_release_images.py
docker compose pull nginx
```

The quiet config check must fail when either TLS path is absent. Source tests do not prove that the certificate and key match.

After start, inspect Nginx health and restricted logs locally. Stop if Nginx cannot load the chain/key, if port 80 serves application content, if the redirect host differs, or if the certificate name/chain is wrong.

### Live proof

From an approved external client, prove:

- HTTP redirects to the fixed approved HTTPS host;
- TLS 1.0 and 1.1 fail while TLS 1.2 and 1.3 work;
- certificate name, chain, validity, and renewal path are correct;
- login, CSRF, secure cookies, HSTS, static files, API errors, and request IDs work through HTTPS;
- direct application port 8000 and database port 5432 are not public;
- a reviewed TLS scanner has no release-blocking result.

Record only host, time, release reference, tool version, status, and reviewer. Do not store cookies, headers with credentials, key data, or raw restricted logs.

### Renewal

Renew into protected host files using the approved certificate process. Validate the new pair before cutover, keep the prior valid pair recoverable, then reload or restart only Nginx through the approved change. Repeat hostname, chain, expiry, redirect, health, login, and scanner proof. If any check fails, restore the prior pair and reload Nginx; do not weaken TLS or expose HTTP application traffic.


## Synthetic UAT data

*(from `docs/ops/UAT.md`)*

The UAT seed command creates one fixed, obviously synthetic CRM graph for acceptance checks. It never deletes, resets, updates, or overwrites rows.

### Hard guards

The command runs only when every guard passes:

1. `DOLPHIN_ALLOW_UAT_SEED` equals `1`.
2. `--confirm-synthetic-data` is present.
3. The database is either the repo test settings' Django in-memory database or PostgreSQL with a lowercase safe name shaped like `uat_dolphin_team_1`.
4. User, Customer, Product Category, Product, Lead, Interaction, Sale, After-sales Request, and ActivityLog tables are all empty.
5. `DOLPHIN_UAT_PASSWORD` is present and passes the configured Django password validators for all five fixed identities.

The command checks emptiness again inside the write transaction. A failed row or audit rolls back the full graph. A second run refuses the nonempty database.

### Run

Set a strong password made only for this isolated UAT environment. Do not reuse a real account password. Keep it out of shell history and logs.

PowerShell:

```powershell
$env:DOLPHIN_ALLOW_UAT_SEED = "1"
$env:DOLPHIN_UAT_PASSWORD = Read-Host "UAT password" -MaskInput
python manage.py seed_synthetic_uat --confirm-synthetic-data
Remove-Item Env:DOLPHIN_UAT_PASSWORD
Remove-Item Env:DOLPHIN_ALLOW_UAT_SEED
```

The success output contains no password or password hash.

### Fixed graph

- Five active CRM identities across the four fixed role codes: one sales/call-center Sales Agent, one bounded after-sales Sales Agent, one Sales Manager, one Company IT, and one Platform Admin.
- Both operator identities keep the `sales_agent` role. Their fixed workstreams are `sales` and `after_sales`; no fifth role or dynamic permission is created.
- All five remain outside Django admin with `is_staff=false` and `is_superuser=false`.
- One Persian synthetic Customer with one synthetic primary phone.
- One Persian synthetic Product Category and one categorized Product.
- One Lead assigned by the Sales Manager to the Sales Agent.
- One Interaction by that Sales Agent.
- One confirmed Sale for two units of the synthetic Product.
- One open after-sales case linked to that Customer and Sale and assigned to the bounded after-sales operator.
- Safe audit rows for seeded users and service-managed actions. No plaintext password enters audit data.

### Separate acceptance personas

Run and record each persona separately against the same exact isolated release artifact:

1. `uat_platform_admin`: platform home, full clean CRM identity custody, audit, and all shipped business modules.
2. `uat_sales_manager`: store-manager home, company scope, both Sales Agent identities, reports, catalog management, and after-sales management; no platform audit custody.
3. `uat_sales_agent`: assigned Lead/work queue, permitted Customer, Interaction, own Sale, read-only catalog, and own report; no user administration or audit.
4. `uat_after_sales_operator`: assigned after-sales case only; no unrelated Customer, Sale, sales report, user administration, or audit navigation/data.

The release record must bind browser evidence, PostgreSQL database identity, Compose image digests, public host, and time to the exact candidate. Repository test execution alone does not complete target UAT.

This fixture is only for isolated UAT. It is not a production bootstrap, demo reset, migration, or recovery tool.
