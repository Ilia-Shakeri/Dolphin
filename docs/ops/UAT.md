# Synthetic UAT data

The UAT seed command creates one fixed, obviously synthetic CRM graph for acceptance checks. It never deletes, resets, updates, or overwrites rows.

## Hard guards

The command runs only when every guard passes:

1. `KARIZ_ALLOW_UAT_SEED` equals `1`.
2. `--confirm-synthetic-data` is present.
3. The database is either the repo test settings' Django in-memory database or PostgreSQL with a lowercase safe name shaped like `uat_kariz_team_1`.
4. User, Customer, Product, Lead, Interaction, Sale, and ActivityLog tables are all empty.
5. `KARIZ_UAT_PASSWORD` is present and passes the configured Django password validators for all four fixed users.

The command checks emptiness again inside the write transaction. A failed row or audit rolls back the full graph. A second run refuses the nonempty database.

## Run

Set a strong password made only for this isolated UAT environment. Do not reuse a real account password. Keep it out of shell history and logs.

PowerShell:

```powershell
$env:KARIZ_ALLOW_UAT_SEED = "1"
$env:KARIZ_UAT_PASSWORD = Read-Host "UAT password" -MaskInput
python manage.py seed_synthetic_uat --confirm-synthetic-data
Remove-Item Env:KARIZ_UAT_PASSWORD
Remove-Item Env:KARIZ_ALLOW_UAT_SEED
```

The success output contains no password or password hash.

## Fixed graph

- Four active CRM users: one Sales Agent, Sales Manager, Company IT, and Platform Admin.
- All four remain outside Django admin with `is_staff=false` and `is_superuser=false`.
- One Persian synthetic Customer with one synthetic primary phone.
- One Persian synthetic Product.
- One Lead assigned by the Sales Manager to the Sales Agent.
- One Interaction by that Sales Agent.
- One confirmed Sale for two units of the synthetic Product.
- Safe audit rows for seeded users and service-managed actions. No plaintext password enters audit data.

This fixture is only for isolated UAT. It is not a production bootstrap, demo reset, migration, or recovery tool.
