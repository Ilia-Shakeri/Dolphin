# Multi-server Docker deployment

How to bring ForooshBin up on **clean Linux servers**, in three topologies:

1. one server running the application and PostgreSQL together;
2. the application and PostgreSQL on separate servers;
3. several isolated customer deployments on shared infrastructure.

This document is the *from nothing* runbook. It does not replace the existing
operational documents and deliberately does not repeat them:

| For | Read |
|---|---|
| Upgrading an already-running deployment | `DEPLOYMENT.md` |
| Backup and restore procedure and evidence | `BACKUP_RESTORE.md` |
| Rollback procedure | `ROLLBACK.md` |
| Database roles and the privilege contract | `DATABASE_ROLES.md` |
| Certificate issuance and TLS policy | `TLS.md` |
| Dependency lock rules | `DEPENDENCIES.md` |
| Feature manifest design | `../backend/DEPLOYMENT_PROFILE.md` |

**No real secret, key, certificate, password, hostname, or customer identifier
belongs in this file or anywhere else in Git.** Every value below is a
placeholder. Commands that would print a secret are written so they do not.

---

## 0. What the shipped Compose file actually is

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

## 1. Prerequisites on every server

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

## 2. Directory layout on the deployment host

Use one directory per deployment. Everything outside Git lives here.

```text
/srv/forooshbin/<deployment-name>/
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
sudo install -d -m 755 -o "$USER" -g "$USER" /srv/forooshbin/<deployment-name>
cd /srv/forooshbin/<deployment-name>
install -d -m 700 secrets secrets/tls
```

The application source tree is **not** deployed. Only the files above plus the
images. Do not clone this repository onto a customer server.

---

## 3. Build the application image (on your build machine, not the customer's)

The build is hash-pinned and platform-pinned; the Dockerfile refuses anything
else. `PYTHON_BASE_IMAGE` must be a digest reference for CPython 3.13.

```bash
# On a Linux amd64 build host, from a checkout of the reviewed commit.
export PYTHON_BASE_IMAGE='python@sha256:<reviewed-64-hex-digest>'

docker build \
  --platform linux/amd64 \
  --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
  --tag forooshbin:<release-version> \
  .
```

Then prove the image ships nothing it should not — no docs, no tests, no
repository metadata, no scripts, no signing key:

```bash
docker create --name forooshbin-check forooshbin:<release-version>
docker export forooshbin-check | tar -t > /tmp/image-listing.txt
docker rm forooshbin-check
python scripts/validate_image_content.py --listing /tmp/image-listing.txt
```

Push to the registry the customer host can reach, then **record the digest** —
the digest, not the tag, is what the deployment pins:

```bash
docker push <registry>/forooshbin:<release-version>
docker inspect --format='{{index .RepoDigests 0}}' <registry>/forooshbin:<release-version>
```

For an air-gapped site, move the image as a file instead:

```bash
docker save forooshbin:<release-version> | gzip > forooshbin-<release-version>.tar.gz
# transfer, then on the target:
gunzip -c forooshbin-<release-version>.tar.gz | docker load
```

### Optional: server-generated PDF

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

## 4. Secrets and the `.env` file

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

## 5. Create the external volumes

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

## 6. Obtain the signed deployment manifest

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

## 7. Topology 1 — one server, application and database together

The shipped `compose.yml` describes exactly this. Recommended for a single site.

```bash
cd /srv/forooshbin/<deployment-name>
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

## 8. Topology 2 — application and database on separate servers

Use this when the database must live on its own hardware or a hardened host.

**Read this first.** The override below uses the `!reset` and `!override` merge
keywords, which need Compose **v2.24.4 or newer**; check `docker compose version`
before relying on them. The shipped `compose.yml` is written for a single host: it
pins `POSTGRES_HOST: db` and marks the `backend` network `internal: true`. A
split deployment therefore needs a small, explicit override — and it needs
transport security, because the connection now crosses a real network instead of
a Docker bridge that never leaves the machine.

### 8.1 Database server (server B)

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

### 8.2 Application server (server A)

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

## 9. Topology 3 — several isolated customer deployments

One host, several customers, no shared state. Isolation comes from giving each
deployment its own everything:

| Per deployment | How |
|---|---|
| Directory | `/srv/forooshbin/<customer>/` |
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

## 10. Health, static assets, and port exposure

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
curl -fsS -o /dev/null -w '%{http_code}\n' "https://<public-host>/static/common/forooshbin.css"
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

## 11. First Platform Admin

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

## 12. Persistence across restart

Prove the volume, not the container, holds the data:

```bash
docker compose --env-file secrets/.env restart web
docker compose --env-file secrets/.env ps          # web healthy again
# Then, in the UI, confirm a record created before the restart is still present.
```

For a full-stack restart, follow the ordered stop procedure in `DEPLOYMENT.md`
(§"Safe full-stack stop") rather than `docker compose down`, which is where
external volumes get detached by accident.

---

## 13. Backups and restore

The `backup` service is behind a Compose profile, so it never runs on its own:

```bash
docker compose --env-file secrets/.env --profile backup run --rm backup
docker run --rm -v <deployment>_postgres_backups:/backups alpine ls -la /backups
```

Copy archives off the host — a backup on the same disk as the database is not a
backup:

```bash
docker run --rm -v <deployment>_postgres_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/forooshbin-backups-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /backups .
# Encrypt before it leaves the host; keep the passphrase in your secret manager.
gpg --symmetric --cipher-algo AES256 forooshbin-backups-*.tar.gz
scp forooshbin-backups-*.tar.gz.gpg <operator>@<backup-destination>:<path>/
shred -u forooshbin-backups-*.tar.gz
```

**A backup is only real once restored.** The repository ships an isolated
verifier that restores into a throwaway database with `network_mode: none` and
checks the schema contract:

```bash
docker compose --env-file secrets/.env -f compose.restore-verify.yml \
  --profile restore-verify run --rm restore-verify
```

Run it on a schedule, not only at install. Full procedure and evidence
requirements: `BACKUP_RESTORE.md`.

---

## 14. Logging

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

## 15. Start on boot

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

## 16. Upgrade

Follow `DEPLOYMENT.md` for the full gated procedure. In outline:

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

## 17. Rollback

Full procedure in `ROLLBACK.md`. The decisive question is whether the release
applied a migration:

* **No migration applied** — put the previous digest back in `.env`, `pull`,
  `up -d`. The database is untouched.
* **A migration applied** — code alone cannot go back, because the old code does
  not know the new schema. Restore the pre-upgrade backup taken in §16 step 1,
  then redeploy the previous digest. This is why that step is not optional.

---

## 18. Disaster recovery

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

## 19. Troubleshooting

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

## 20. Complete uninstall

**This destroys customer data. Take and verify a final backup first (§13), and
copy it off the host.** Then confirm you are in the right directory and
targeting the right project — the volume names are the point of no return.

```bash
cd /srv/forooshbin/<deployment-name>
docker compose --env-file secrets/.env config --format json | grep -o '"name": *"[^"]*"' | head -1

docker compose --env-file secrets/.env down --remove-orphans   # keeps volumes
docker volume rm <deployment>_postgres_data                    # irreversible
docker volume rm <deployment>_postgres_backups                 # irreversible

sudo rm -rf /srv/forooshbin/<deployment-name>
docker image rm <app-image-digest> <postgres-image-digest> <nginx-image-digest>
docker system prune -f
```

On a host with several deployments (§9), every command above must name the one
deployment. `docker system prune -a` and `docker volume prune` do **not**
distinguish between customers — do not use them there.

Finally, revoke what outlived the host: the TLS certificate, the database
credentials, and the deployment's manifest key if it was deployment-specific.
