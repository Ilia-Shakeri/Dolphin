# Rollback procedure

Status: decision-safe procedure complete; immutable release values and live recovery proof remain external.

This guide never deletes a volume, rewrites the live worktree, reverses a migration by guess, or restores over a business database.

## Required rollback inputs

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

## Triage without mutation

Capture the release reference, request IDs, UTC time window, affected routes, and observed status. Inspect state without changing schema or data:

```powershell
docker compose ps --all
docker compose logs --no-color --tail 200 db-bootstrap migrate db-finalize web nginx db
docker compose run --rm --no-deps migrate python manage.py showmigrations --plan
```

Keep raw logs restricted. Do not paste credentials, environment output, request bodies, customer data, or audit rows into tickets.

## Choose one recovery path

### Application-only rollback

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
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose pull web migrate
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose stop --timeout 30 nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose run --rm --no-deps migrate python manage.py collectstatic --clear --noinput
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose up -d --no-build --no-deps --force-recreate --wait web
if ($LASTEXITCODE -ne 0) { throw 'Prior application failed its health gate.' }
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose ps web
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
```

The explicit one-off command overrides the `migrate` service command and runs only `collectstatic` from the prior image. Stopping Nginx first prevents clients from seeing a half-regenerated shared static volume. If static collection or web health fails, keep Nginx stopped and writes closed; regenerate from the reviewed current or prior image according to the rollback decision. Do not run a schema migration during an application-only rollback.

After prior-image web health, start Nginx with the write-stop override, prove static files and business smoke, and reopen writes only through the approved write-stop procedure. In a new shell with no image override, run quiet Compose validation and prove the durable protected input still selects the prior application release. Record the protected-input change, compatibility review, prior digest, pull, static regeneration, recreate, health, and smoke. This path does not alter the database volume.

### Edge/config-only rollback

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
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $currentCompose -f $currentWriteStop exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose -f $priorWriteStop config --quiet
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose pull nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose -f $priorWriteStop up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose -f $priorWriteStop exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose ps nginx web db
```

Prove edge liveness, HTTPS/TLS, request IDs, safe errors, static revalidation, and routing while writes stay closed. After owner approval, reopen writes only from the prior base Compose file and prove its off mount:

```powershell
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose up -d --no-build --no-deps --force-recreate nginx
docker compose --project-name $approvedProjectName --env-file $approvedProtectedEnv -f $priorCompose exec -T nginx grep -F '# kariz-write-stop: off' /etc/nginx/write-stop.conf
```

Record both artifact paths, their release reference, the stable project name, protected-input change if any, and all health/smoke evidence. These commands recreate only `nginx`; they do not recreate `web`, run migrations, or alter database/static volumes. If the prior configuration changes a database or application contract, this path is forbidden; choose a separately reviewed application or database recovery plan.

### Forward fix

Prefer a reviewed forward fix when the current schema is valid and the defect is isolated in application or configuration code. Run the full repository, image, migration-plan, backup, health, and smoke gates again. Do not patch files inside a running container.

### Migration rollback

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

### Database recovery

Use database recovery when schema/data cannot be safely repaired forward. Follow [BACKUP_RESTORE.md](BACKUP_RESTORE.md): verify checksum, restore into a new recovery database, validate ownership and core tables, run release-compatible migrations only after review, perform role/business/audit checks, and obtain owner approval before routing the application to it.

Never restore into the damaged database in place. Keep the prior database and release intact until acceptance and rollback windows close.

## Validation after rollback

Repeat all applicable deployment gates:

- `migrate` job exit code 0 for the selected release;
- application liveness and database readiness;
- Nginx liveness and routing;
- login/logout and CSRF;
- one scoped read per fixed CRM role;
- Customer, Lead assignment, Product, Sale, audit, report, and XLSX critical paths using approved fixtures;
- static, Persian/RTL, Kariz brand, browser console/network, and HTTPS checks;
- backup job and alert path.

Keep the incident open if any gate lacks proof.

## Forbidden rollback actions

- no Compose teardown that removes volumes, database-directory deletion, or broad filesystem delete;
- no live-worktree reset, broad checkout, or history rewrite on the live host;
- no manual edit of applied migration files or migration-table rows;
- no direct production SQL repair without an exact reviewed change and recovery point;
- no in-place restore over the current business database;
- no claim that a rollback worked from process liveness alone.

Use [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) for ownership, evidence, and incident closure.
