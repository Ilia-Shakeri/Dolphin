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

PostgreSQL 17.11 was provisioned on the developer host, and most of the proof
now passes. One step remains blocked; see "Remaining blocker" below.

Executed with `-PostgresBin` pointing at a developer-controlled 17.11 tree (not
installed as a service, not on machine `PATH`, and not a production contract):

```text
full suite on PostgreSQL      404 tests, OK, 6 skipped
full suite on SQLite          404 tests, OK, 7 skipped
7 PostgreSQL-only tests       all execute and pass
fresh migrations from zero    correct; no migration drift
health/readiness              200 healthy, 503 unavailable, no credential leak
browser matrix                runs and passes against PostgreSQL
```

The first PostgreSQL run produced 10 failures and 18 errors. Every one was a
defect in a test or in test configuration, not in the application; the fixes are
in commit `fix: make the test suite pass on real postgresql`. The most serious
was a migration test that left the schema downgraded for all later tests,
which SQLite hid because that test was always skipped there.

Observed SQLite/PostgreSQL differences that matter to this codebase: PostgreSQL
enforces `varchar` length while SQLite ignores it; real query latency (tens to
hundreds of milliseconds rather than microseconds) exposes frontend races;
`TransactionTestCase` does not roll back schema changes, so a migration test can
poison every later test.

### Remaining blocker

The role bootstrap, contract, dump, and restore stages do not run on Windows.
`scripts/bootstrap-postgres.sh` sets role passwords with psql's interactive
`\password` meta-command, which on Windows reads the console instead of piped
stdin and therefore blocks forever. Proven in isolation:

```text
printf 'pw\npw\n' | psql ... -c "SET password_encryption='scram-sha-256'" \
                             -c "\password role"
-> times out; pg_stat_activity shows state=idle, wait_event=Client/ClientRead
```

This is a portability limitation, not a production defect: the production target
is a Linux container, where piped stdin works. Earlier runs never reached this
stage because the harness stopped at the failing tests first.

It was deliberately left unchanged. `bootstrap-postgres.sh` is the production
`db-bootstrap` script and `\password` is chosen precisely so a plaintext
password never reaches the server or its logs. Changing it is a product-owner
decision. Options, smallest first:

1. Run the bootstrap, contract, dump and restore stages on Linux (a container or
   VM), keeping the Windows host for the Django suite only.
2. Add an opt-in, harness-only non-interactive branch to the script, so the
   production Compose path keeps using `\password` unchanged.
3. Compute the SCRAM-SHA-256 verifier client-side and use
   `ALTER ROLE ... PASSWORD '<verifier>'`, which keeps the plaintext off the
   wire but is a real change to production tooling.

### Version contract

The repository does specify a version: `docs/ops/DEPLOYMENT.md` states the `db`
service is **PostgreSQL 17**. Use that. The Compose image is pinned by digest
through `KARIZ_POSTGRES_IMAGE`, so the digest — not a tag — is the release
contract. `psycopg[binary]==3.2.13` is the client and imposes no narrower bound.

### Tooling probe

Exhaustively verified on this host, not assumed:

```text
psql pg_dump pg_restore initdb pg_isready pg_ctl createdb postgres   all MISSING
docker                                                              MISSING
C:\Program Files\PostgreSQL, C:\Program Files (x86)\PostgreSQL,
C:\PostgreSQL                                                       absent
Windows service matching *postgres*                                 none
Registry uninstall entries (PostgreSQL/pgAdmin/EnterpriseDB)         none
HKLM:\SOFTWARE\PostgreSQL                                            absent
scoop / chocolatey / LOCALAPPDATA / C:\tools locations               absent
recursive search for psql.exe on C:                                  no match

python 3.14.5 | django 5.2.17 | psycopg 3.2.13  (driver present, server absent)
```

The blocker is the absence of PostgreSQL **server** binaries. The driver is
installed, so the application could already talk to a PostgreSQL server that
exists elsewhere; what is missing is the ability to create a local cluster,
which `scripts/test-postgres.ps1` requires.

Note this host runs Python 3.14.5 while the production image pins CPython 3.13
(`Dockerfile` rejects any other minor version), so local results prove logic,
not the exact production interpreter.

### Harness safety audit (static, passed)

`scripts/test-postgres.ps1` was read in full before any attempt to run it. It
cannot reach a production or pre-existing database:

- it runs `initdb` to build a **new throwaway cluster** under the OS temp
  directory rather than connecting to any existing server;
- the data path must match the `kariz-pgtest-<guid>` prefix, checked both before
  creation and again before deletion, and it throws instead of deleting anything
  outside that prefix;
- it binds `127.0.0.1` only, on a random high port, and explicitly rejects 5432
  and any port ≤ 1024;
- database names, role names, and passwords are all bound to a random run token;
- `config/postgres_test_guard.py` independently re-validates the flag, token
  format, loopback host, non-5432 high port, token-matched database name, and
  the `kariz_test_` user prefix, so a misconfigured environment fails closed;
- every touched environment variable and `PATH` is saved and restored in
  `finally`, the cluster is stopped in `finally`, and no password is printed.

Confirmed by execution: with the tooling absent the harness aborts at tool
resolution (`CommandNotFoundException` on `initdb`) and does **not** fall back to
any other server.

### Coverage gap found while auditing

The harness proves the backup role can `pg_dump`, but it never calls
`pg_restore`. The only restore verifier, `scripts/verify-postgres-restore.sh`,
is container-bound: it hardcodes the `/backups` and `/ops` mounts and requires a
`.kariz-backup-root` sentinel, so it belongs to the Compose `restore-verify`
profile and cannot run natively on Windows.

Therefore, even once PostgreSQL is installed, the "isolated restore" half of the
P0R.2 gate needs one of:

- Docker plus the Compose `restore-verify` profile, or
- a small native restore step added to the harness (`createdb` a second
  database, `pg_restore` the dump into it, then run
  `scripts/verify-postgres-schema.sql` against it).

This is a tooling gap, not an application defect.

### To clear the blocker

The harness accepts an explicit binary directory, so a full installer is not
required:

```powershell
# Option A - no admin install: extract the PostgreSQL 17 Windows binaries
# archive anywhere, then point the harness at its bin directory.
powershell -NoProfile -File scripts/test-postgres.ps1 -PostgresBin 'C:\pgsql\bin'

# Option B - normal installer, tools on PATH
powershell -NoProfile -File scripts/test-postgres.ps1
```

Option A installs no service, writes no registry entry, and needs no
administrator rights; the harness creates and destroys its own cluster. A
disposable developer VM is equally acceptable. Docker is not required except for
the container-bound restore verifier described above.

### What clearing it unblocks

- The 7 PostgreSQL-only tests, whose sole skip condition is
  `connection.vendor == "postgresql"`.
- The `P0R.2` gates: fresh migration, constraints, transaction semantics, row
  locking, concurrency, the four-role privilege contract, dump, and restore.
- Phase `P4` (Inventory) cannot be declared complete on SQLite evidence alone,
  because its correctness depends on concurrency behaviour SQLite does not
  reproduce. Until this gate is green, P4 output is "local-only, PostgreSQL
  proof outstanding".

