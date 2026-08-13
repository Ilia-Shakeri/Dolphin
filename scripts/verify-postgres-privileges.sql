SELECT (
    EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'migration_user'
          AND rolcanlogin
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolinherit
          AND NOT rolreplication
          AND NOT rolbypassrls
    )
    AND EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'app_user'
          AND rolcanlogin
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolinherit
          AND NOT rolreplication
          AND NOT rolbypassrls
    )
    AND EXISTS (
        SELECT 1
        FROM pg_roles
        WHERE rolname = :'backup_user'
          AND rolcanlogin
          AND NOT rolsuper
          AND NOT rolcreatedb
          AND NOT rolcreaterole
          AND NOT rolinherit
          AND NOT rolreplication
          AND NOT rolbypassrls
    )
    AND NOT EXISTS (
        SELECT 1
        FROM pg_auth_members membership
        JOIN pg_roles member ON member.oid = membership.member
        WHERE member.rolname IN (:'migration_user', :'app_user', :'backup_user')
    )
    AND NOT EXISTS (
        SELECT 1
        FROM pg_auth_members membership
        JOIN pg_roles granted ON granted.oid = membership.roleid
        WHERE granted.rolname IN (:'migration_user', :'app_user', :'backup_user')
    )
    AND has_database_privilege(:'app_user', current_database(), 'CONNECT')
    AND NOT has_database_privilege(:'app_user', current_database(), 'CREATE')
    AND NOT has_database_privilege(:'app_user', current_database(), 'TEMP')
    AND has_schema_privilege(:'app_user', 'public', 'USAGE')
    AND NOT has_schema_privilege(:'app_user', 'public', 'CREATE')
    AND has_table_privilege(:'app_user', 'accounts_user', 'SELECT')
    AND has_table_privilege(:'app_user', 'accounts_user', 'INSERT')
    AND has_table_privilege(:'app_user', 'accounts_user', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'accounts_user', 'DELETE')
    AND has_table_privilege(:'app_user', 'django_session', 'SELECT')
    AND has_table_privilege(:'app_user', 'django_session', 'INSERT')
    AND has_table_privilege(:'app_user', 'django_session', 'UPDATE')
    AND has_table_privilege(:'app_user', 'django_session', 'DELETE')
    AND has_table_privilege(:'app_user', 'auditlog_activitylog', 'SELECT')
    AND has_table_privilege(:'app_user', 'auditlog_activitylog', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'auditlog_activitylog', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'auditlog_activitylog', 'DELETE')
    AND has_table_privilege(:'app_user', 'sales_interaction', 'SELECT')
    AND has_table_privilege(:'app_user', 'sales_interaction', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'sales_interaction', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'sales_interaction', 'DELETE')
    AND has_table_privilege(:'app_user', 'sales_leadassignmenthistory', 'SELECT')
    AND has_table_privilege(:'app_user', 'sales_leadassignmenthistory', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'sales_leadassignmenthistory', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'sales_leadassignmenthistory', 'DELETE')
    AND has_table_privilege(:'app_user', 'sales_postalstatushistory', 'SELECT')
    AND has_table_privilege(:'app_user', 'sales_postalstatushistory', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'sales_postalstatushistory', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'sales_postalstatushistory', 'DELETE')
    AND has_table_privilege(:'app_user', 'sales_salesdocument', 'SELECT')
    AND has_table_privilege(:'app_user', 'sales_salesdocument', 'INSERT')
    AND has_table_privilege(:'app_user', 'sales_salesdocument', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'sales_salesdocument', 'DELETE')
    AND has_table_privilege(:'app_user', 'aftersales_aftersalesrequest', 'SELECT')
    AND has_table_privilege(:'app_user', 'aftersales_aftersalesrequest', 'INSERT')
    AND has_table_privilege(:'app_user', 'aftersales_aftersalesrequest', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'aftersales_aftersalesrequest', 'DELETE')
    AND has_table_privilege(:'app_user', 'aftersales_aftersaleshistory', 'SELECT')
    AND has_table_privilege(:'app_user', 'aftersales_aftersaleshistory', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'aftersales_aftersaleshistory', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'aftersales_aftersaleshistory', 'DELETE')
    AND has_table_privilege(:'app_user', 'django_admin_log', 'SELECT')
    AND has_table_privilege(:'app_user', 'django_admin_log', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'django_admin_log', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'django_admin_log', 'DELETE')
    AND has_table_privilege(:'app_user', 'django_migrations', 'SELECT')
    AND NOT has_table_privilege(:'app_user', 'django_migrations', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'django_migrations', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'django_migrations', 'DELETE')
    AND has_sequence_privilege(:'app_user', 'accounts_user_id_seq', 'USAGE')
    AND has_sequence_privilege(:'app_user', 'accounts_user_id_seq', 'SELECT')
    AND NOT has_sequence_privilege(:'app_user', 'auth_permission_id_seq', 'USAGE')
    AND NOT has_function_privilege(:'app_user', 'public.kariz_contract_probe()', 'EXECUTE')
    AND has_database_privilege(:'backup_user', current_database(), 'CONNECT')
    AND NOT has_database_privilege(:'backup_user', current_database(), 'CREATE')
    AND NOT has_database_privilege(:'backup_user', current_database(), 'TEMP')
    AND has_schema_privilege(:'backup_user', 'public', 'USAGE')
    AND NOT has_schema_privilege(:'backup_user', 'public', 'CREATE')
    AND has_table_privilege(:'backup_user', 'accounts_user', 'SELECT')
    AND NOT has_table_privilege(:'backup_user', 'accounts_user', 'INSERT')
    AND NOT has_table_privilege(:'backup_user', 'accounts_user', 'UPDATE')
    AND NOT has_table_privilege(:'backup_user', 'accounts_user', 'DELETE')
    AND has_table_privilege(:'backup_user', 'auditlog_activitylog', 'SELECT')
    AND NOT has_table_privilege(:'backup_user', 'auditlog_activitylog', 'INSERT')
    AND NOT has_table_privilege(:'backup_user', 'auditlog_activitylog', 'UPDATE')
    AND NOT has_table_privilege(:'backup_user', 'auditlog_activitylog', 'DELETE')
    AND has_sequence_privilege(:'backup_user', 'accounts_user_id_seq', 'SELECT')
    AND NOT has_sequence_privilege(:'backup_user', 'accounts_user_id_seq', 'USAGE')
    AND NOT has_function_privilege(:'backup_user', 'public.kariz_contract_probe()', 'EXECUTE')
) AS privilege_contract_ok \gset

\if :privilege_contract_ok
\else
    \echo 'PostgreSQL runtime privilege contract failed.'
    \quit 5
\endif
