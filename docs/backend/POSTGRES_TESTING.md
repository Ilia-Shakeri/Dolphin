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

The harness runs Django checks, migration drift detection, and the full test suite against the temporary PostgreSQL cluster. It stops the cluster in `finally` and removes only the validated `dolphin-pgtest-<random-token>` temporary directory.

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

### Resolved blocker: the interactive password step

The role bootstrap, contract, dump, and restore stages used to stop on Windows.
`scripts/bootstrap-postgres.sh` sets role passwords with psql's interactive
`\password` meta-command, which reads the console device rather than piped stdin
and therefore blocks forever here. Proven in isolation:

```text
printf 'pw\npw\n' | psql ... -c "SET password_encryption='scram-sha-256'" \
                             -c "\password role"
-> times out; pg_stat_activity shows state=idle, wait_event=Client/ClientRead
```

This was a portability limitation, not a production defect: the production
target is a Linux container, where piped stdin works. Earlier runs never reached
this stage because the harness stopped at failing tests first.

**Production behaviour is unchanged.** `\password` is still what the Compose
`db-bootstrap` service runs, and it is still chosen precisely so a plaintext
password never reaches the server or its log. What was added is an opt-in
branch that is unreachable from any production configuration:

- it runs only when `DOLPHIN_BOOTSTRAP_NONINTERACTIVE_PASSWORD=1` is set
  explicitly, and any other non-empty value aborts the bootstrap;
- even then it refuses unless `POSTGRES_DB` matches
  `(test|contract|restore)_dolphin_<32 hex>`, every managed role matches
  `dolphin_(migration|app|backup)_<32 hex>`, the host is `127.0.0.1`, and the port
  is a high port other than 5432 — values a production deployment cannot have;
- it derives the identical SCRAM-SHA-256 verifier on the client with
  `scripts/pg_scram_verifier.py`, so the plaintext still never reaches the
  server; the password is passed on that helper's stdin and never as an
  argument or an SQL literal;
- it then asserts the stored `pg_authid.rolpassword` really is a
  `SCRAM-SHA-256$...` verifier, and aborts if it is not.

There is no fallback: any unmet condition ends the bootstrap with a non-zero
exit rather than choosing a weaker method. `DOLPHIN_BOOTSTRAP_NONINTERACTIVE_PASSWORD`
appears in no Compose file and in no `.env.example`, and the `db-bootstrap`
container mounts only the bootstrap script, so the verifier helper it requires
is not even present there. Covered by
`common/tests/test_database_privileges.py` and
`common/tests/test_pg_scram_verifier.py`.

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
- the data path must match the `dolphin-pgtest-<guid>` prefix, checked both before
  creation and again before deletion, and it throws instead of deleting anything
  outside that prefix;
- it binds `127.0.0.1` only, on a random high port, and explicitly rejects 5432
  and any port ≤ 1024;
- database names, role names, and passwords are all bound to a random run token;
- `config/postgres_test_guard.py` independently re-validates the flag, token
  format, loopback host, non-5432 high port, token-matched database name, and
  the `dolphin_test_` user prefix, so a misconfigured environment fails closed;
- every touched environment variable and `PATH` is saved and restored in
  `finally`, the cluster is stopped in `finally`, and no password is printed.

Confirmed by execution: with the tooling absent the harness aborts at tool
resolution (`CommandNotFoundException` on `initdb`) and does **not** fall back to
any other server.

### Coverage gap found while auditing — closed

The harness used to prove only that the backup role can `pg_dump`; it never
called `pg_restore`. The only restore verifier,
`scripts/verify-postgres-restore.sh`, is container-bound (fixed `/backups` and
`/ops` mounts, a `.dolphin-backup-root` sentinel), so it belongs to the Compose
`restore-verify` profile and cannot run natively on Windows.

A native restore step now runs inside the harness: it creates a second, separately
named ephemeral database, restores the dump into it with `pg_restore
--exit-on-error --single-transaction`, and then checks that the restored database
is genuinely usable — schema contract, migration-state hash equal to the source,
sentinel rows and their cross-table relationships intact, the ordinary
application login able to read and write it through both psql and Django, and no
privilege gained by the runtime role through the restore. The restore database
name must pass the same ephemeral-name guard before it is created and again
before it is dropped.

Two notes on defects this uncovered, both in the harness rather than the
application: the sentinel step passed a Windows shell's mangled argument to
`manage.py shell -c` (now a generated file executed directly), and it passed
`phone=` as a string where `create_customer_with_phone` takes a mapping.

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
