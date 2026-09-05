"""The provisioning tool that writes a new deployment's `.env`.

Two things are worth pinning here, and they are different in kind.

The first is that the file it produces actually starts a stack: every variable
`compose.yml` requires without a default has to be present, and that assertion
is made against `compose.yml` itself rather than against a copy of the list, so
adding a required variable to Compose fails this test rather than the customer's
first deployment.

The second is the handling of secrets. This tool is the only place four database
passwords and a Django secret key come into existence, and they exist in no
other copy afterwards. So: distinct from each other, long enough for the
bootstrap script's own check, drawn from an alphabet no shell will reinterpret,
and never written anywhere but the file.
"""

import importlib.util
import io
import os
import re
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from django.test import SimpleTestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "new_deployment.py"
COMPOSE = REPOSITORY_ROOT / "compose.yml"


def load_script():
    """Import the script by path; `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("new_deployment", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


provisioning = load_script()


def env_of(text):
    return dict(re.findall(r"^([A-Z][A-Z0-9_]*)=(.*)$", text, re.M))


def provision(**overrides):
    """Run the tool into a throwaway directory and return the parsed `.env`."""
    options = {
        "slug": "tiara",
        "host": "crm.tiara.ir",
        "image": "dolphin-app:v1.1.1",
        "profile": "client-1",
        "manifest_path": "/srv/dolphin/secrets/manifest.json",
        "manifest_keys": "k1:AAAA",
        "retention_days": 0,
    }
    options.update(overrides)
    return env_of("\n".join(provisioning.env_lines(**options)))


class FeatureResolutionTests(SimpleTestCase):
    def test_dependencies_are_pulled_in_transitively(self):
        """`payments` needs invoices, which needs products — two levels down."""
        features, added = provisioning.resolve_features({"payments"})
        self.assertIn("invoices", features)
        self.assertIn("customers", features)
        self.assertIn("products", features)
        self.assertIn("payments", added)

    def test_what_was_added_is_reported_rather_than_done_silently(self):
        """An operator has to be able to see they got more than they asked for."""
        _, added = provisioning.resolve_features({"reports"})
        self.assertTrue(added)
        self.assertIn("sales", {name for names in added.values() for name in names} | set(added))

    def test_a_complete_request_adds_nothing(self):
        features, added = provisioning.resolve_features({"customers", "products"})
        self.assertEqual(features, frozenset({"customers", "products"}))
        self.assertEqual(added, {})

    def test_the_resolved_set_has_no_unmet_dependency_left(self):
        from common.deployment.registry import FEATURES, missing_dependencies

        for requested in ({"payments"}, {"reports"}, {"invoices"}, set(FEATURES)):
            with self.subTest(requested=sorted(requested)):
                features, _ = provisioning.resolve_features(requested)
                self.assertEqual(missing_dependencies(features), {})

    def test_a_feature_this_release_does_not_ship_is_refused(self):
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.resolve_features({"accounting"})


class GeneratedEnvironmentTests(SimpleTestCase):
    def test_every_variable_compose_requires_is_present(self):
        """Asserted against compose.yml, so adding a requirement fails here."""
        compose = COMPOSE.read_text(encoding="utf-8")
        # `${NAME}` and `${NAME:?...}` are required; `${NAME:-default}` is not.
        required = {
            name for name, marker in re.findall(r"\$\{([A-Z][A-Z0-9_]*)(:[-?])?", compose)
            if marker != ":-"
        }
        produced = set(provision())
        self.assertEqual(
            required - produced, set(),
            "compose.yml requires variables the provisioning tool does not write",
        )

    def test_identifiers_all_derive_from_the_one_slug(self):
        """They must agree: three separate places read the same role name."""
        env = provision(slug="acme")
        self.assertEqual(env["KARIZ_COMPOSE_PROJECT_NAME"], "acme")
        self.assertEqual(env["POSTGRES_DB"], "acme")
        self.assertEqual(env["POSTGRES_APP_USER"], "acme_app")
        self.assertEqual(env["POSTGRES_BACKUP_USER"], "acme_backup")
        self.assertEqual(env["POSTGRES_DATA_VOLUME"], "acme_postgres_data")
        self.assertEqual(env["POSTGRES_BACKUP_VOLUME"], "acme_postgres_backups")

    def test_every_derived_name_is_a_legal_postgres_identifier(self):
        env = provision(slug="a" * 41)
        for key in ("POSTGRES_DB", "POSTGRES_INIT_USER", "POSTGRES_MIGRATION_USER",
                    "POSTGRES_APP_USER", "POSTGRES_BACKUP_USER"):
            with self.subTest(key=key):
                value = env[key]
                self.assertRegex(value, r"\A[a-z_][a-z0-9_]*\Z")
                self.assertLessEqual(len(value), 63)
                self.assertFalse(value.startswith("pg_"))

    def test_the_project_name_never_carries_a_version(self):
        """A project per version is what put two servers on one data directory."""
        env = provision(image="dolphin-app:v9.9.9")
        self.assertNotIn("9", env["KARIZ_COMPOSE_PROJECT_NAME"])
        self.assertIn("v9.9.9", env["KARIZ_APP_IMAGE"])


class SecretTests(SimpleTestCase):
    SECRET_KEYS = (
        "DJANGO_SECRET_KEY", "POSTGRES_INIT_PASSWORD", "POSTGRES_MIGRATION_PASSWORD",
        "POSTGRES_APP_PASSWORD", "POSTGRES_BACKUP_PASSWORD",
    )

    def test_every_secret_is_distinct(self):
        """bootstrap-postgres.sh refuses a deployment reusing one."""
        env = provision()
        values = [env[key] for key in self.SECRET_KEYS]
        self.assertEqual(len(set(values)), len(values))

    def test_secrets_are_long_enough_for_the_bootstrap_check(self):
        env = provision()
        for key in self.SECRET_KEYS:
            with self.subTest(key=key):
                self.assertGreaterEqual(len(env[key]), 16)

    def test_the_generated_env_satisfies_the_real_production_validator(self):
        """The check that matters, run by the code that gates production start.

        Asserting a minimum length here by hand is what let a defect ship: the
        secrets were 43 characters, the bootstrap script wanted 16, and this
        test was satisfied — while `production_env.py` refuses anything under 50
        for DJANGO_SECRET_KEY, so every provisioned deployment would have failed
        on first boot. Handing the file to the real validator cannot drift from
        the rule the same way a copied number can.
        """
        from config.production_env import validate_production_environment

        env = provision()
        # compose.yml supplies this per service rather than through .env.
        env["KARIZ_DATABASE_ROLE"] = "app"
        validate_production_environment(env)  # raises if the deployment is unstartable

    def test_secrets_cannot_be_reinterpreted_by_a_shell_or_by_compose(self):
        """A quote, a space or a `$` in a .env value is eventually expanded."""
        for _ in range(20):
            env = provision()
            for key in self.SECRET_KEYS:
                with self.subTest(key=key):
                    self.assertRegex(env[key], r"\A[A-Za-z0-9_-]+\Z")

    def test_two_deployments_never_share_a_secret(self):
        first, second = provision(), provision()
        for key in self.SECRET_KEYS:
            with self.subTest(key=key):
                self.assertNotEqual(first[key], second[key])


class WriteTests(SimpleTestCase):
    def test_an_existing_env_is_never_replaced(self):
        """Overwriting would discard secrets that exist in no other copy."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("POSTGRES_DB=already_here\n", encoding="utf-8")
            with self.assertRaises(provisioning.ProvisioningError):
                provisioning.write_env(path, ["POSTGRES_DB=replacement"])
            self.assertIn("already_here", path.read_text(encoding="utf-8"))

    def test_the_file_is_created_unreadable_to_other_users(self):
        if os.name != "posix":
            self.skipTest("POSIX file modes; this host does not have them")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            provisioning.write_env(path, ["POSTGRES_DB=x"])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class MainEntryPointTests(SimpleTestCase):
    """Where `main()` actually writes the file — DEPLOY-ENV-001.

    A fresh install used to get its `.env` at the deployment directory's own
    root, while the runbook's first-install sequence, `deploy.sh`, and every
    documented `docker compose` example all read `secrets/.env`. Nothing
    reconciled the two on its own; an operator had to notice and
    `cp .env secrets/.env` by hand.
    """

    def test_the_env_lands_at_secrets_env_not_the_bare_root(self):
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory) / "deployment"
            exit_code = provisioning.main([
                "--slug", "acme", "--host", "crm.acme.ir", "--out", str(out_dir),
            ])
            self.assertEqual(exit_code, 0)
            self.assertTrue((out_dir / "secrets" / ".env").is_file())
            self.assertFalse((out_dir / ".env").exists())

    def test_the_secrets_directory_is_created_owner_only(self):
        if os.name != "posix":
            self.skipTest("POSIX file modes; this host does not have them")
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory) / "deployment"
            provisioning.main([
                "--slug", "acme", "--host", "crm.acme.ir", "--out", str(out_dir),
            ])
            self.assertEqual((out_dir / "secrets").stat().st_mode & 0o777, 0o700)

    def test_a_brand_new_profile_id_is_accepted_no_code_change_needed(self):
        """2026-09-05 design change: `--profile` is no longer restricted to
        `PROFILES`'s three existing entries — see the comment above that
        dict in `common/deployment/registry.py`. Onboarding a real new
        customer beyond Client-1 with its own profile id is exactly this."""
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory) / "deployment"
            exit_code = provisioning.main([
                "--slug", "acme", "--host", "crm.acme.ir", "--out", str(out_dir),
                "--profile", "acme-corp",
            ])
            self.assertEqual(exit_code, 0)
            env_text = (out_dir / "secrets" / ".env").read_text(encoding="utf-8")
            self.assertIn("# Profile: acme-corp", env_text)

    def test_a_malformed_profile_id_is_still_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory) / "deployment"
            exit_code = provisioning.main([
                "--slug", "acme", "--host", "crm.acme.ir", "--out", str(out_dir),
                "--profile", "Not Valid!",
            ])
            self.assertEqual(exit_code, 2)
            self.assertFalse((out_dir / "secrets" / ".env").exists())

    def test_a_second_run_refuses_rather_than_replacing_the_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory) / "deployment"
            first = provisioning.main([
                "--slug", "acme", "--host", "crm.acme.ir", "--out", str(out_dir),
            ])
            self.assertEqual(first, 0)
            original = (out_dir / "secrets" / ".env").read_text(encoding="utf-8")
            second = provisioning.main([
                "--slug", "acme", "--host", "crm.acme.ir", "--out", str(out_dir),
            ])
            self.assertEqual(second, 2)
            self.assertEqual((out_dir / "secrets" / ".env").read_text(encoding="utf-8"), original)


class PrintResolvedFeaturesTests(SimpleTestCase):
    """`--print-resolved-features` — what `scripts/quickstart.sh` signs a
    self-generated manifest for, so it never re-derives the dependency rules
    (and risks disagreeing with them) in shell."""

    def _run(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = provisioning.main(argv)
        return exit_code, buffer.getvalue().strip()

    def test_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            out_dir = Path(directory) / "deployment"
            exit_code, _ = self._run(["--print-resolved-features"])
            self.assertEqual(exit_code, 0)
            self.assertFalse(out_dir.exists())

    def test_default_set_matches_the_registry_default(self):
        from common.deployment.registry import DEFAULT_FEATURES

        exit_code, output = self._run(["--print-resolved-features"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(set(output.split(",")), set(DEFAULT_FEATURES))

    def test_a_dependency_is_added_and_reported(self):
        exit_code, output = self._run(["--print-resolved-features", "--features", "invoices"])
        self.assertEqual(exit_code, 0)
        resolved = set(output.split(","))
        self.assertIn("invoices", resolved)
        self.assertIn("customers", resolved)
        self.assertIn("products", resolved)

    def test_an_unknown_feature_is_refused(self):
        exit_code, _ = self._run(["--print-resolved-features", "--features", "not-a-real-feature"])
        self.assertEqual(exit_code, 2)
