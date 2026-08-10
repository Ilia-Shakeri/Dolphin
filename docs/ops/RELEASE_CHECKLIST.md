# Release checklist

Status values: `PASS`, `FAIL`, `BLOCKED_EXTERNAL`, `BLOCKED_DECISION`, or `NOT_RUN`. Every `PASS` needs dated evidence tied to one exact release reference.

Any `FAIL`, missing recovery point, unresolved P0/P1 defect, or unapproved data/credential/TLS decision is no-go.

## Release identity and ownership

- [ ] Exact commit/release artifact recorded and reviewed.
- [ ] Prior release artifact exists outside the live worktree.
- [ ] One approved `KARIZ_COMPOSE_PROJECT_NAME` is recorded and unchanged across current, restart, rollback, and prior-artifact commands; restore verification uses only its derived `-restore-verify` project.
- [ ] Release, database, security, business, rollback, and evidence owners named.
- [ ] Maintenance window, user notice, success window, and abort threshold approved.
- [ ] Known limitations and open decisions reviewed for this release.

## Repository gates

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
- [ ] The exact-commit source-secret scan, locked-dependency advisory scan, per-image SBOM and vulnerability scans for the exact application, PostgreSQL, and Nginx digests, recorded Python build-base digest, and public TLS scan passed review through [SECURITY_SCANS.md](SECURITY_SCANS.md); all evidence is digest-bound and sealed.
- [ ] Diff and staged-file review has no forbidden secret, database, backup, generated, or excluded archive artifact.

Repository gates do not prove PostgreSQL, containers, proxy, TLS, or browser behavior.

## Environment and security gates

- [ ] Protected `.env` exists through the approved secret process and is not printed or committed.
- [ ] Exact external backup volume, managed backup role/secret, explicit retention-days value, and disposable-restore tmpfs byte limit are approved; no other base service receives the backup password or mounts the backup volume.
- [ ] Required secret, host, HTTPS CSRF origin, database, timeout, HSTS, and proxy inputs pass strict production validation.
- [ ] Allowed hosts contain only `KARIZ_PUBLIC_HOST`; CSRF origins contain only `https://KARIZ_PUBLIC_HOST`, with no wildcard, dot prefix, sibling, port, slash, or extra entry.
- [ ] Approved certificate chain/key files are mounted read-only and pass the [TLS procedure](TLS.md).
- [ ] Exact trusted proxy CIDR matches the approved one-proxy topology; no wildcard host or broad trust range.
- [ ] Trusted proxy validation rejects both IPv4 and IPv6 `/0` networks.
- [ ] HTTPS termination and forwarded-scheme behavior proved before secure session/CSRF smoke.
- [ ] HSTS value approved only after stable HTTPS proof; preload has separate explicit approval.
- [ ] Database is not published to the host or public network.
- [ ] Application runs as the non-root image user.
- [ ] Django/root default logs use the bounded safe formatter; application and edge logs omit query/body/header secrets and retain request-ID correlation.
- [ ] Nginx access logs reach container stdout, Nginx error logs reach stderr, and PostgreSQL statement, sampled/slow statement, parameter, connection, disconnection, and duration logging are disabled by the reviewed Compose command.
- [ ] Container log caps, external log retention, access, and alert path proved.

## Database and recovery gates

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

Use [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Guard/parser tests alone do not pass the real backup/restore gates.

## Container and edge gates

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
- [ ] Base Compose mounted `# kariz-write-stop: off`; override Compose mounted `# kariz-write-stop: on` at `/etc/nginx/write-stop.conf`.
- [ ] With stop on, edge health `GET`/`HEAD` stayed live and safe-path `POST`/`PUT`/`PATCH`/`DELETE` each returned stable JSON `503` with matching header/body request IDs.
- [ ] With stop off again, the safe write probe no longer returned the edge write-stop response.
- [ ] Restart-policy and bounded-log behavior proved.

Do not use a Compose teardown that removes volumes or remove `postgres_data`/`static_data` during release testing.

## Initial access gate

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

## Health, authorization, and product gates

- [ ] Nginx `/health/live/` passed through the deployed edge.
- [ ] Application `/api/v1/health/live/` passed.
- [ ] Database-backed `/api/v1/health/ready/` passed.
- [ ] HTTPS, certificate, fixed-host redirect, secure cookies, CSRF, HSTS, old-protocol denial, and scanner behavior passed through the real public path.
- [ ] Login/logout/inactive denial passed.
- [ ] Sales Agent, Sales Manager, Company IT, and Platform Admin list/detail/write/action/filter scope passed with approved non-production fixtures.
- [ ] Customer/phone uniqueness, Lead assignment/history, Interaction append-only, positive Product, Sale create/cancel, and audit critical paths passed.
- [ ] Report JSON/XLSX scope, formulas, non-enumerating Product filter, exact money text, parity, cache, and download passed.
- [ ] Persian/RTL root/admin, Kariz brand, static assets, target viewports, and clean browser console/network passed.
- [ ] Capacity/load target passed on production-shaped infrastructure through the bounded read-only procedure in [LOAD_TEST.md](LOAD_TEST.md), or through one separately approved exact tool and contract, with external resource and abort evidence.

## Rollback and incident gates

Run this exact reversible edge drill only on the approved target. Use the no-body safe probes from [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md), not a business route:

```powershell
docker compose -f compose.yml -f compose.write-stop.yml config --quiet
docker compose -f compose.yml -f compose.write-stop.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml -f compose.write-stop.yml exec -T nginx grep -F '# kariz-write-stop: on' /etc/nginx/write-stop.conf
docker compose -f compose.yml up -d --no-deps --force-recreate nginx
docker compose -f compose.yml exec -T nginx grep -F '# kariz-write-stop: off' /etc/nginx/write-stop.conf
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
- [ ] Rollback and incident tabletop completed against [ROLLBACK.md](ROLLBACK.md) and [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).

## Evidence result

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

Use [DEPLOYMENT.md](DEPLOYMENT.md) for execution. Use [ROLLBACK.md](ROLLBACK.md) and [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) for abort and recovery.
