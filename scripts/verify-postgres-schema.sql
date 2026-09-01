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
    AND to_regclass('public.sales_productcategory') IS NOT NULL
    AND to_regclass('public.sales_sale') IS NOT NULL
    AND to_regclass('public.sales_salesdocument') IS NOT NULL
    AND to_regclass('public.sales_postalstatushistory') IS NOT NULL
    AND to_regclass('public.aftersales_aftersalesrequest') IS NOT NULL
    AND to_regclass('public.aftersales_aftersaleshistory') IS NOT NULL
    AND to_regclass('public.communications_inboundsms') IS NOT NULL
    AND to_regclass('public.inventory_warehouse') IS NOT NULL
    AND to_regclass('public.inventory_stockitem') IS NOT NULL
    AND to_regclass('public.inventory_stockmovement') IS NOT NULL
    AND to_regclass('public.billing_documentsequence') IS NOT NULL
    AND to_regclass('public.billing_quotation') IS NOT NULL
    AND to_regclass('public.billing_quotationitem') IS NOT NULL
    AND to_regclass('public.billing_order') IS NOT NULL
    AND to_regclass('public.billing_orderitem') IS NOT NULL
    AND to_regclass('public.billing_invoice') IS NOT NULL
    AND to_regclass('public.billing_invoiceitem') IS NOT NULL
    AND to_regclass('public.billing_payment') IS NOT NULL
    AND to_regclass('public.billing_paymentallocation') IS NOT NULL
    AND to_regclass('public.billing_cheque') IS NOT NULL
    AND to_regclass('public.billing_chequestatushistory') IS NOT NULL
    AND to_regclass('public.billing_installmentplan') IS NOT NULL
    AND to_regclass('public.billing_installment') IS NOT NULL
    AND to_regclass('public.billing_customerledgerentry') IS NOT NULL
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'accounts') = 3
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'accounts') = '0003_after_sales_foundation'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'auditlog') = 2
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'auditlog') = '0002_activitylog_role_snapshots'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'sales') = 13
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'sales') = '0013_product_barcode_product_brand_productcategory_and_more'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'aftersales') = 1
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'aftersales') = '0001_after_sales_foundation'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'communications') = 1
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'communications') = '0001_initial'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'inventory') = 1
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'inventory') = '0001_initial'
    AND (SELECT COUNT(*) FROM django_migrations WHERE app = 'billing') = 2
    AND (SELECT MAX(name) FROM django_migrations WHERE app = 'billing') = '0002_initial'
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
                ('communications_inboundsms', 'uniq_inbound_sms_provider_message'),
                ('communications_inboundsms', 'inbound_sms_provider_code_shape'),
                ('communications_inboundsms', 'inbound_sms_external_id_nonblank'),
                ('communications_inboundsms', 'inbound_sms_sender_e164'),
                ('communications_inboundsms', 'inbound_sms_recipient_e164'),
                ('communications_inboundsms', 'inbound_sms_direction_only'),
                ('communications_inboundsms', 'inbound_sms_body_not_retained'),
                ('communications_inboundsms', 'inbound_sms_processing_state_valid'),
                ('communications_inboundsms', 'inbound_sms_lead_requires_customer'),
                ('inventory_stockmovement', 'stock_movement_quantity_positive'),
                ('inventory_stockmovement', 'stock_movement_type_valid'),
                ('inventory_stockmovement', 'stock_movement_reference_pair'),
                ('inventory_stockitem', 'uniq_stock_item_warehouse_product'),
                ('inventory_warehouse', 'warehouse_default_is_active'),
                ('billing_invoice', 'invoice_total_matches_parts'),
                ('billing_invoice', 'invoice_paid_within_total'),
                ('billing_invoice', 'invoice_discount_within_subtotal'),
                ('billing_invoice', 'invoice_status_valid'),
                ('billing_invoiceitem', 'invoice_item_line_total_matches_inputs'),
                ('billing_invoiceitem', 'uniq_invoice_item_line_number'),
                ('billing_quotation', 'quotation_total_matches_parts'),
                ('billing_order', 'order_total_matches_parts'),
                ('billing_payment', 'payment_amount_positive'),
                ('billing_payment', 'payment_allocated_within_amount'),
                ('billing_cheque', 'cheque_status_valid'),
                ('billing_installment', 'installment_paid_within_amount'),
                ('billing_customerledgerentry', 'ledger_exactly_one_side'),
                ('billing_customerledgerentry', 'ledger_entry_type_valid'),
                ('billing_customerledgerentry', 'ledger_reference_pair'),
                ('sales_customerphone', 'customer_phone_normalized_shape'),
                ('sales_interaction', 'interaction_direction_valid'),
                ('sales_interaction', 'interaction_outcome_nonblank'),
                ('sales_lead', 'lead_assignment_fields_consistent'),
                ('sales_product', 'product_price_positive'),
                ('sales_product', 'product_barcode_shape'),
                ('sales_productcategory', 'product_category_code_shape'),
                ('sales_productcategory', 'product_category_name_nonblank'),
                ('sales_productcategory', 'product_category_normalized_name_nonblank'),
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
    -- Partial unique rules of the inventory and billing modules. A
    -- UniqueConstraint carrying a condition is created as a partial unique
    -- index, so it is absent from pg_constraint and has to be proven here:
    -- these are the rules that stop a duplicate idempotency key, a second
    -- default warehouse, a re-applied allocation, and a duplicate live cheque
    -- from surviving a restore.
    AND NOT EXISTS (
        SELECT 1
        FROM (
            VALUES
                ('inventory_stockmovement', 'uniq_stock_movement_idempotency_key'),
                ('inventory_warehouse', 'uniq_single_default_warehouse'),
                ('billing_payment', 'uniq_payment_idempotency_key'),
                ('billing_paymentallocation', 'uniq_active_payment_invoice_allocation'),
                ('billing_cheque', 'uniq_active_cheque_bank_serial')
        ) AS required_index(table_name, index_name)
        WHERE NOT EXISTS (
            SELECT 1
            FROM pg_class index_relation
            JOIN pg_namespace index_namespace
              ON index_namespace.oid = index_relation.relnamespace
            JOIN pg_index index_info
              ON index_info.indexrelid = index_relation.oid
            WHERE index_namespace.nspname = 'public'
              AND index_relation.relname = required_index.index_name
              AND index_info.indrelid = to_regclass('public.' || required_index.table_name)
              AND index_info.indisunique
              AND index_info.indisvalid
              AND index_info.indisready
              AND index_info.indislive
              AND index_info.indpred IS NOT NULL
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
    AND EXISTS (
        SELECT 1
        FROM pg_class index_relation
        JOIN pg_namespace index_namespace
          ON index_namespace.oid = index_relation.relnamespace
        JOIN pg_index index_info
          ON index_info.indexrelid = index_relation.oid
        WHERE index_namespace.nspname = 'public'
          AND index_relation.relname = 'uniq_product_nonblank_barcode'
          AND index_info.indrelid = to_regclass('public.sales_product')
          AND index_info.indisunique
          AND index_info.indisvalid
          AND index_info.indisready
          AND index_info.indislive
          AND index_info.indnkeyatts = 1
          AND pg_get_indexdef(index_relation.oid, 1, true) = 'barcode'
          AND pg_get_expr(index_info.indpred, index_info.indrelid, true) IS NOT NULL
    )
    AND 2 = (
        SELECT COUNT(*)
        FROM pg_class index_relation
        JOIN pg_namespace index_namespace
          ON index_namespace.oid = index_relation.relnamespace
        JOIN pg_index index_info
          ON index_info.indexrelid = index_relation.oid
        WHERE index_namespace.nspname = 'public'
          AND index_info.indrelid = to_regclass('public.sales_productcategory')
          AND index_info.indisunique
          AND index_info.indisvalid
          AND index_info.indisready
          AND index_info.indislive
          AND index_info.indnkeyatts = 1
          AND pg_get_indexdef(index_relation.oid, 1, true) IN ('code', 'normalized_name')
          AND index_info.indpred IS NULL
    )
) AS schema_contract_ok \gset

\if :schema_contract_ok
    SELECT 1;
\else
    \echo 'PostgreSQL schema contract failed.'
    -- psql's \quit takes no argument and exits 0, so announcing the failure is
    -- not enough: raise, and let ON_ERROR_STOP=1 give a non-zero exit.
    DO $dolphin_guard$ BEGIN
        RAISE EXCEPTION 'PostgreSQL schema contract failed.';
    END $dolphin_guard$;
\endif
