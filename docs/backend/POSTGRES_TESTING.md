# Isolated PostgreSQL testing

Use `scripts/test-postgres.ps1` only with native PostgreSQL tools available. The harness never reads `.env`, Compose settings, persistent volumes, or the normal `POSTGRES_*` variables.

It creates a new cluster under the operating-system temporary directory, binds only `127.0.0.1`, selects a random high port other than 5432, and binds the test database name to a random run token. `config/postgres_test_settings.py` rejects any host, port, user, or database name outside that contract.

Run:

```powershell
powershell -NoProfile -File scripts/test-postgres.ps1
```

If PostgreSQL tools are not on `PATH`:

```powershell
powershell -NoProfile -File scripts/test-postgres.ps1 -PostgresBin 'C:\Program Files\PostgreSQL\17\bin'
```

The harness runs Django checks, migration drift detection, and the full test suite against the temporary PostgreSQL cluster. It stops the cluster in `finally` and removes only the validated `kariz-pgtest-<random-token>` temporary directory.

SQLite test success is logic proof only. Harness success is local PostgreSQL migration, constraint, transaction, and query proof. Neither is production deployment proof.

## Current status (phase P0R.2, 2026-08-15)

`RUNTIME_UNPROVED` — the harness cannot run on the current development host.

Verified by direct probe on this host, not assumed:

```text
psql        MISSING
initdb      MISSING
pg_ctl      MISSING
pg_dump     MISSING
pg_restore  MISSING
docker      MISSING
docker-compose MISSING
C:\Program Files\PostgreSQL   does not exist
C:\Program Files\Docker       does not exist

python 3.14.5
django 5.2.17
psycopg 3.2.13   <- driver present, server tooling absent
```

The exact blocker is the absence of PostgreSQL **server** binaries. The Python
driver is installed, so the application can already talk to a PostgreSQL server
that exists elsewhere; what is missing is the ability to create a local
cluster, which `scripts/test-postgres.ps1` requires (`initdb`, `pg_ctl`,
`psql`, `createdb`, `pg_dump`).

Note also that this host runs Python 3.14.5 while the production image pins
CPython 3.13 (`Dockerfile` rejects any other minor version). Local results are
therefore proof of logic, not of the exact production interpreter.

### To clear this blocker

Either is sufficient; no application code change is involved.

1. **Install PostgreSQL locally.** Any currently supported major version. The
   harness auto-detects tools on `PATH`, or accepts an explicit path:

   ```powershell
   powershell -NoProfile -File scripts/test-postgres.ps1 -PostgresBin 'C:\Program Files\PostgreSQL\17\bin'
   ```

2. **Provision a staging host** with PostgreSQL, or with Docker so the
   `compose.yml` stack can run. A staging host additionally unblocks P13.

### What clearing it unblocks

- The PostgreSQL-only tests that currently skip in every local run.
- The `P0R.2` completion gate: migrations, constraints, transaction semantics,
  row locking, concurrency harness, database roles, backup, isolated restore.
- Phase `P4` (Inventory) cannot be declared complete on SQLite evidence alone,
  because its correctness depends on concurrency behaviour that SQLite does not
  reproduce. Until this gate is green, P4 output is "local-only, PostgreSQL
  proof outstanding".

