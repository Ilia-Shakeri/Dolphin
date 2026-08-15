#!/bin/sh
set -eu

require_value() {
    value_name="$1"
    value="$2"
    if [ -z "$value" ]; then
        echo "$value_name must be set." >&2
        exit 2
    fi
}

require_secret() {
    value_name="$1"
    value="$2"
    require_value "$value_name" "$value"
    if [ "${#value}" -lt 16 ]; then
        echo "$value_name must be at least 16 characters." >&2
        exit 2
    fi
}

require_identifier() {
    value_name="$1"
    value="$2"
    require_value "$value_name" "$value"
    if [ "${#value}" -gt 63 ] || \
       printf '%s' "$value" | LC_ALL=C grep -Eq '^pg_' || \
       ! printf '%s' "$value" | LC_ALL=C grep -Eq '^[a-z_][a-z0-9_]*$'; then
        echo "$value_name must be a safe lowercase PostgreSQL identifier." >&2
        exit 2
    fi
}

require_value POSTGRES_HOST "${POSTGRES_HOST:-}"
require_value POSTGRES_PORT "${POSTGRES_PORT:-}"
require_identifier POSTGRES_DB "${POSTGRES_DB:-}"
require_identifier POSTGRES_INIT_USER "${POSTGRES_INIT_USER:-}"
require_identifier POSTGRES_MIGRATION_USER "${POSTGRES_MIGRATION_USER:-}"
require_identifier POSTGRES_APP_USER "${POSTGRES_APP_USER:-}"
require_identifier POSTGRES_BACKUP_USER "${POSTGRES_BACKUP_USER:-}"
require_secret POSTGRES_INIT_PASSWORD "${POSTGRES_INIT_PASSWORD:-}"
require_secret POSTGRES_MIGRATION_PASSWORD "${POSTGRES_MIGRATION_PASSWORD:-}"
require_secret POSTGRES_APP_PASSWORD "${POSTGRES_APP_PASSWORD:-}"
require_secret POSTGRES_BACKUP_PASSWORD "${POSTGRES_BACKUP_PASSWORD:-}"

if [ "$POSTGRES_INIT_USER" = "$POSTGRES_MIGRATION_USER" ] || \
   [ "$POSTGRES_INIT_USER" = "$POSTGRES_APP_USER" ] || \
   [ "$POSTGRES_INIT_USER" = "$POSTGRES_BACKUP_USER" ] || \
   [ "$POSTGRES_MIGRATION_USER" = "$POSTGRES_APP_USER" ] || \
   [ "$POSTGRES_MIGRATION_USER" = "$POSTGRES_BACKUP_USER" ] || \
   [ "$POSTGRES_APP_USER" = "$POSTGRES_BACKUP_USER" ]; then
    echo "PostgreSQL role names must be distinct." >&2
    exit 2
fi
if [ "$POSTGRES_INIT_PASSWORD" = "$POSTGRES_MIGRATION_PASSWORD" ] || \
   [ "$POSTGRES_INIT_PASSWORD" = "$POSTGRES_APP_PASSWORD" ] || \
   [ "$POSTGRES_INIT_PASSWORD" = "$POSTGRES_BACKUP_PASSWORD" ] || \
   [ "$POSTGRES_MIGRATION_PASSWORD" = "$POSTGRES_APP_PASSWORD" ] || \
   [ "$POSTGRES_MIGRATION_PASSWORD" = "$POSTGRES_BACKUP_PASSWORD" ] || \
   [ "$POSTGRES_APP_PASSWORD" = "$POSTGRES_BACKUP_PASSWORD" ]; then
    echo "PostgreSQL role passwords must be distinct." >&2
    exit 2
fi

# --- Disposable-proof non-interactive password path (opt-in, fail-closed) ----
#
# Production sets role passwords with psql's interactive `\password`, which
# hashes on the client so no plaintext password ever reaches the server or its
# log. That meta-command reads the console device directly and ignores piped
# stdin on some platforms, so the isolated PostgreSQL proof harness cannot drive
# it there and the bootstrap -> contract -> dump -> restore proof cannot finish.
#
# When, and only when, the caller opts in explicitly AND every value in play
# belongs to a disposable proof cluster, the same client-side hash is computed
# by scripts/pg_scram_verifier.py instead and applied as a SCRAM verifier. The
# plaintext still never reaches the server. Any unmet condition aborts the whole
# bootstrap; there is no fallback to a weaker method, and production is
# unreachable from this branch because a production database and role name can
# never match the disposable-proof patterns below.
NONINTERACTIVE_PASSWORD="${KARIZ_BOOTSTRAP_NONINTERACTIVE_PASSWORD:-0}"
EPHEMERAL_DB_PATTERN='^(test|contract|restore)_kariz_[0-9a-f]{32}$'
EPHEMERAL_ROLE_PATTERN='^kariz_(migration|app|backup)_[0-9a-f]{32}$'
VERIFIER_PATTERN='^SCRAM-SHA-256\$[0-9]+:[A-Za-z0-9+/]+=*\$[A-Za-z0-9+/]+=*:[A-Za-z0-9+/]+=*$'

refuse_noninteractive() {
    echo "$1" >&2
    echo "Refusing the non-interactive password path." >&2
    exit 2
}

require_ephemeral_proof_context() {
    printf '%s' "$POSTGRES_DB" | LC_ALL=C grep -Eq "$EPHEMERAL_DB_PATTERN" || \
        refuse_noninteractive "POSTGRES_DB is not a disposable Kariz proof database."
    for proof_role in "$POSTGRES_MIGRATION_USER" "$POSTGRES_APP_USER" "$POSTGRES_BACKUP_USER"; do
        printf '%s' "$proof_role" | LC_ALL=C grep -Eq "$EPHEMERAL_ROLE_PATTERN" || \
            refuse_noninteractive "A managed role name is not a disposable Kariz proof role."
    done
    if [ "$POSTGRES_HOST" != "127.0.0.1" ]; then
        refuse_noninteractive "The non-interactive path is limited to the IPv4 loopback host."
    fi
    if ! printf '%s' "$POSTGRES_PORT" | LC_ALL=C grep -Eq '^[0-9]+$' || \
       [ "$POSTGRES_PORT" -le 1024 ] || [ "$POSTGRES_PORT" -ge 65536 ] || \
       [ "$POSTGRES_PORT" -eq 5432 ]; then
        refuse_noninteractive "The non-interactive path requires a high local port other than 5432."
    fi
    if [ -z "${KARIZ_BOOTSTRAP_SCRAM_HELPER:-}" ] || [ ! -f "$KARIZ_BOOTSTRAP_SCRAM_HELPER" ]; then
        refuse_noninteractive "KARIZ_BOOTSTRAP_SCRAM_HELPER must point at the client-side verifier helper."
    fi
    if ! command -v "${KARIZ_BOOTSTRAP_PYTHON:-python3}" >/dev/null 2>&1; then
        refuse_noninteractive "KARIZ_BOOTSTRAP_PYTHON must name an available interpreter."
    fi
}

case "$NONINTERACTIVE_PASSWORD" in
    0)
        ;;
    1)
        require_ephemeral_proof_context
        ;;
    *)
        echo "KARIZ_BOOTSTRAP_NONINTERACTIVE_PASSWORD must be unset, '0', or '1'." >&2
        exit 2
        ;;
esac

export PGPASSWORD="$POSTGRES_INIT_PASSWORD"

emit_variables() {
    printf "\\set db_name '%s'\n" "$POSTGRES_DB"
    printf "\\set init_user '%s'\n" "$POSTGRES_INIT_USER"
    printf "\\set migration_user '%s'\n" "$POSTGRES_MIGRATION_USER"
    printf "\\set app_user '%s'\n" "$POSTGRES_APP_USER"
    printf "\\set backup_user '%s'\n" "$POSTGRES_BACKUP_USER"
}

set_role_password_from_client_hash() {
    # Disposable-proof path only; see the guard block above. The plaintext is
    # piped to the helper on stdin and never becomes an argument, an SQL
    # literal, or a psql variable; only the derived verifier is sent.
    role_name="$1"
    role_password="$2"
    role_verifier=$(printf '%s' "$role_password" | "${KARIZ_BOOTSTRAP_PYTHON:-python3}" "$KARIZ_BOOTSTRAP_SCRAM_HELPER") || \
        refuse_noninteractive "Client-side SCRAM-SHA-256 derivation failed."
    printf '%s' "$role_verifier" | LC_ALL=C grep -Eq "$VERIFIER_PATTERN" || \
        refuse_noninteractive "Client-side SCRAM-SHA-256 derivation produced no usable verifier."

    {
        printf "\\set role_name '%s'\n" "$role_name"
        printf "\\set role_verifier '%s'\n" "$role_verifier"
        cat <<'SQL'
SELECT format('ALTER ROLE %I PASSWORD %L', :'role_name', :'role_verifier') \gexec

SELECT COALESCE(
    (SELECT rolpassword FROM pg_authid WHERE rolname = :'role_name'),
    ''
) LIKE 'SCRAM-SHA-256$%' AS stored_password_is_scram \gset
\if :stored_password_is_scram
\else
    \echo 'The managed role password was not stored as a SCRAM-SHA-256 verifier.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'The managed role password was not stored as a SCRAM-SHA-256 verifier.';
    END $kariz_guard$;
\endif
SQL
    } | psql \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_INIT_USER" \
        --dbname=postgres \
        --no-password \
        --quiet \
        --set=ON_ERROR_STOP=1
    role_verifier=""
}

set_role_password() {
    if [ "$NONINTERACTIVE_PASSWORD" = "1" ]; then
        set_role_password_from_client_hash "$1" "$2"
        return
    fi
    role_name="$1"
    role_password="$2"
    printf '%s\n%s\n' "$role_password" "$role_password" | psql \
        --host="$POSTGRES_HOST" \
        --port="$POSTGRES_PORT" \
        --username="$POSTGRES_INIT_USER" \
        --dbname=postgres \
        --no-password \
        --quiet \
        --set=ON_ERROR_STOP=1 \
        --command="SET password_encryption = 'scram-sha-256'" \
        --command="\\password $role_name"
}

{
    emit_variables
    cat <<'SQL'
SELECT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'init_user' AND rolsuper
) AS init_is_superuser \gset
\if :init_is_superuser
\else
    \echo 'POSTGRES_INIT_USER must be an existing PostgreSQL superuser.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'POSTGRES_INIT_USER must be an existing PostgreSQL superuser.';
    END $kariz_guard$;
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'migration_user'
) OR EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'migration_user'
      AND shobj_description(oid, 'pg_authid') = 'Kariz managed migration role v1'
) AS migration_role_is_managed \gset
\if :migration_role_is_managed
\else
    \echo 'POSTGRES_MIGRATION_USER already exists but is not Kariz-managed.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'POSTGRES_MIGRATION_USER already exists but is not Kariz-managed.';
    END $kariz_guard$;
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'app_user'
) OR EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'app_user'
      AND shobj_description(oid, 'pg_authid') = 'Kariz managed application role v1'
) AS app_role_is_managed \gset
\if :app_role_is_managed
\else
    \echo 'POSTGRES_APP_USER already exists but is not Kariz-managed.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'POSTGRES_APP_USER already exists but is not Kariz-managed.';
    END $kariz_guard$;
\endif

SELECT NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'backup_user'
) OR EXISTS (
    SELECT 1
    FROM pg_roles
    WHERE rolname = :'backup_user'
      AND shobj_description(oid, 'pg_authid') = 'Kariz managed backup role v1'
) AS backup_role_is_managed \gset
\if :backup_role_is_managed
\else
    \echo 'POSTGRES_BACKUP_USER already exists but is not Kariz-managed.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'POSTGRES_BACKUP_USER already exists but is not Kariz-managed.';
    END $kariz_guard$;
\endif

SELECT NOT EXISTS (
    SELECT 1
    FROM pg_auth_members membership
    JOIN pg_roles granted ON granted.oid = membership.roleid
    WHERE granted.rolname IN (:'migration_user', :'app_user', :'backup_user')
) AS managed_roles_have_no_members \gset
\if :managed_roles_have_no_members
\else
    \echo 'A Kariz-managed PostgreSQL role is granted to another role.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'A Kariz-managed PostgreSQL role is granted to another role.';
    END $kariz_guard$;
\endif

SELECT format('CREATE ROLE %I', :'migration_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'migration_user') \gexec
SELECT format('CREATE ROLE %I', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('CREATE ROLE %I', :'backup_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'backup_user') \gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'migration_user'
) \gexec
SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'app_user'
) \gexec
SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS',
    :'backup_user'
) \gexec
SELECT format('ALTER ROLE %I RESET ALL', :'migration_user') \gexec
SELECT format('ALTER ROLE %I RESET ALL', :'app_user') \gexec
SELECT format('ALTER ROLE %I RESET ALL', :'backup_user') \gexec
SELECT format(
    'ALTER ROLE %I SET search_path TO public, pg_catalog',
    :'migration_user'
) \gexec
SELECT format(
    'ALTER ROLE %I SET search_path TO public, pg_catalog',
    :'app_user'
) \gexec
SELECT format(
    'ALTER ROLE %I SET search_path TO public, pg_catalog',
    :'backup_user'
) \gexec
SELECT format(
    'COMMENT ON ROLE %I IS %L',
    :'migration_user',
    'Kariz managed migration role v1'
) \gexec
SELECT format(
    'COMMENT ON ROLE %I IS %L',
    :'app_user',
    'Kariz managed application role v1'
) \gexec
SELECT format(
    'COMMENT ON ROLE %I IS %L',
    :'backup_user',
    'Kariz managed backup role v1'
) \gexec

SELECT format('REVOKE %I FROM %I', granted.rolname, :'migration_user')
FROM pg_auth_members membership
JOIN pg_roles member ON member.oid = membership.member
JOIN pg_roles granted ON granted.oid = membership.roleid
WHERE member.rolname = :'migration_user' \gexec
SELECT format('REVOKE %I FROM %I', granted.rolname, :'app_user')
FROM pg_auth_members membership
JOIN pg_roles member ON member.oid = membership.member
JOIN pg_roles granted ON granted.oid = membership.roleid
WHERE member.rolname = :'app_user' \gexec
SELECT format('REVOKE %I FROM %I', granted.rolname, :'backup_user')
FROM pg_auth_members membership
JOIN pg_roles member ON member.oid = membership.member
JOIN pg_roles granted ON granted.oid = membership.roleid
WHERE member.rolname = :'backup_user' \gexec
SQL
} | psql \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_INIT_USER" \
    --dbname=postgres \
    --no-password \
    --quiet \
    --set=ON_ERROR_STOP=1

set_role_password "$POSTGRES_MIGRATION_USER" "$POSTGRES_MIGRATION_PASSWORD"
set_role_password "$POSTGRES_APP_USER" "$POSTGRES_APP_PASSWORD"
set_role_password "$POSTGRES_BACKUP_USER" "$POSTGRES_BACKUP_PASSWORD"

{
    emit_variables
    cat <<'SQL'
BEGIN;
SELECT pg_advisory_xact_lock(1263684178, 1146243404);

SELECT format('ALTER DATABASE %I OWNER TO %I', :'db_name', :'migration_user') \gexec
SELECT format('ALTER SCHEMA public OWNER TO %I', :'migration_user') \gexec
SELECT format(
    'ALTER ROLE %I IN DATABASE %I RESET ALL',
    :'migration_user',
    :'db_name'
) \gexec
SELECT format(
    'ALTER ROLE %I IN DATABASE %I RESET ALL',
    :'app_user',
    :'db_name'
) \gexec
SELECT format(
    'ALTER ROLE %I IN DATABASE %I RESET ALL',
    :'backup_user',
    :'db_name'
) \gexec

SELECT format(
    'ALTER %s %I.%I OWNER TO %I',
    CASE relation.relkind
        WHEN 'S' THEN 'SEQUENCE'
        WHEN 'v' THEN 'VIEW'
        WHEN 'm' THEN 'MATERIALIZED VIEW'
        WHEN 'f' THEN 'FOREIGN TABLE'
        ELSE 'TABLE'
    END,
    namespace.nspname,
    relation.relname,
    :'migration_user'
)
FROM pg_class relation
JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
JOIN pg_roles owner_role ON owner_role.oid = relation.relowner
WHERE namespace.nspname = 'public'
  AND owner_role.rolname = :'init_user'
  AND relation.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend dependency
      WHERE dependency.classid = 'pg_class'::regclass
        AND dependency.objid = relation.oid
        AND dependency.deptype = 'e'
  )
ORDER BY CASE WHEN relation.relkind IN ('r', 'p') THEN 0 ELSE 1 END, relation.oid
\gexec

SELECT format(
    'ALTER %s %I.%I(%s) OWNER TO %I',
    CASE routine.prokind WHEN 'p' THEN 'PROCEDURE' WHEN 'a' THEN 'AGGREGATE' ELSE 'FUNCTION' END,
    namespace.nspname,
    routine.proname,
    pg_get_function_identity_arguments(routine.oid),
    :'migration_user'
)
FROM pg_proc routine
JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace
JOIN pg_roles owner_role ON owner_role.oid = routine.proowner
WHERE namespace.nspname = 'public'
  AND owner_role.rolname = :'init_user'
  AND NOT EXISTS (
      SELECT 1
      FROM pg_depend dependency
      WHERE dependency.classid = 'pg_proc'::regclass
        AND dependency.objid = routine.oid
        AND dependency.deptype = 'e'
  )
ORDER BY routine.oid
\gexec

SELECT NOT EXISTS (
    SELECT 1
    FROM pg_class relation
    JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
    JOIN pg_roles owner_role ON owner_role.oid = relation.relowner
    WHERE namespace.nspname = 'public'
      AND owner_role.rolname <> :'migration_user'
      AND relation.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
      AND NOT EXISTS (
          SELECT 1
          FROM pg_depend dependency
          WHERE dependency.classid = 'pg_class'::regclass
            AND dependency.objid = relation.oid
            AND dependency.deptype = 'e'
      )
) AS relation_owners_are_safe \gset
\if :relation_owners_are_safe
\else
    \echo 'A first-party public relation has an unapproved owner.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'A first-party public relation has an unapproved owner.';
    END $kariz_guard$;
\endif

SELECT NOT EXISTS (
    SELECT 1
    FROM pg_proc routine
    JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace
    JOIN pg_roles owner_role ON owner_role.oid = routine.proowner
    WHERE namespace.nspname = 'public'
      AND owner_role.rolname <> :'migration_user'
      AND NOT EXISTS (
          SELECT 1
          FROM pg_depend dependency
          WHERE dependency.classid = 'pg_proc'::regclass
            AND dependency.objid = routine.oid
            AND dependency.deptype = 'e'
      )
) AS routine_owners_are_safe \gset
\if :routine_owners_are_safe
\else
    \echo 'A first-party public routine has an unapproved owner.'
    DO $kariz_guard$ BEGIN
        RAISE EXCEPTION 'A first-party public routine has an unapproved owner.';
    END $kariz_guard$;
\endif

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db_name') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM %I', :'db_name', :'app_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'app_user') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM %I', :'db_name', :'backup_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'backup_user') \gexec
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('REVOKE ALL ON SCHEMA public FROM %I', :'app_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format('REVOKE ALL ON SCHEMA public FROM %I', :'backup_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'backup_user') \gexec
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
SELECT format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', :'app_user') \gexec
SELECT format(
    'GRANT %s ON TABLE %I.%I TO %I',
    table_grant.privileges,
    'public',
    table_grant.table_name,
    :'app_user'
)
FROM (
    VALUES
        ('accounts_user', 'SELECT, INSERT, UPDATE'),
        ('accounts_user_groups', 'SELECT, INSERT, DELETE'),
        ('accounts_user_user_permissions', 'SELECT, INSERT, DELETE'),
        ('aftersales_aftersaleshistory', 'SELECT, INSERT'),
        ('aftersales_aftersalesrequest', 'SELECT, INSERT, UPDATE'),
        ('auditlog_activitylog', 'SELECT, INSERT'),
        ('communications_inboundsms', 'SELECT, INSERT'),
        ('auth_group', 'SELECT, INSERT, UPDATE, DELETE'),
        ('auth_group_permissions', 'SELECT, INSERT, DELETE'),
        ('auth_permission', 'SELECT'),
        ('django_admin_log', 'SELECT, INSERT'),
        ('django_content_type', 'SELECT'),
        ('django_migrations', 'SELECT'),
        ('django_session', 'SELECT, INSERT, UPDATE, DELETE'),
        ('sales_customer', 'SELECT, INSERT, UPDATE'),
        ('sales_customerphone', 'SELECT, INSERT, UPDATE'),
        ('sales_interaction', 'SELECT, INSERT'),
        ('sales_lead', 'SELECT, INSERT, UPDATE'),
        ('sales_leadassignmenthistory', 'SELECT, INSERT'),
        ('sales_product', 'SELECT, INSERT, UPDATE'),
        ('sales_productcategory', 'SELECT, INSERT, UPDATE'),
        ('sales_sale', 'SELECT, INSERT, UPDATE'),
        ('sales_salesdocument', 'SELECT, INSERT, UPDATE'),
        ('sales_postalstatushistory', 'SELECT, INSERT')
) AS table_grant(table_name, privileges)
WHERE to_regclass(format('%I.%I', 'public', table_grant.table_name)) IS NOT NULL
ORDER BY table_grant.table_name
\gexec
SELECT format(
    'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I',
    :'backup_user'
) \gexec
SELECT format(
    'GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I',
    :'backup_user'
) \gexec
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
SELECT format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', :'app_user') \gexec
SELECT format(
    'GRANT USAGE, SELECT ON SEQUENCE %I.%I TO %I',
    sequence_namespace.nspname,
    sequence_relation.relname,
    :'app_user'
)
FROM pg_class sequence_relation
JOIN pg_namespace sequence_namespace
  ON sequence_namespace.oid = sequence_relation.relnamespace
JOIN pg_depend dependency
  ON dependency.classid = 'pg_class'::regclass
 AND dependency.objid = sequence_relation.oid
 AND dependency.refclassid = 'pg_class'::regclass
 AND dependency.deptype IN ('a', 'i')
JOIN pg_class table_relation ON table_relation.oid = dependency.refobjid
JOIN pg_namespace table_namespace ON table_namespace.oid = table_relation.relnamespace
WHERE sequence_relation.relkind = 'S'
  AND sequence_namespace.nspname = 'public'
  AND table_namespace.nspname = 'public'
  AND has_table_privilege(:'app_user', table_relation.oid, 'INSERT')
ORDER BY sequence_relation.oid
\gexec
SELECT format(
    'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I',
    :'backup_user'
) \gexec
SELECT format(
    'GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO %I',
    :'backup_user'
) \gexec
REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA public FROM PUBLIC;
SELECT format(
    'REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA public FROM %I',
    :'app_user'
) \gexec
SELECT format(
    'REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA public FROM %I',
    :'backup_user'
) \gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC',
    :'migration_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON TABLES FROM %I',
    :'migration_user',
    :'app_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON TABLES FROM %I',
    :'migration_user',
    :'backup_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I',
    :'migration_user',
    :'backup_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC',
    :'migration_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I',
    :'migration_user',
    :'app_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I',
    :'migration_user',
    :'backup_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON SEQUENCES TO %I',
    :'migration_user',
    :'backup_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC',
    :'migration_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM %I',
    :'migration_user',
    :'app_user'
) \gexec
SELECT format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM %I',
    :'migration_user',
    :'backup_user'
) \gexec
COMMIT;
SQL
} | psql \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_INIT_USER" \
    --dbname="$POSTGRES_DB" \
    --no-password \
    --quiet \
    --set=ON_ERROR_STOP=1

unset PGPASSWORD
echo "PostgreSQL managed roles are ready."
