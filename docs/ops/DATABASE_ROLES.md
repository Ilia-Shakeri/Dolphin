# PostgreSQL role split

The production stack uses four distinct PostgreSQL logins. It does not use the application or backup login as a cluster superuser or schema owner.

| Environment name | Scope | Rights |
| --- | --- | --- |
| `POSTGRES_INIT_USER` | `db`, `db-bootstrap`, and `db-finalize` only | Existing cluster superuser used only by the two one-shot database jobs to create roles, transfer first-party ownership, and set grants |
| `POSTGRES_MIGRATION_USER` | One-shot database jobs and `migrate` only | Database and `public` schema owner; no superuser, role creation, database creation, replication, or inherited role rights |
| `POSTGRES_APP_USER` | One-shot database jobs and long-running `web` only | Exact table row rights and sequence use; no schema creation, cluster rights, or inherited role rights |
| `POSTGRES_BACKUP_USER` | One-shot database jobs and profile-only `backup` job | Read-only dump login with database connect, schema use, and `SELECT` on current/future public tables and sequences; no row writes, routine execution, schema creation, cluster rights, or inherited role rights |

The four names must be safe lowercase PostgreSQL identifiers and must differ. Each password must be private, random, at least 16 characters, and different from the other passwords. Compose passes only the application password to `web`, only the migration password to `migrate`, and only the backup password to `backup`. All four passwords go only to the two role-management jobs. It does not spread the whole `.env` into application containers.

`db-bootstrap` runs before migration. It prepares roles/passwords, then locks one owner/ACL transaction that removes runtime default privileges. `db-finalize` repeats that guarded flow after migration and reapplies the exact table/sequence/routine policy before `web` may start. Owner transfer and every database/schema/table/sequence/routine/default-ACL change run inside the locked unit. Any SQL error closes the session and rolls back that unit.

The exact runtime map gives:

- `SELECT, INSERT` only to ActivityLog, LeadAssignmentHistory, Interaction, and Django admin log;
- `SELECT, INSERT, UPDATE` to mutable CRM and account rows;
- `SELECT, INSERT, UPDATE, DELETE` to Django sessions;
- only the exact extra group-table verbs needed by Django group administration;
- `SELECT` only to migration metadata, content types, and permissions.

Future tables, sequences, and routines receive no runtime rights by default. Existing public-schema routines lose implicit `PUBLIC` and application-role execution rights. `db-finalize` grants sequence use only when its owning table has an exact `INSERT` grant. No runtime routine grant is approved today. Any schema change that needs runtime table or routine access must add an explicit reviewed decision to `scripts/bootstrap-postgres.sh`; the static grant-map test fails when a managed model table is missing.

The backup role is separate from the runtime map. It receives only read rights needed by `pg_dump`: `SELECT` on current public tables and sequences, plus matching migration-owner default privileges for future tables and sequences. It gets no `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, DDL, routine execution, role membership, or row-security bypass. Run a real dump after every schema or PostgreSQL security change; source ACL checks cannot prove `pg_dump` against the target engine.

## New database

Set all names and secrets through the protected deployment secret process. Create one approved, explicitly named Docker volume, set that exact name as `POSTGRES_DATA_VOLUME`, and record it as durable infrastructure. Compose marks this volume external and refuses to create it. This prevents a changed checkout path or Compose project name from silently starting an empty database.

```powershell
$approvedVolume = Read-Host 'Approved new PostgreSQL volume name'
docker volume create $approvedVolume
```

Do this only for a reviewed new installation. Do not run it while adopting an existing database. On the empty named volume, the PostgreSQL image creates `POSTGRES_INIT_USER`. `db-bootstrap` creates the migration, application, and backup roles and prepares narrow defaults, `migrate` builds the schema as its owner, and `db-finalize` applies the exact runtime and backup policy. `web` cannot start until all three one-shot steps succeed.

The long-running `web` container has a read-only root filesystem and a read-only static mount. Only its bounded `/tmp` mount is writable. The `migrate` container keeps the static mount writable for collection.

## Existing named volume

Do not delete, replace, or reinitialize `postgres_data`.

The bundled backup login does not exist before the first in-place role job. The recovery point required below must use the already approved database-owner or legacy backup path. Do not run bootstrap first merely to make the new backup role; that would mutate ownership and ACLs before the recovery gate. After adoption succeeds, use the bundled job in [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

1. Make and verify a fresh recovery point using [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
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

## Secret rotation

The one-shot database jobs rotate the migration, application, and backup passwords to the protected values and reapply their attributes and grants. The PostgreSQL image does not rotate the init login on an existing volume. Rotate that credential through a separately approved database-owner procedure, then update the protected secret in the same maintenance change. Never put a password in a command argument, migration, log, ticket, or repository file.

## Evidence boundary

Source tests prove the intended Compose secret scope, transaction boundary, table map, backup-read map, and grant policy only. A real PostgreSQL run must still prove role creation, ownership, advisory-lock serialization, injected-failure rollback, migration success, session login/logout, allowed CRM writes, a complete backup-role dump, denied backup writes/DDL/routine execution, denied application DDL and routine execution, denied audit/history update-delete, restart behavior, and in-place upgrade against a disposable copy of production-like data.
