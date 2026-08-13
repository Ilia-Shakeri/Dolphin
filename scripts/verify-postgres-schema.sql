SELECT (
    to_regclass('public.django_migrations') IS NOT NULL
    AND to_regclass('public.accounts_user') IS NOT NULL
    AND to_regclass('public.auditlog_activitylog') IS NOT NULL
    AND to_regclass('public.sales_customer') IS NOT NULL
    AND to_regclass('public.sales_customerphone') IS NOT NULL
    AND to_regclass('public.sales_lead') IS NOT NULL
    AND to_regclass('public.sales_leadassignmenthistory') IS NOT NULL
    AND to_regclass('public.sales_interaction') IS NOT NULL
    AND to_regclass('public.sales_product') IS NOT NULL
    AND to_regclass('public.sales_sale') IS NOT NULL
    AND to_regclass('public.sales_salesdocument') IS NOT NULL
    AND to_regclass('public.sales_postalstatushistory') IS NOT NULL
    AND to_regclass('public.aftersales_aftersalesrequest') IS NOT NULL
    AND to_regclass('public.aftersales_aftersaleshistory') IS NOT NULL
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'accounts') = 3
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'accounts') = '0003_after_sales_foundation'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'auditlog') = 2
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'auditlog') = '0002_activitylog_role_snapshots'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'sales') = 12
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'sales') = '0012_sales_document_postal_foundation'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'aftersales') = 1
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'aftersales') = '0001_after_sales_foundation'
    AND NOT EXISTS (
        SELECT 1
        FROM (
            VALUES
                ('accounts_user', 'accounts_user_role_valid'),
                ('accounts_user', 'accounts_user_workstream_valid'),
                ('accounts_user', 'accounts_user_elevated_workstream_sales'),
                ('aftersales_aftersalesrequest', 'after_sales_subject_nonblank'),
                ('aftersales_aftersalesrequest', 'after_sales_description_nonblank'),
                ('aftersales_aftersalesrequest', 'after_sales_status_nonblank'),
                ('aftersales_aftersaleshistory', 'after_sales_history_event_valid'),
                ('sales_customerphone', 'customer_phone_normalized_shape'),
                ('sales_interaction', 'interaction_direction_valid'),
                ('sales_interaction', 'interaction_outcome_nonblank'),
                ('sales_lead', 'lead_assignment_fields_consistent'),
                ('sales_product', 'product_price_positive'),
                ('sales_sale', 'sale_quantity_positive'),
                ('sales_sale', 'sale_total_non_negative'),
                ('sales_sale', 'sale_unit_price_non_negative'),
                ('sales_sale', 'sale_status_valid'),
                ('sales_sale', 'sale_product_snapshot_pair'),
                ('sales_sale', 'sale_product_total_matches_snapshot'),
                ('sales_salesdocument', 'sales_document_number_nonblank'),
                ('sales_salesdocument', 'sales_document_postal_status_nonblank'),
                ('sales_postalstatushistory', 'postal_history_to_status_nonblank')
        ) AS required_constraint(table_name, constraint_name)
        WHERE NOT EXISTS (
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = to_regclass('public.' || required_constraint.table_name)
              AND conname = required_constraint.constraint_name
        )
    )
    AND EXISTS (
        SELECT 1
        FROM pg_class index_relation
        JOIN pg_namespace index_namespace
          ON index_namespace.oid = index_relation.relnamespace
        JOIN pg_index index_info
          ON index_info.indexrelid = index_relation.oid
        WHERE index_namespace.nspname = 'public'
          AND index_relation.relname = 'uniq_active_normalized_phone'
          AND index_info.indrelid = to_regclass('public.sales_customerphone')
          AND index_info.indisunique
          AND index_info.indisvalid
          AND index_info.indisready
          AND index_info.indislive
          AND index_info.indnkeyatts = 1
          AND pg_get_indexdef(index_relation.oid, 1, true) = 'normalized_phone'
          AND regexp_replace(
              pg_get_expr(index_info.indpred, index_info.indrelid, true),
              '[()[:space:]]',
              '',
              'g'
          ) = 'is_active'
    )
    AND EXISTS (
        SELECT 1
        FROM pg_class index_relation
        JOIN pg_namespace index_namespace
          ON index_namespace.oid = index_relation.relnamespace
        JOIN pg_index index_info
          ON index_info.indexrelid = index_relation.oid
        WHERE index_namespace.nspname = 'public'
          AND index_relation.relname = 'uniq_active_primary_phone'
          AND index_info.indrelid = to_regclass('public.sales_customerphone')
          AND index_info.indisunique
          AND index_info.indisvalid
          AND index_info.indisready
          AND index_info.indislive
          AND index_info.indnkeyatts = 1
          AND pg_get_indexdef(index_relation.oid, 1, true) = 'customer_id'
          AND regexp_replace(
              pg_get_expr(index_info.indpred, index_info.indrelid, true),
              '[()[:space:]]',
              '',
              'g'
          ) = 'is_activeANDis_primary'
    )
) AS schema_contract_ok \gset

\if :schema_contract_ok
    SELECT 1;
\else
    \echo 'PostgreSQL schema contract failed.'
    \quit 6
\endif
