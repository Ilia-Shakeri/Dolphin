# Deployment procedure

> This document defines an operations procedure, not live project status. Current progress, blockers, evidence, and exact next action exist only in `KARIZ_PROJECT_HANDOFF.md`.

Procedure snapshot: repository procedure was complete at its recorded release reference; use `KARIZ_PROJECT_HANDOFF.md` for the current proof state.

This guide uses the current [Compose definition](../../compose.yml), [production settings](../../config/production_settings.py), [database-role guide](DATABASE_ROLES.md), health routes, and [backup guide](BACKUP_RESTORE.md). It does not prove that a host is ready.

## Current topology and limits

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
- TLS paths and the public host are required Compose inputs. Nginx mounts the chain/key read-only, allows TLS 1.2/1.3, and sends a fixed HTTPS scheme to Django. Certificate, hostname, renewal, scanner, and browser proof still need the target host procedure in [TLS.md](TLS.md).

## Required release inputs

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

For an existing `postgres_data` volume, read and complete the in-place upgrade steps in the [database-role guide](DATABASE_ROLES.md) before starting the new stack. Never delete or recreate the volume to adopt the role split.

## Repository proof

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

## Current-compatible write-stop and recovery point

For every existing database, complete this section from the currently deployed compatible release and its current protected inputs before replacing `.env`, loading candidate image references, pulling candidate images, or starting any candidate service. Record the current application and PostgreSQL image digests without printing secrets.

Enable and prove the current release write-stop through its approved override. Keep it on through candidate acceptance:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
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

For a legacy database without the managed backup role or bundled job, use the already approved owner/legacy backup path and host-only verifier from [the database-role guide](DATABASE_ROLES.md). Do not run candidate `db-bootstrap` merely to create the backup role. For a proven empty new installation, record explicit new-install approval instead of inventing a recovery point.

The gate passes only with the matching SHA-256 sidecar, successful archive list, protected destination, and successful disposable restore. Guard tests or an archive list alone do not pass. Stop before candidate input changes if any proof fails.

## Target preflight

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

## Preserve edge write-stop

The current-compatible gate already enabled the stop for an existing deployment. Base candidate Compose is the off state; validate both candidate source states without printing expanded configuration:

```powershell
docker compose -f compose.yml config --quiet
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
```

Show current runtime state:

```powershell
docker compose exec -T nginx grep -E '^# kariz-write-stop: (on|off)$' /etc/nginx/write-stop.conf
```

If the candidate edge must be recreated before application acceptance, recreate it only with the write-stop override and prove the on mount:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
```

Run the safe health and write probes in [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md). Reopen writes only after the release owner passes the required data, readiness, role, audit, TLS, and browser gates.

Do not run the base off-state recreation yet. Never use a volume-removing teardown for this control. Source and static tests do not prove native Nginx parse, mount replacement, response behavior, or target-host TLS; those remain external gates.

## Recovery point gate

Confirm the current-compatible gate above passed before the candidate `.env`, image pull, or database start. Do not replace it with a new dump made after candidate image or role mutation. Keep the recorded archive, sidecar, restore result, current image references, operator, and UTC time tied to this release.

## Role and migration-plan gate

Only after the compatible recovery point and disposable restore pass may the candidate mutate database roles or ownership and inspect the migration plan with the managed owner:

```powershell
docker compose run --rm db-bootstrap
docker compose run --rm --no-deps migrate python manage.py migrate --plan
```

Stop if role bootstrap fails, the plan differs from review, or a migration lacks a compatible recovery path. Keep writes stopped. Do not continue merely because rerunning the one-shot job might succeed.

## Apply release

After approval, let Compose run the one-shot migration/static service and start the application:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-build
docker compose ps --all
docker compose logs --no-color --tail 200 db-bootstrap migrate db-finalize
```

The `db-bootstrap`, `migrate`, and `db-finalize` services must show exit code 0. `db`, `web`, and `nginx` must become healthy. Treat logs as restricted operational data; review them locally and do not paste raw output into public tickets.

## First Platform Admin

For a new database with no Platform Admin row, active or inactive, run the guarded interactive command exactly once:

```powershell
$approvedUsername = Read-Host 'Approved username'
docker compose exec web python manage.py bootstrap_platform_admin --username $approvedUsername
```

The command prompts twice for the password, accepts no password argument, applies configured password validators, creates a CRM `platform_admin` without staff or superuser flags, and appends a safe audit event. It refuses any later bootstrap when a Platform Admin row already exists. Do not use `createsuperuser` as a substitute.

## Health and smoke gates

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

Then run controlled browser smoke for `/`, `/admin/login/`, login/logout with CSRF, one safe read per CRM role, static delivery, RTL/Persian output, ForooshBin branding, responsive viewports, and clean console/network behavior. Never use production customer data for smoke fixtures.

Only after every acceptance gate and reopen approval passes, recreate just Nginx from base Compose and prove the off mount:

```powershell
docker compose -f compose.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml exec -T nginx grep -F '# kariz-write-stop: off' /etc/nginx/write-stop.conf
```

This recreates only `nginx`; it does not stop `web` or `db`.

## Safe full-stack stop and same-release restart

Use this only for an approved full outage after the current release jobs completed successfully. First enable and prove write-stop. Prove that `db-bootstrap`, `migrate`, `db-finalize`, and any prior `backup` job are not running; abort if one is active or a current release job failed. Then create and disposable-restore a fresh retention-disabled backup by the exact procedures above. Record the stable Compose project name, archive leaf, restore result, owner, and UTC time. Stop each long-running service in dependency order; do not use `down`:

```powershell
$approvedProjectName = Read-Host 'Unchanged approved Compose project name'
$restoreProjectName = "${approvedProjectName}-restore-verify"
$approvedProtectedEnv = (Resolve-Path (Read-Host 'Approved protected environment file')).Path
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
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
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
```

Repeat database readiness, role, static, HTTPS, and business smoke before the approved base-Compose Nginx recreation reopens writes. If any service fails, keep writes stopped and use the rollback guide. Never change `KARIZ_COMPOSE_PROJECT_NAME`, delete a container volume, or start a second project as a recovery shortcut.

## Evidence boundary

Repository tests, deploy checks, migration plans, and source review are repository proof. Container health, PostgreSQL migration/restore, Nginx routing, HTTPS/HSTS, browser behavior, capacity, and restart recovery are external proof. Record each separately. Never call a release production-ready from repository proof alone.

Use the [release checklist](RELEASE_CHECKLIST.md) for go/no-go and the [rollback guide](ROLLBACK.md) for a failed gate.
