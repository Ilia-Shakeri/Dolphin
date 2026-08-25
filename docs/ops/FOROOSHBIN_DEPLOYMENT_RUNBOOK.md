# ForooshBin — deployment and operations runbook

**This is the canonical document for installing, starting, updating, backing up,
restoring and recovering ForooshBin.** Where any other document disagrees with
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
| [7. Static-IP deployment](#7-static-ip-deployment) | Staging / internal only |
| [8. Troubleshooting](#8-troubleshooting) | Something is broken |
| [9. Security and secrets](#9-security-and-secrets) | Always |

Throughout, `$DEPLOY` is the deployment directory — this runbook uses
`/srv/forooshbin/client-1`. Adjust once and stay consistent.

Every Compose command needs `--env-file secrets/.env`. Compose does **not** read
that path automatically, and without it the stack fails on missing variables.

---

## Shipping a change

The everyday loop, start to finish. Two commands on the server; everything else
happens on the machine you develop on. The longer sections below explain what
these do and what to reach for when something is wrong — this is the path when
nothing is.

`$DEPLOY` is the deployment directory, `/srv/forooshbin/FrooshBin` on the
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
printf '1.1.2
' > VERSION
```

Record what changed in `CHANGELOG.md`: what was added, changed, removed and
fixed. Commit both with the work they describe, and push.

Build the image and tag it with the same version:

```bash
docker build -t forooshbin-app:v1.1.2 .
```

```bash
docker save forooshbin-app:v1.1.2 | gzip > forooshbin-app-v1.1.2.tar.gz
```

```bash
scp forooshbin-app-v1.1.2.tar.gz deploy@<server>:/srv/forooshbin/
```

### 2. On the server

Load the image:

```bash
docker load -i /srv/forooshbin/forooshbin-app-v1.1.2.tar.gz
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
(`forooshbin`); the version lives in the image tag and nowhere else. Standing up
a second project beside the live one looks like a safe way to trial a release
and is not: both publish 80 and 443, and both name the same external volume, so
two PostgreSQL servers end up writing one data directory. `postmaster.pid` does
not protect against this across containers — the second server checks the
recorded PID inside its own namespace, does not find it, decides the lock is
stale and starts anyway. The result is shared-catalog corruption. To trial a
release without touching production, use a separate host or a separate volume
set.

**Never run a release with a prompt in it.** `docker compose run` attaches a TTY
by default, and psql's `\password` reads the terminal instead of stdin whenever
one is present, which silently discards the passwords `db-bootstrap` pipes in
from `.env`. Every service invocation in a release path uses `-T`.

---

## 0. Cheat sheet

Run all of these from `$DEPLOY`.

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
  /static/common/forooshbin.css \
  /static/common/forooshbin-app.js \
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
sudo mkdir -p /srv/forooshbin/client-1
sudo chown "$USER":"$USER" /srv/forooshbin/client-1
cd /srv/forooshbin/client-1
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
  | gzip > forooshbin-images.tar.gz
sha256sum forooshbin-images.tar.gz
```

Copy the archive across, verify the checksum matches what the build machine
printed, then:

```bash
gunzip -c forooshbin-images.tar.gz | docker load
docker images --digests | grep -E 'app-repository|postgres|nginx'
```

The digests on the host must equal the digests in `.env`. That equality is the
whole point of pinning by digest.

### 1.7 External volumes

Database and backup volumes are declared `external: true`, so Compose refuses to
invent them. Creating them by hand is deliberate: it makes accidental data loss
through `docker compose down -v` impossible.

```bash
docker volume create forooshbin_postgres_data
docker volume create forooshbin_postgres_backups
```

The backup volume needs a one-time sentinel before the backup job will write to
it — see [4.1](#41-prepare-the-backup-volume-once).

### 1.8 `.env`

**Generate it rather than writing it by hand:**

```bash
python3 scripts/new_deployment.py --slug <customer> --host <public-hostname> --out /srv/forooshbin/<customer>
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
| `POSTGRES_*_USER` / `POSTGRES_DB` | any safe lowercase identifier | Fresh installs get `forooshbin*` names from the template; an existing deployment keeps whatever it already has |
| `KARIZ_BILLING_INVOICE_AFFECTS_STOCK` | **leave unset** | See [1.11](#111-client-1-business-switches) |

> **Why the `KARIZ_` prefix is still there.** It is a compatibility contract, not
> branding: `compose.yml`, the nginx envsubst filter, `config/production_env.py`
> and every existing `.env` read these exact names. Renaming them would break a
> running deployment on upgrade for no functional gain. Everything a customer
> sees says ForooshBin / فروش‌بین.

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

Copy `manifest.json` to `secrets/` on the host and point
`KARIZ_DEPLOYMENT_MANIFEST_PATH` at it.

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

It prompts for the password twice, enforces Django's password validators, and
refuses to run if an active Platform Admin already exists.

> **Password recovery is a host operation.** No interface anywhere changes a
> password, and the API refuses it. A user who forgets theirs is recovered with
> `docker compose --env-file secrets/.env run --rm web python manage.py changepassword <username>`.

### 1.16 Smoke check

1. Open `https://${PUBLIC}/` and sign in as the Platform Admin.
2. The dashboard renders with the dark sidebar, Persian RTL, and the ForooshBin
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
cd /srv/forooshbin/client-1
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

What is running now: project, image tag, database volume, and every ForooshBin
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

`-T` is required, not cosmetic. `docker compose run` attaches a TTY by default,
and psql's `\password` reads from the terminal rather than from stdin whenever
one is present — so the script prompts the operator and discards the passwords
it piped in from `.env`. The roles then hold whatever the terminal supplied, and
the next backup fails to authenticate against them. Running the same service
through `up` is unaffected, because a service has no TTY.

### One stack, not one per version

`KARIZ_COMPOSE_PROJECT_NAME` names a **stable** project, and
`POSTGRES_DATA_VOLUME` a single fixed volume. The version belongs to the image
tag, never to the project name.

Standing up `forooshbin-v110` and `forooshbin-v111` as parallel Compose projects
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
   git -C /srv/forooshbin/client-1 pull --ff-only
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

The order below is not arbitrary. The `backup` service runs with `cap_drop:
ALL`, and this command adds only `CHOWN`. `chmod` on a path you do not own needs
`CAP_FOWNER`, which is not there — so every `chmod` has to happen while root
still owns the path, before the matching `chown`. `/backups` itself is handed
over last, because once it belongs to `postgres` at mode `0700` a root without
`DAC_OVERRIDE` can no longer write the sentinel into it.

It reclaims ownership of `/backups` first so it can be re-run. An earlier
attempt that chowned the directory and then failed leaves it owned by
`postgres`, and without this the retry fails at the same `chmod` as the first
run did. The emptiness test still guards the volume: this recovers a
half-prepared directory, never an inhabited one.

```bash
docker compose --env-file secrets/.env --profile backup run --rm --no-deps \
  --user root --cap-add CHOWN --entrypoint sh backup -c \
  'set -eu; test -z "$(find /backups -mindepth 1 -maxdepth 1 -print -quit)"; chown root:root /backups; chmod 0700 /backups; printf "%s\n" FROOSHBIN_BACKUP_ROOT_V1 > /backups/.frooshbin-backup-root; chmod 0600 /backups/.frooshbin-backup-root; chown postgres:postgres /backups/.frooshbin-backup-root; chown postgres:postgres /backups'
```

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

Archives are named `frooshbin-pg-<UTC timestamp>-<32 hex>.dump`, each beside its
`.sha256`, on the `backup_data` volume.

```bash
docker compose --env-file secrets/.env --profile backup run --rm --no-deps \
  --entrypoint sh backup -c 'ls -l /backups'
```

### 4.4 Schedule it

As the deployment user, `crontab -e`:

```
15 2 * * * cd /srv/forooshbin/client-1 && docker compose --env-file secrets/.env --profile backup run --rm backup >> /var/log/forooshbin-backup.log 2>&1
```

Retention is `POSTGRES_BACKUP_RETENTION_DAYS` in `.env`. `0` keeps everything —
correct until someone has decided the real policy in writing.

Also schedule expired-session cleanup. Django stops honouring expired sessions
but never deletes the rows, so `django_session` grows forever:

```
30 3 * * 0 cd /srv/forooshbin/client-1 && docker compose --env-file secrets/.env --profile maintenance run --rm session-cleanup >> /var/log/forooshbin-session-cleanup.log 2>&1
```

### 4.5 Verify a restore — into a disposable database

This is the only supported restore rehearsal. It restores into a throwaway
database and never touches the live one.

```bash
docker compose --env-file secrets/.env -f compose.restore-verify.yml --profile restore-verify config --quiet
docker compose --env-file secrets/.env -f compose.restore-verify.yml --profile restore-verify run --rm --no-deps restore-verify frooshbin-pg-<timestamp>-<token>.dump
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
git -C /srv/forooshbin/client-1 checkout <previous-tag>
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
   cd /srv/forooshbin/client-1
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
renamed to `forooshbin.css` / `forooshbin-app.js`; a cache holding the old names
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
  `chmod 600 secrets/tls/privkey.pem`.
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
| `docs/ops/BACKUP_RESTORE.md` | Backup internals and the restore-verification contract |
| `docs/ops/DATABASE_ROLES.md` | The per-table privilege contract |
| `docs/ops/TLS.md` | Certificate handling detail |
| `docs/ops/ROLLBACK.md` | Rollback detail |
| `docs/ops/INCIDENT_RESPONSE.md` | What to do during an incident |
| `docs/ops/UAT.md` | Acceptance test script |
| `docs/ops/CLIENT1_LINUX_STAGING_GUIDE.md` | The original Client-1 staging walkthrough |
