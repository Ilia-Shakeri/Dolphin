# Incident response

Status: repository response guide complete; contacts, external secret systems, host controls, and live drills remain deployment inputs.

## Roles and first actions

Assign one incident commander, operations owner, security owner, business owner, and evidence custodian. One person may hold several roles, but ownership must be explicit.

For every incident:

1. record UTC start time, detection source, release reference, affected routes, request IDs, and known user impact;
2. restrict evidence access and preserve original logs/audit data;
3. stop risky releases and business writes through the approved maintenance path when integrity is uncertain;
4. do not destroy containers, volumes, databases, backups, or Git history;
5. choose containment from evidence, not from guess;
6. keep status claims split into observed, inferred, and proved.

The repository has a reversible edge write-stop. Base Compose keeps it off; the approved override turns it on. It is an edge write block, not a maintenance page or database lock.

## Safe first checks

```powershell
docker compose ps --all
docker compose logs --no-color --tail 200 web nginx db db-bootstrap migrate db-finalize
```

Application `/api/v1/health/live/` proves process response only. `/api/v1/health/ready/` runs a database query. Nginx `/health/live/` proves only the edge process path. A green liveness result does not prove database, TLS, authentication, or business-flow health.

Treat all command output as restricted. Do not print `.env`, database connection strings, cookies, headers, request bodies, customer fields, or raw audit rows into shared tickets.

## Reversible edge write-stop

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

## Suspected credential exposure

1. Do not copy, quote, test, or transmit the suspected value.
2. Restrict access to the source location and preserve path, time, actor, and access metadata without preserving the value in the ticket.
3. Identify the exact credential owner, service, environment, privileges, and possible exposure window.
4. Have the owner rotate or revoke it in the real secret/database/certificate provider. The repository cannot prove external rotation.
5. Update the protected deployment source, restart only affected services through the approved change path, and test health plus authentication.
6. Verify that the old credential is rejected and the new credential works before marking rotation complete.
7. Decide whether sessions, certificates, database roles, or other dependent credentials also need invalidation.
8. If source or Git may contain the value, preserve evidence and get an approved history-remediation plan. Do not rewrite history during triage.

Local scans, file edits, or service restart are not credential rotation. Never state that rotation is done without provider-side proof.

## Database outage or readiness failure

1. Compare Nginx liveness, application liveness, and application readiness.
2. Inspect `db` health, recent database/application logs, host disk capacity, memory pressure, network state, and credential validity through approved host tools.
3. Determine whether failure is availability-only or whether data integrity may be affected.
4. Do not recreate PostgreSQL, remove `postgres_data`, rerun initialization, or restore over the database.
5. If restart is approved, first prove storage and recovery-point safety. Preserve pre-restart logs.
6. After recovery, require readiness, migration state, role isolation, core business flow, audit continuity, and fresh backup checks.

If integrity is unclear, keep writes stopped and use the new-database recovery path in [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

## Bad deploy or migration

1. Freeze further release work and use the approved edge write-stop if writes may worsen impact.
2. Record current/prior release references, migration service exit, and migration state.
3. Inspect the read-only migration plan:

```powershell
docker compose run --rm --no-deps migrate python manage.py showmigrations --plan
```

4. Decide between a forward fix, schema-compatible prior application, reviewed migration rollback, or restore into a new recovery database.
5. Follow [ROLLBACK.md](ROLLBACK.md). Do not issue a generic reverse migration or change migration-table rows.
6. Reopen traffic only after readiness, role, business, audit, report, static, TLS, and browser acceptance gates pass.

## Backup failure

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

## Audit and log handling

- Application request logs contain only event, request ID, method, path, status, and duration. The production Django/root fallback stream uses only UTC time, fixed event, logger, level, request ID, method, path, and exception type; it drops record messages, arguments, exception text, and tracebacks. Both streams omit query, body, headers, and client IP.
- Nginx request logs are structured on container stdout and omit query, referrer, and browser-agent data, but contain peer address and timing. Alert-level Nginx errors go to container stderr. Treat both streams as restricted.
- PostgreSQL runs with statement, sampled/slow statement, parameter, connection, disconnection, and duration logging disabled; only panic-level statements can be included in error logs. Preserve a reviewed copy of the effective command with runtime evidence, but never weaken these controls during incident triage.
- ActivityLog is append-only through the application and may contain actor, object, safe changes, request ID, and trusted IP. Do not edit or delete it during response.
- Correlate edge, application, and ActivityLog records by request ID and UTC time. Keep source timestamps and timezone clear.
- Compose log caps are finite. Preserve relevant evidence promptly in an approved restricted store before rotation, with access record and integrity hash.
- Do not place raw logs, customer data, credentials, cookies, or headers in chat, email, or public issue systems.

No central log archive or incident evidence store is configured by this repository. Its retention, access, and deletion rules are external production requirements.

## Recovery and closure

Before closure, record:

- impact window and affected data/users;
- confirmed cause and contributing controls;
- containment and recovery actions with owners and times;
- credential provider proof when rotation occurred;
- database readiness and business acceptance evidence;
- latest verified backup and restore result;
- audit/log preservation location and access owner;
- follow-up fixes, tests, deadlines, and decision owners.

Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) before any recovery release. Do not call the incident closed while data integrity, credential status, or recovery-point validity remains unknown.
