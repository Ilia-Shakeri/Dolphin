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
    AND has_table_privilege(:'app_user', 'communications_inboundsms', 'SELECT')
    AND has_table_privilege(:'app_user', 'communications_inboundsms', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'communications_inboundsms', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'communications_inboundsms', 'DELETE')
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
    -- Inventory: the movement ledger is append-only.
    AND has_table_privilege(:'app_user', 'inventory_warehouse', 'SELECT')
    AND has_table_privilege(:'app_user', 'inventory_warehouse', 'INSERT')
    AND has_table_privilege(:'app_user', 'inventory_warehouse', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'inventory_warehouse', 'DELETE')
    AND has_table_privilege(:'app_user', 'inventory_stockitem', 'SELECT')
    AND has_table_privilege(:'app_user', 'inventory_stockitem', 'INSERT')
    AND has_table_privilege(:'app_user', 'inventory_stockitem', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'inventory_stockitem', 'DELETE')
    AND has_table_privilege(:'app_user', 'inventory_stockmovement', 'SELECT')
    AND has_table_privilege(:'app_user', 'inventory_stockmovement', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'inventory_stockmovement', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'inventory_stockmovement', 'DELETE')
    -- Billing: line tables allow DELETE for draft editing only; the money
    -- ledger and the cheque history are append-only.
    AND has_table_privilege(:'app_user', 'billing_documentsequence', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_documentsequence', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_documentsequence', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_documentsequence', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_quotation', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_quotation', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_quotation', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_quotation', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_quotationitem', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_quotationitem', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'billing_quotationitem', 'UPDATE')
    AND has_table_privilege(:'app_user', 'billing_quotationitem', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_order', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_order', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_order', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_order', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_orderitem', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_orderitem', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'billing_orderitem', 'UPDATE')
    AND has_table_privilege(:'app_user', 'billing_orderitem', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_invoice', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_invoice', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_invoice', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_invoice', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_invoiceitem', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_invoiceitem', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_invoiceitem', 'UPDATE')
    AND has_table_privilege(:'app_user', 'billing_invoiceitem', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_payment', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_payment', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_payment', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_payment', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_paymentallocation', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_paymentallocation', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_paymentallocation', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_paymentallocation', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_cheque', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_cheque', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_cheque', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_cheque', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_chequestatushistory', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_chequestatushistory', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'billing_chequestatushistory', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_chequestatushistory', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_installmentplan', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_installmentplan', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_installmentplan', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_installmentplan', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_installment', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_installment', 'INSERT')
    AND has_table_privilege(:'app_user', 'billing_installment', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_installment', 'DELETE')
    AND has_table_privilege(:'app_user', 'billing_customerledgerentry', 'SELECT')
    AND has_table_privilege(:'app_user', 'billing_customerledgerentry', 'INSERT')
    AND NOT has_table_privilege(:'app_user', 'billing_customerledgerentry', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'billing_customerledgerentry', 'DELETE')
    AND has_table_privilege(:'app_user', 'sales_salesdocument', 'SELECT')
    AND has_table_privilege(:'app_user', 'sales_salesdocument', 'INSERT')
    AND has_table_privilege(:'app_user', 'sales_salesdocument', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'sales_salesdocument', 'DELETE')
    AND has_table_privilege(:'app_user', 'sales_productcategory', 'SELECT')
    AND has_table_privilege(:'app_user', 'sales_productcategory', 'INSERT')
    AND has_table_privilege(:'app_user', 'sales_productcategory', 'UPDATE')
    AND NOT has_table_privilege(:'app_user', 'sales_productcategory', 'DELETE')
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
    AND NOT has_function_privilege(:'app_user', 'public.frooshbin_contract_probe()', 'EXECUTE')
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
    AND has_table_privilege(:'backup_user', 'communications_inboundsms', 'SELECT')
    AND NOT has_table_privilege(:'backup_user', 'communications_inboundsms', 'INSERT')
    AND NOT has_table_privilege(:'backup_user', 'communications_inboundsms', 'UPDATE')
    AND NOT has_table_privilege(:'backup_user', 'communications_inboundsms', 'DELETE')
    AND has_sequence_privilege(:'backup_user', 'accounts_user_id_seq', 'SELECT')
    AND NOT has_sequence_privilege(:'backup_user', 'accounts_user_id_seq', 'USAGE')
    AND NOT has_function_privilege(:'backup_user', 'public.frooshbin_contract_probe()', 'EXECUTE')
) AS privilege_contract_ok \gset

\if :privilege_contract_ok
\else
    \echo 'PostgreSQL runtime privilege contract failed.'
    -- psql's \quit takes no argument and exits 0, so announcing the failure is
    -- not enough: raise, and let ON_ERROR_STOP=1 give a non-zero exit.
    DO $frooshbin_guard$ BEGIN
        RAISE EXCEPTION 'PostgreSQL runtime privilege contract failed.';
    END $frooshbin_guard$;
\endif
