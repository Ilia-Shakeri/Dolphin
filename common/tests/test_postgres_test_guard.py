from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.postgres_contract_guard import build_postgres_contract_database
from config.postgres_test_guard import build_postgres_test_database


class PostgresTestGuardTests(SimpleTestCase):
    def safe_environment(self):
        token = "a" * 32
        return {
            "KARIZ_PG_TEST": "1",
            "KARIZ_PG_TEST_TOKEN": token,
            "KARIZ_PG_TEST_HOST": "127.0.0.1",
            "KARIZ_PG_TEST_PORT": "55432",
            "KARIZ_PG_TEST_NAME": f"test_frooshbin_{token}",
            "KARIZ_PG_TEST_USER": "frooshbin_test_admin",
        }

    def test_builds_only_isolated_postgres_settings(self):
        database = build_postgres_test_database(self.safe_environment())
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["HOST"], "127.0.0.1")
        self.assertEqual(database["CONN_MAX_AGE"], 0)
        self.assertTrue(database["TEST"]["NAME"].startswith("test_frooshbin_"))

    def test_rejects_missing_opt_in(self):
        environment = self.safe_environment()
        environment.pop("KARIZ_PG_TEST")
        with self.assertRaises(ImproperlyConfigured):
            build_postgres_test_database(environment)

    def test_rejects_non_loopback_host(self):
        environment = self.safe_environment()
        environment["KARIZ_PG_TEST_HOST"] = "db.example.com"
        with self.assertRaises(ImproperlyConfigured):
            build_postgres_test_database(environment)

    def test_rejects_default_postgres_port(self):
        environment = self.safe_environment()
        environment["KARIZ_PG_TEST_PORT"] = "5432"
        with self.assertRaises(ImproperlyConfigured):
            build_postgres_test_database(environment)

    def test_rejects_database_name_not_bound_to_token(self):
        environment = self.safe_environment()
        environment["KARIZ_PG_TEST_NAME"] = "kariz"
        with self.assertRaises(ImproperlyConfigured):
            build_postgres_test_database(environment)


class PostgresContractGuardTests(SimpleTestCase):
    def safe_environment(self):
        token = "b" * 32
        return {
            "KARIZ_PG_CONTRACT": "1",
            "KARIZ_PG_CONTRACT_TOKEN": token,
            "KARIZ_PG_CONTRACT_HOST": "127.0.0.1",
            "KARIZ_PG_CONTRACT_PORT": "55433",
            "KARIZ_PG_CONTRACT_NAME": f"contract_frooshbin_{token}",
            "KARIZ_PG_CONTRACT_USER": f"frooshbin_migration_{token}",
            "KARIZ_PG_CONTRACT_PASSWORD": "isolated-contract-secret",
        }

    def test_builds_only_token_bound_contract_settings(self):
        database = build_postgres_contract_database(self.safe_environment())
        self.assertEqual(database["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(database["HOST"], "127.0.0.1")
        self.assertEqual(database["PORT"], "55433")
        self.assertEqual(database["CONN_MAX_AGE"], 0)
        self.assertEqual(database["NAME"], "contract_frooshbin_" + "b" * 32)

    def test_rejects_contract_without_sentinel(self):
        environment = self.safe_environment()
        environment.pop("KARIZ_PG_CONTRACT")
        with self.assertRaises(ImproperlyConfigured):
            build_postgres_contract_database(environment)

    def test_rejects_contract_default_port_or_non_loopback(self):
        for field, value in (
            ("KARIZ_PG_CONTRACT_PORT", "5432"),
            ("KARIZ_PG_CONTRACT_HOST", "db.internal"),
        ):
            with self.subTest(field=field):
                environment = self.safe_environment()
                environment[field] = value
                with self.assertRaises(ImproperlyConfigured):
                    build_postgres_contract_database(environment)

    def test_rejects_contract_name_user_and_password_not_bound_to_run(self):
        for field, value in (
            ("KARIZ_PG_CONTRACT_NAME", "kariz"),
            ("KARIZ_PG_CONTRACT_USER", "frooshbin_migration_other"),
            ("KARIZ_PG_CONTRACT_PASSWORD", "short"),
        ):
            with self.subTest(field=field):
                environment = self.safe_environment()
                environment[field] = value
                with self.assertRaises(ImproperlyConfigured):
                    build_postgres_contract_database(environment)
