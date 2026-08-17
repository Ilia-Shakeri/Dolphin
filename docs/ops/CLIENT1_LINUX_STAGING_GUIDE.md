# Client-1 Linux staging guide

Bring ForooshBin up on a **fresh Linux amd64 server**, from nothing to a stack
you can hand to UAT. Follow it top to bottom; each section ends with something
you can check.

Two conventions used throughout:

* **FINAL INPUT** — a value or step that must come from the product owner or the
  customer. It is not a placeholder you may invent. Staging can proceed with a
  staging-only substitute where the step says so; production cannot.
* Every credential, host and key below is a placeholder. **Nothing real belongs
  in this file, in Git, or in a shell you did not clear afterwards.**

Related documents, not repeated here: `MULTI_SERVER_DOCKER_DEPLOYMENT.md` (three
topologies and the split-server override), `BACKUP_RESTORE.md`, `ROLLBACK.md`,
`DATABASE_ROLES.md`, `TLS.md`, `DEPENDENCIES.md`,
`../backend/DEPLOYMENT_PROFILE.md`.

---

## 0. What you are deploying

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

## 1. Server assumptions

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

If Docker is absent, install **Docker Engine + the Compose v2 plugin from
Docker's own repository**. Distribution packages are frequently too old for the
Compose syntax used here.

---

## 2. Network, DNS and TLS

| Item | Value | Status |
|---|---|---|
| Public hostname | `<crm.example.com>` | **FINAL INPUT** |
| DNS A/AAAA record → this server | — | **FINAL INPUT** |
| TLS certificate chain + private key | `secrets/tls/fullchain.pem`, `secrets/tls/privkey.pem` | **FINAL INPUT** |
| VPN / private routing to the customer network | — | **FINAL INPUT** (see `TARGET_SITE_SURVEY.md`) |

For staging you may use a staging hostname and a self-signed or internal
certificate. Note it in the run record; a self-signed certificate is not a TLS
readiness proof.

Ports reachable from users: **443**, and **80** only because it redirects.
Nothing else.

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
# 5432 is never published. Verify later in section 12.
```

---

## 3. Directory layout

```bash
sudo install -d -m 755 -o "$USER" -g "$USER" /srv/forooshbin/client-1
cd /srv/forooshbin/client-1
install -d -m 700 secrets secrets/tls
```

```text
/srv/forooshbin/client-1/
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

## 4. Release flow and image build

Build on your build machine, not the customer's. The Dockerfile is
hash-pinned and platform-pinned and refuses anything else.

```bash
git clone <repository-url> forooshbin-src && cd forooshbin-src
git checkout <reviewed-release-commit>

export PYTHON_BASE_IMAGE='python@sha256:<reviewed-64-hex-digest>'
docker build \
  --platform linux/amd64 \
  --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}" \
  --tag forooshbin:<release-version> .
```

### Image-content validation — do not skip

Proves the image ships no documentation, tests, repository metadata, ops
scripts or signing material:

```bash
docker create --name forooshbin-check forooshbin:<release-version>
docker export forooshbin-check | tar -t > /tmp/image-listing.txt
docker rm forooshbin-check
python scripts/validate_image_content.py --listing /tmp/image-listing.txt   # expect IMAGE_CONTENT_PASS
```

Push and **record the digest** — the digest, not the tag, is what the deployment
pins:

```bash
docker push <registry>/forooshbin:<release-version>
docker inspect --format='{{index .RepoDigests 0}}' <registry>/forooshbin:<release-version>
```

Air-gapped alternative:

```bash
docker save forooshbin:<release-version> | gzip > forooshbin-<release-version>.tar.gz
# transfer, then on the server:
gunzip -c forooshbin-<release-version>.tar.gz | docker load
```

### Optional: server-side PDF

Invoice and quotation PDFs are produced by printing the application's own print
page with a headless browser. Without a browser in the image the feature stays
off and users still get correct Persian PDFs through their browser's
print / save-as-PDF — that is the supported day-one path.

To enable the server-side download, add Chromium to the image and set
`KARIZ_PDF_RENDERER=chromium`. The trade is real: about 300–400 MB and an `apt`
layer that is **not** hash-pinned the way `requirements.txt` is. Record the
installed version in the release notes if you take it.

---

## 5. Secrets and `.env`

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
| `DJANGO_ALLOWED_HOSTS`, `KARIZ_PUBLIC_HOST` | the real hostname users type | **FINAL INPUT** |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` + that hostname | **FINAL INPUT** |
| `POSTGRES_INIT/MIGRATION/APP/BACKUP_PASSWORD` | four independent values, ≥16 chars | **FINAL INPUT** for production |
| `KARIZ_TLS_CERT_PATH`, `KARIZ_TLS_KEY_PATH` | absolute paths under `secrets/tls/` | **FINAL INPUT** |
| `KARIZ_DEPLOYMENT_MANIFEST_PATH` | absolute path to `secrets/manifest.json` | — |
| `KARIZ_DEPLOYMENT_MANIFEST_KEYS` | `key-id:base64-ed25519-**public**-key` | **FINAL INPUT** |
| `POSTGRES_DATA_VOLUME`, `POSTGRES_BACKUP_VOLUME` | the external volume names from §6 | — |
| `POSTGRES_BACKUP_RETENTION_DAYS` | a deliberate whole-day number | — |
| `POSTGRES_SSLMODE` | leave **empty** on a single host; the database is only on an internal Docker network | — |

The manifest **signing private key never reaches a deployment host.** Only the
public verification key is configured here.

---

## 6. External volumes

Compose will not create these, on purpose: an accidental new volume is an empty
database, and an empty database that starts cleanly is how data loss is missed.

```bash
docker volume create client1_postgres_data
docker volume create client1_postgres_backups
docker volume ls | grep client1
```

Put those exact names in `POSTGRES_DATA_VOLUME` / `POSTGRES_BACKUP_VOLUME`.

---

## 7. Client-1 deployment manifest

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

## 8. Bring the stack up

```bash
cd /srv/forooshbin/client-1
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

## 9. Static files — check this before anything else

The static layer changed materially in this release and has only ever been
exercised on Windows. It is the single most likely thing to behave differently
here, so verify it before UAT rather than during it.

```bash
for path in \
  /static/css/style.bundle.rtl.css \
  /static/plugins/global/plugins.bundle.rtl.css \
  /static/js/scripts.bundle.js \
  /static/common/kariz.css \
  /static/common/kariz-app.js \
  /static/common/favicon.ico \
  /static/fonts/IRANSansWeb.woff \
  /static/plugins/global/fonts/keenicons/keenicons-duotone.woff ; do
  printf '%s ' "$path"
  curl -s -o /dev/null -w '%{http_code}\n' "https://<crm.example.com>${path}"
done
```

All eight must be `200`. If the theme bundles 404 the UI renders unstyled; if
the fonts 404 the Persian text falls back and the sidebar icons vanish.

Expect roughly **197 files, ~11 MB** in the `static_data` volume — the theme's
demo imagery, unused icon families and LTR bundles are excluded by
`common/management/commands/collectstatic.py`.

---

## 10. Health and readiness

```bash
# Application + database, from inside the container.
docker compose --env-file secrets/.env exec -T web python -c \
"import os,urllib.request;h=os.environ['DJANGO_ALLOWED_HOSTS'].split(',')[0].strip();\
r=urllib.request.Request('http://127.0.0.1:8000/api/v1/health/ready/',headers={'Host':h,'X-Forwarded-Proto':'https'});\
print(urllib.request.urlopen(r,timeout=3).status)"

# The edge over plain HTTP — the only non-redirect HTTP route.
curl -fsS http://127.0.0.1/health/live/ && echo

# The edge over TLS, as a user reaches it.
curl -fsS "https://<crm.example.com>/api/v1/health/ready/" && echo
```

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

Every other account is then created from the UI by that Platform Admin.

---

## 12. Exposure check

```bash
docker compose --env-file secrets/.env ps --format '{{.Service}}\t{{.Ports}}'
sudo ss -ltnp | grep -E ':(5432|8000)\b' \
  && echo "EXPOSED — stop and fix" || echo "database and app not published: ok"

curl -s -o /dev/null -w 'admin=%{http_code}\n' "https://<crm.example.com>/admin/"
```

Only `nginx` may map `0.0.0.0:80` and `0.0.0.0:443`. `/admin/` must return
**404** — the Django admin is unregistered in production independently of
`DEBUG`, and Nginx denies the prefix. A 200 there is a misconfiguration.

---

## 13. UAT

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

**Presentation**, on every page: Persian RTL, ForooshBin branding, dates Jalali
(`۱۴۰۵/۰۵/۲۵`), no English UI text, no theme or language switcher, no social
sign-in, no placeholder control.

---

## 14. Print and PDF

```text
/invoices/<id>/print/     → Persian RTL sheet, no navigation, Jalali dates
browser print / save-PDF  → correct Persian shaping in the produced file
/invoices/<id>/print.pdf  → 200 only if §4's optional Chromium layer was built;
                            otherwise 503 with a Persian message pointing at
                            browser print. Both are correct behaviour.
```

---

## 15. Performance smoke

Not a load test — a sanity check that nothing is pathological:

```bash
for path in / /customers/ /invoices/ /reports/receivables/ ; do
  printf '%s ' "$path"
  curl -s -o /dev/null -w '%{time_total}s\n' -b <session-cookie> "https://<crm.example.com>${path}"
done
```

Expect well under a second each on an idle staging box. Then open the browser
devtools network panel on the customers list and confirm the page issues a
small, constant number of requests — list endpoints are paginated and
`select_related`/`prefetch_related` are covered by query-growth tests, so a
count that climbs with row count means something regressed.

---

## 16. Reboot and persistence

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

## 17. Backup, restore, rollback

```bash
# Backup (behind a Compose profile, so it never runs on its own)
docker compose --env-file secrets/.env --profile backup run --rm backup
docker run --rm -v client1_postgres_backups:/backups alpine ls -la /backups

# Off-host copy — a backup on the same disk is not a backup
docker run --rm -v client1_postgres_backups:/backups -v "$PWD":/out alpine \
  tar czf /out/forooshbin-backups-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /backups .
gpg --symmetric --cipher-algo AES256 forooshbin-backups-*.tar.gz
scp forooshbin-backups-*.tar.gz.gpg <operator>@<backup-destination>:<path>/
shred -u forooshbin-backups-*.tar.gz

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

Full procedures: `BACKUP_RESTORE.md`, `ROLLBACK.md`.

---

## 18. Logs

Every service is capped at 5 × 10 MB JSON files, so logs cannot fill the disk.
PostgreSQL is configured not to log statements, parameters or connections —
customer data must not reach a log file.

```bash
docker compose --env-file secrets/.env logs --tail 200 web
docker compose --env-file secrets/.env logs --since 1h nginx
```

Application logs are structured JSON with a request id. Review any log for
customer data before pasting it into a ticket.

---

## 19. Stop, start, update

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

## 20. Troubleshooting

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

## 21. Uninstall

**This destroys customer data. Take and verify a final backup first (§17) and
copy it off the host.**

```bash
cd /srv/forooshbin/client-1
docker compose --env-file secrets/.env down --remove-orphans   # keeps volumes
docker volume rm client1_postgres_data                         # irreversible
docker volume rm client1_postgres_backups                      # irreversible
sudo rm -rf /srv/forooshbin/client-1
docker image rm <app-digest> <postgres-digest> <nginx-digest>
```

On a host with several deployments, every command must name the one deployment.
`docker system prune -a` and `docker volume prune` do **not** distinguish
between customers — do not use them there.

Finally revoke what outlived the host: the TLS certificate, the database
credentials, and the manifest key if it was deployment-specific.

---

## Sign-off checklist

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
