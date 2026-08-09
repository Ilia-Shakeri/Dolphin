# Platform Admin bootstrap

This command is for a server operator creating the first-ever CRM Platform Admin. It refuses to run when any active or inactive Platform Admin row already exists. It is not an HTTP endpoint and is not a normal user-management path.

## Before use

1. Apply database migrations.
2. Open a private server terminal attached to the intended deployment database.
3. Confirm no Platform Admin row, active or inactive, exists.
4. Keep the password out of shell history, environment files, process arguments, tickets, and logs.

## Run

From the deployed application environment:

```sh
python manage.py bootstrap_platform_admin --username admin_name
```

For the Compose deployment:

```sh
docker compose exec web python manage.py bootstrap_platform_admin --username admin_name
```

The command asks for the password twice without terminal echo. It has no password argument. Django password validators must accept the value.

## Result and guardrails

- The command works only before any CRM Platform Admin row exists.
- An existing username is never reused, including an inactive account.
- The account receives CRM role `platform_admin`.
- The account remains outside Django admin: `is_staff=false` and `is_superuser=false`.
- Account creation and its system audit row commit in one database transaction.
- The audit actor is null because no CRM user exists to perform first bootstrap. The audit stores field names and a password-set flag, never the password.
- Later user and role work must use the normal authorized CRM paths. This command is not a lockout-recovery or role-escalation tool. Recovery after an existing Platform Admin is disabled or lost needs an approved incident procedure.
