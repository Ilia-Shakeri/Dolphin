# Synthetic UAT data

The UAT seed command creates one fixed, obviously synthetic CRM graph for acceptance checks. It never deletes, resets, updates, or overwrites rows.

## Hard guards

The command runs only when every guard passes:

1. `KARIZ_ALLOW_UAT_SEED` equals `1`.
2. `--confirm-synthetic-data` is present.
3. The database is either the repo test settings' Django in-memory database or PostgreSQL with a lowercase safe name shaped like `uat_kariz_team_1`.
4. User, Customer, Product Category, Product, Lead, Interaction, Sale, After-sales Request, and ActivityLog tables are all empty.
5. `KARIZ_UAT_PASSWORD` is present and passes the configured Django password validators for all five fixed identities.

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

- Five active CRM identities across the four fixed role codes: one sales/call-center Sales Agent, one bounded after-sales Sales Agent, one Sales Manager, one Company IT, and one Platform Admin.
- Both operator identities keep the `sales_agent` role. Their fixed workstreams are `sales` and `after_sales`; no fifth role or dynamic permission is created.
- All five remain outside Django admin with `is_staff=false` and `is_superuser=false`.
- One Persian synthetic Customer with one synthetic primary phone.
- One Persian synthetic Product Category and one categorized Product.
- One Lead assigned by the Sales Manager to the Sales Agent.
- One Interaction by that Sales Agent.
- One confirmed Sale for two units of the synthetic Product.
- One open after-sales case linked to that Customer and Sale and assigned to the bounded after-sales operator.
- Safe audit rows for seeded users and service-managed actions. No plaintext password enters audit data.

## Separate acceptance personas

Run and record each persona separately against the same exact isolated release artifact:

1. `uat_platform_admin`: platform home, full clean CRM identity custody, audit, and all shipped business modules.
2. `uat_sales_manager`: store-manager home, company scope, both Sales Agent identities, reports, catalog management, and after-sales management; no platform audit custody.
3. `uat_sales_agent`: assigned Lead/work queue, permitted Customer, Interaction, own Sale, read-only catalog, and own report; no user administration or audit.
4. `uat_after_sales_operator`: assigned after-sales case only; no unrelated Customer, Sale, sales report, user administration, or audit navigation/data.

The release record must bind browser evidence, PostgreSQL database identity, Compose image digests, public host, and time to the exact candidate. Repository test execution alone does not complete target UAT.

This fixture is only for isolated UAT. It is not a production bootstrap, demo reset, migration, or recovery tool.
