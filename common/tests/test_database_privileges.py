import re
from pathlib import Path

import yaml
from django.apps import apps
from django.test import SimpleTestCase


ROOT = Path(__file__).resolve().parents[2]


class DatabasePrivilegeContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.compose_text = (ROOT / "compose.yml").read_text(encoding="utf-8")
        cls.compose = yaml.safe_load(cls.compose_text)
        cls.services = cls.compose["services"]
        cls.bootstrap = (ROOT / "scripts" / "bootstrap-postgres.sh").read_text(
            encoding="utf-8"
        )
        cls.backup_script = (ROOT / "scripts" / "backup-postgres.sh").read_text(
            encoding="utf-8"
        )
        cls.dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        cls.gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        cls.env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    def test_database_secrets_are_scoped_to_the_services_that_need_them(self):
        self.assertNotIn("env_file", self.services["web"])
        self.assertNotIn("env_file", self.services["migrate"])

        web_environment = self.services["web"]["environment"]
        self.assertEqual(web_environment["KARIZ_DATABASE_ROLE"], "app")
        self.assertIn("POSTGRES_APP_PASSWORD", web_environment)
        self.assertNotIn("POSTGRES_MIGRATION_PASSWORD", web_environment)
        self.assertNotIn("POSTGRES_INIT_PASSWORD", web_environment)
        self.assertNotIn("POSTGRES_BACKUP_PASSWORD", web_environment)

        migration_environment = self.services["migrate"]["environment"]
        self.assertEqual(migration_environment["KARIZ_DATABASE_ROLE"], "migration")
        self.assertIn("POSTGRES_MIGRATION_PASSWORD", migration_environment)
        self.assertNotIn("POSTGRES_APP_PASSWORD", migration_environment)
        self.assertNotIn("POSTGRES_INIT_PASSWORD", migration_environment)
        self.assertNotIn("POSTGRES_BACKUP_PASSWORD", migration_environment)

        database_environment = self.services["db"]["environment"]
        self.assertEqual(database_environment["POSTGRES_USER"], "${POSTGRES_INIT_USER}")
        self.assertEqual(
            database_environment["POSTGRES_PASSWORD"],
            "${POSTGRES_INIT_PASSWORD}",
        )
        self.assertEqual(web_environment["POSTGRES_HOST"], "db")
        self.assertEqual(web_environment["POSTGRES_PORT"], "5432")
        self.assertEqual(migration_environment["POSTGRES_HOST"], "db")
        self.assertEqual(migration_environment["POSTGRES_PORT"], "5432")

        for one_shot_service in ("db-bootstrap", "db-finalize"):
            with self.subTest(service=one_shot_service):
                environment = self.services[one_shot_service]["environment"]
                self.assertIn("POSTGRES_INIT_PASSWORD", environment)
                self.assertIn("POSTGRES_MIGRATION_PASSWORD", environment)
                self.assertIn("POSTGRES_APP_PASSWORD", environment)
                self.assertIn("POSTGRES_BACKUP_PASSWORD", environment)
                self.assertEqual(self.services[one_shot_service]["restart"], "no")

        backup_environment = self.services["backup"]["environment"]
        self.assertEqual(
            {
                name
                for name in backup_environment
                if name.endswith("_PASSWORD")
            },
            {"POSTGRES_BACKUP_PASSWORD"},
        )
        self.assertNotIn("env_file", self.services["backup"])

        password_scope = {
            "POSTGRES_INIT_PASSWORD": {"db", "db-bootstrap", "db-finalize"},
            "POSTGRES_MIGRATION_PASSWORD": {
                "db-bootstrap",
                "migrate",
                "db-finalize",
            },
            "POSTGRES_APP_PASSWORD": {"db-bootstrap", "db-finalize", "web"},
            "POSTGRES_BACKUP_PASSWORD": {
                "db-bootstrap",
                "db-finalize",
                "backup",
            },
        }
        for password_name, expected_services in password_scope.items():
            interpolation = f"${{{password_name}}}"
            actual_services = {
                service_name
                for service_name, service in self.services.items()
                if interpolation in service.get("environment", {}).values()
            }
            with self.subTest(password=password_name):
                self.assertEqual(actual_services, expected_services)

        nginx_environment = self.services["nginx"]["environment"]
        self.assertFalse(
            any(name.endswith("_PASSWORD") for name in nginx_environment)
        )

    def test_bootstrap_precedes_owner_migration_and_runtime(self):
        self.assertEqual(
            self.services["migrate"]["depends_on"]["db-bootstrap"]["condition"],
            "service_completed_successfully",
        )
        self.assertEqual(
            self.services["db-finalize"]["depends_on"]["migrate"]["condition"],
            "service_completed_successfully",
        )
        self.assertEqual(
            self.services["web"]["depends_on"]["db-finalize"]["condition"],
            "service_completed_successfully",
        )
        self.assertEqual(
            self.services["migrate"]["command"][2],
            "python manage.py migrate --noinput && python manage.py collectstatic --noinput",
        )
        self.assertNotIn("migrate", " ".join(self.services["web"].get("command", [])))
        self.assertEqual(
            self.services["db-finalize"]["command"],
            ["sh", "/ops/bootstrap-postgres.sh"],
        )

    def test_database_and_backup_volumes_need_explicit_existing_names(self):
        volume = self.compose["volumes"]["postgres_data"]
        self.assertTrue(volume["external"])
        self.assertEqual(
            volume["name"],
            "${POSTGRES_DATA_VOLUME:?POSTGRES_DATA_VOLUME must name the approved database volume}",
        )
        self.assertEqual(
            self.services["db"]["volumes"],
            ["postgres_data:/var/lib/postgresql/data"],
        )
        backup_volume = self.compose["volumes"]["backup_data"]
        self.assertTrue(backup_volume["external"])
        self.assertEqual(
            backup_volume["name"],
            "${POSTGRES_BACKUP_VOLUME:?POSTGRES_BACKUP_VOLUME must name the approved backup volume}",
        )
        self.assertIn("backup_data:/backups", self.services["backup"]["volumes"])
        for service_name, service in self.services.items():
            if service_name == "backup":
                continue
            self.assertFalse(
                any("backup_data" in str(volume) for volume in service.get("volumes", [])),
                service_name,
            )

    def test_edge_cannot_join_database_network(self):
        self.assertTrue(self.compose["networks"]["backend"]["internal"])
        self.assertEqual(self.services["db"]["networks"], ["backend"])
        self.assertEqual(self.services["db-bootstrap"]["networks"], ["backend"])
        self.assertEqual(self.services["migrate"]["networks"], ["backend"])
        self.assertEqual(self.services["db-finalize"]["networks"], ["backend"])
        self.assertEqual(self.services["backup"]["networks"], ["backend"])
        self.assertEqual(self.services["web"]["networks"], ["backend", "frontend"])
        self.assertEqual(self.services["nginx"]["networks"], ["frontend"])
        self.assertNotIn("backend", self.services["nginx"]["networks"])

    def test_runtime_role_has_no_cluster_or_schema_build_rights(self):
        self.assertIn(
            "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS",
            self.bootstrap,
        )
        self.assertIn("REVOKE ALL ON DATABASE %I FROM PUBLIC", self.bootstrap)
        self.assertIn("REVOKE ALL ON SCHEMA public FROM PUBLIC", self.bootstrap)
        self.assertIn(
            "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC",
            self.bootstrap,
        )
        self.assertIn(
            "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC",
            self.bootstrap,
        )
        self.assertIn("GRANT USAGE ON SCHEMA public", self.bootstrap)
        self.assertNotIn("UPDATE, DELETE ON ALL TABLES", self.bootstrap)
        self.assertNotIn("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES", self.bootstrap)
        self.assertIn(
            "ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public",
            self.bootstrap,
        )
        self.assertNotIn("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I", self.bootstrap)
        self.assertNotIn("GRANT USAGE, SELECT ON ALL SEQUENCES", self.bootstrap)
        self.assertIn(
            "has_table_privilege(:'app_user', table_relation.oid, 'INSERT')",
            self.bootstrap,
        )
        self.assertNotIn("GRANT ALL", self.bootstrap)
        self.assertNotIn("REASSIGN OWNED", self.bootstrap)

    def test_backup_role_is_read_only_and_future_safe(self):
        self.assertIn("Kariz managed backup role v1", self.bootstrap)
        self.assertIn("POSTGRES_BACKUP_USER already exists but is not Kariz-managed.", self.bootstrap)
        self.assertIn("REVOKE ALL ON DATABASE %I FROM %I', :'db_name', :'backup_user'", self.bootstrap)
        self.assertIn("GRANT CONNECT ON DATABASE %I TO %I', :'db_name', :'backup_user'", self.bootstrap)
        self.assertIn("REVOKE ALL ON SCHEMA public FROM %I', :'backup_user'", self.bootstrap)
        self.assertIn("GRANT USAGE ON SCHEMA public TO %I', :'backup_user'", self.bootstrap)
        self.assertIn("GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I", self.bootstrap)
        self.assertIn("GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO %I", self.bootstrap)
        self.assertIn(
            "ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I",
            self.bootstrap,
        )
        self.assertIn(
            "ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON SEQUENCES TO %I",
            self.bootstrap,
        )
        self.assertIn(
            "ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM %I",
            self.bootstrap,
        )
        backup_grants = set()
        for command in self.bootstrap.split("\\gexec"):
            if ":'backup_user'" not in command:
                continue
            backup_grants.update(
                re.findall(
                    r"'((?:ALTER DEFAULT PRIVILEGES [^']+ )?GRANT [^']+)'",
                    command,
                )
            )
        self.assertEqual(
            backup_grants,
            {
                "GRANT CONNECT ON DATABASE %I TO %I",
                "GRANT USAGE ON SCHEMA public TO %I",
                "GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I",
                "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO %I",
                "ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I",
                "ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON SEQUENCES TO %I",
            },
        )

    def test_backup_job_is_isolated_and_guarded(self):
        backup = self.services["backup"]
        self.assertEqual(backup["profiles"], ["backup"])
        self.assertEqual(backup["restart"], "no")
        self.assertEqual(backup["user"], "postgres")
        self.assertTrue(backup["read_only"])
        self.assertEqual(backup["cap_drop"], ["ALL"])
        self.assertIn("no-new-privileges:true", backup["security_opt"])
        self.assertEqual(
            backup["depends_on"]["db"]["condition"],
            "service_healthy",
        )
        self.assertEqual(backup["command"], ["sh", "/ops/backup-postgres.sh"])
        self.assertIn(
            "./scripts/backup-postgres.sh:/ops/backup-postgres.sh:ro",
            backup["volumes"],
        )
        self.assertEqual(backup["tmpfs"], ["/tmp:size=16m,mode=1777"])
        self.assertEqual(backup["environment"]["POSTGRES_BACKUP_ROOT"], "/backups")
        self.assertIn("KARIZ_BACKUP_ROOT_V1", self.backup_script)
        self.assertIn("--username=\"$POSTGRES_BACKUP_USER\"", self.backup_script)
        self.assertIn("--no-password", self.backup_script)
        self.assertNotIn("POSTGRES_INIT_PASSWORD", self.backup_script)
        self.assertNotIn("POSTGRES_MIGRATION_PASSWORD", self.backup_script)
        self.assertNotIn("POSTGRES_APP_PASSWORD", self.backup_script)
        for setting in (
            "POSTGRES_BACKUP_USER=",
            "POSTGRES_BACKUP_PASSWORD=replace-with-",
            "POSTGRES_BACKUP_VOLUME=",
            "POSTGRES_BACKUP_RETENTION_DAYS=",
        ):
            with self.subTest(environment=setting):
                self.assertIn(setting, self.env_example)

    def test_owner_and_acl_changes_share_one_locked_transaction(self):
        transaction_start = self.bootstrap.index("BEGIN;\nSELECT pg_advisory_xact_lock")
        owner_change = self.bootstrap.index("ALTER DATABASE %I OWNER TO %I")
        acl_reset = self.bootstrap.index("REVOKE ALL ON ALL TABLES")
        routine_acl_reset = self.bootstrap.index(
            "REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA public FROM PUBLIC"
        )
        transaction_end = self.bootstrap.index("COMMIT;", acl_reset)
        self.assertLess(transaction_start, owner_change)
        self.assertLess(owner_change, acl_reset)
        self.assertLess(acl_reset, routine_acl_reset)
        self.assertLess(routine_acl_reset, transaction_end)
        self.assertEqual(self.bootstrap.count("pg_advisory_xact_lock("), 1)

    def test_runtime_and_public_have_no_implicit_routine_execution(self):
        self.assertIn(
            "REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA public FROM PUBLIC",
            self.bootstrap,
        )
        self.assertIn(
            "REVOKE EXECUTE ON ALL ROUTINES IN SCHEMA public FROM %I",
            self.bootstrap,
        )
        self.assertIn(
            "ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC",
            self.bootstrap,
        )
        self.assertIn(
            "ALTER DEFAULT PRIVILEGES FOR ROLE %I REVOKE EXECUTE ON FUNCTIONS FROM %I",
            self.bootstrap,
        )
        self.assertNotIn(
            "IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS",
            self.bootstrap,
        )
        self.assertNotIn("GRANT EXECUTE", self.bootstrap)

    def test_runtime_table_grants_are_exact_and_history_is_append_only(self):
        expected_grants = {
            "accounts_user": "SELECT, INSERT, UPDATE",
            "accounts_user_groups": "SELECT, INSERT, DELETE",
            "accounts_user_user_permissions": "SELECT, INSERT, DELETE",
            "aftersales_aftersaleshistory": "SELECT, INSERT",
            "aftersales_aftersalesrequest": "SELECT, INSERT, UPDATE",
            "auditlog_activitylog": "SELECT, INSERT",
            "auth_group": "SELECT, INSERT, UPDATE, DELETE",
            "auth_group_permissions": "SELECT, INSERT, DELETE",
            "auth_permission": "SELECT",
            "django_admin_log": "SELECT, INSERT",
            "django_content_type": "SELECT",
            "django_migrations": "SELECT",
            "django_session": "SELECT, INSERT, UPDATE, DELETE",
            "sales_customer": "SELECT, INSERT, UPDATE",
            "sales_customerphone": "SELECT, INSERT, UPDATE",
            "sales_interaction": "SELECT, INSERT",
            "sales_lead": "SELECT, INSERT, UPDATE",
            "sales_leadassignmenthistory": "SELECT, INSERT",
            "sales_product": "SELECT, INSERT, UPDATE",
            "sales_sale": "SELECT, INSERT, UPDATE",
            "sales_salesdocument": "SELECT, INSERT, UPDATE",
            "sales_postalstatushistory": "SELECT, INSERT",
        }
        grant_block = re.search(
            r"FROM \(\s*VALUES(?P<rows>.*?)\) AS table_grant",
            self.bootstrap,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(grant_block)
        grant_rows = re.findall(
            r"\('([^']+)', '([^']+)'\)",
            grant_block.group("rows"),
        )
        self.assertEqual(len(grant_rows), len(dict(grant_rows)))
        self.assertEqual(dict(grant_rows), expected_grants)

        managed_tables = {
            model._meta.db_table
            for model in apps.get_models(include_auto_created=True)
            if model._meta.managed and not model._meta.proxy
        }
        managed_tables.add("django_migrations")
        self.assertEqual(set(expected_grants), managed_tables)

        for table_name in (
            "auditlog_activitylog",
            "sales_leadassignmenthistory",
            "sales_interaction",
            "sales_postalstatushistory",
            "aftersales_aftersaleshistory",
            "django_admin_log",
        ):
            with self.subTest(append_only=table_name):
                self.assertNotIn(f"('{table_name}', 'SELECT, INSERT, UPDATE", self.bootstrap)
                self.assertNotIn(f"('{table_name}', 'SELECT, INSERT, DELETE", self.bootstrap)

    def test_role_passwords_never_enter_sql_text_or_process_arguments(self):
        self.assertIn('--command="\\\\password $role_name"', self.bootstrap)
        self.assertIn("password_encryption = 'scram-sha-256'", self.bootstrap)
        self.assertIn("printf '%s\\n%s\\n'", self.bootstrap)
        self.assertNotIn("PASSWORD %L", self.bootstrap)
        self.assertNotIn("password_b64", self.bootstrap)
        self.assertNotIn("--set=role_password", self.bootstrap)

    def test_bootstrap_is_in_place_and_fails_on_unsafe_role_layout(self):
        self.assertNotIn("dropdb", self.bootstrap.lower())
        self.assertNotIn("drop database", self.bootstrap.lower())
        self.assertIn("PostgreSQL role names must be distinct.", self.bootstrap)
        self.assertIn("PostgreSQL role passwords must be distinct.", self.bootstrap)
        self.assertIn("already exists but is not Kariz-managed", self.bootstrap)
        self.assertIn("ALTER ROLE %I RESET ALL", self.bootstrap)
        self.assertIn("ALTER ROLE %I IN DATABASE %I RESET ALL", self.bootstrap)
        self.assertIn("SET search_path TO public, pg_catalog", self.bootstrap)
        self.assertIn(
            "A first-party public relation has an unapproved owner.",
            self.bootstrap,
        )
        self.assertIn(
            "A first-party public routine has an unapproved owner.",
            self.bootstrap,
        )

    def test_web_filesystem_is_read_only_and_source_is_root_owned(self):
        web = self.services["web"]
        migrate = self.services["migrate"]
        self.assertTrue(web["read_only"])
        self.assertEqual(web["tmpfs"], ["/tmp:size=64m,mode=1777"])
        self.assertIn("static_data:/app/staticfiles:ro", web["volumes"])
        self.assertIn("static_data:/app/staticfiles", migrate["volumes"])
        self.assertNotIn("static_data:/app/staticfiles:ro", migrate["volumes"])
        self.assertNotIn("chown -R", self.dockerfile)
        self.assertIn("chown appuser:appuser /app/staticfiles", self.dockerfile)
        self.assertIn("*.sh text eol=lf", self.gitattributes.splitlines())
