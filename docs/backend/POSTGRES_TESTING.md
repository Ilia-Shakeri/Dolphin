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

