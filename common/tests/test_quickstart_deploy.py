"""`scripts/quickstart.sh` — the one-command first install.

Running the real thing needs a Docker host, matching `test_deploy_script.py`'s
own reasoning for why it stops at text/plan assertions rather than executing
anything. `--dry-run` is what makes more than that possible here: every test
below runs the actual script as a subprocess with `--dry-run --skip-os-setup`
and inspects the plan it prints, rather than only pinning source text — proof
the argument handling, mutual-exclusion checks, and command ordering actually
work, not just that the right words appear in the file.
"""

import os
import subprocess
import tempfile
from pathlib import Path

from django.test import SimpleTestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "quickstart.sh"


class QuickstartScriptSyntaxTests(SimpleTestCase):
    def test_the_script_is_syntactically_valid_posix_sh(self):
        result = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class QuickstartDryRunTests(SimpleTestCase):
    """Each test is one real subprocess run, `--dry-run --skip-os-setup`."""

    def _run(self, *args, out=None):
        with tempfile.TemporaryDirectory() as scratch:
            target = out or str(Path(scratch) / "deployment")
            result = subprocess.run(
                ["sh", str(SCRIPT), "--dry-run", "--skip-os-setup", "--out", target, *args],
                capture_output=True,
                text=True,
                cwd=REPOSITORY_ROOT,
            )
            return result, target

    def test_reviewed_image_and_pre_signed_manifest_plan(self):
        result, target = self._run(
            "--slug", "acme", "--host", "crm.acme.ir",
            "--app-image", "ghcr.io/acme/dolphin-app@sha256:" + "a" * 64,
            "--manifest", __file__,  # any real, readable file stands in
            "--manifest-keys", "k1:AAAA",
            "--tls-cert", __file__, "--tls-key", __file__,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("docker pull ghcr.io/acme/dolphin-app@sha256", result.stdout)
        self.assertIn("scripts/new_deployment.py", result.stdout)
        normalized_stdout = result.stdout.replace("\\", "/")
        self.assertIn(f"--manifest-path {target.replace(chr(92), '/')}/secrets/manifest.json", normalized_stdout)
        self.assertIn("docker compose --env-file secrets/.env config --quiet", result.stdout)
        self.assertIn("./scripts/prepare-backup-volume.sh", result.stdout)
        self.assertIn("./scripts/deploy.sh ghcr.io/acme/dolphin-app@sha256", result.stdout)
        self.assertIn("would prompt to create the first Platform Admin", result.stdout)
        # The documented safe path: no build, no self-sign, no self-signed TLS.
        self.assertNotIn("build-image.sh", result.stdout)
        self.assertNotIn("self-sign", result.stdout.lower())

    def test_self_service_plan_builds_signs_and_generates_tls(self):
        result, _target = self._run(
            "--slug", "client1", "--host", "203.0.113.10",
            "--build", "--self-sign", "--self-signed-tls",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("./scripts/build-image.sh", result.stdout)
        self.assertIn("sign_deployment_manifest.py --generate-key", result.stdout)
        self.assertIn("signing for features:", result.stdout)
        self.assertIn("openssl req -x509", result.stdout)
        self.assertIn("browsers will warn", result.stdout)
        self.assertIn("REMINDER", result.stdout)

    def test_a_feature_choice_pulls_in_its_dependency_before_signing(self):
        result, _target = self._run(
            "--slug", "client1", "--host", "203.0.113.10",
            "--build", "--self-sign", "--self-signed-tls",
            "--features", "invoices",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        signing_line = next(
            line for line in result.stdout.splitlines() if "signing for features:" in line
        )
        self.assertIn("invoices", signing_line)
        self.assertIn("customers", signing_line)
        self.assertIn("products", signing_line)

    def test_missing_image_source_is_refused_with_a_clear_message(self):
        result, _target = self._run(
            "--slug", "acme", "--host", "crm.acme.ir",
            "--manifest", __file__, "--manifest-keys", "k1:AAAA",
            "--tls-cert", __file__, "--tls-key", __file__,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("image source is required", result.stderr)

    def test_image_source_is_exclusive_not_additive(self):
        result, _target = self._run(
            "--slug", "acme", "--host", "crm.acme.ir",
            "--app-image", "ghcr.io/acme/dolphin-app@sha256:" + "a" * 64, "--build",
            "--manifest", __file__, "--manifest-keys", "k1:AAAA",
            "--tls-cert", __file__, "--tls-key", __file__,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("mutually exclusive", result.stderr)

    def test_a_pre_signed_manifest_without_its_keys_is_refused(self):
        result, _target = self._run(
            "--slug", "acme", "--host", "crm.acme.ir",
            "--app-image", "ghcr.io/acme/dolphin-app@sha256:" + "a" * 64,
            "--manifest", __file__,
            "--tls-cert", __file__, "--tls-key", __file__,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--manifest-keys", result.stderr)

    def test_missing_slug_or_host_is_refused_before_anything_runs(self):
        result = subprocess.run(
            ["sh", str(SCRIPT), "--dry-run", "--host", "crm.acme.ir"],
            capture_output=True, text=True, cwd=REPOSITORY_ROOT,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--slug is required", result.stderr)

    def test_help_does_not_require_any_argument_and_does_not_touch_anything(self):
        result = subprocess.run(
            ["sh", str(SCRIPT), "--help"], capture_output=True, text=True, cwd=REPOSITORY_ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("quickstart.sh", result.stdout)

    def test_the_runtime_file_list_matches_what_actually_exists(self):
        """Every file this script promises to copy has to exist in the
        checkout it runs from — a stale list would fail loudly on someone's
        first deployment instead of here."""
        result, target = self._run(
            "--slug", "acme", "--host", "crm.acme.ir",
            "--app-image", "ghcr.io/acme/dolphin-app@sha256:" + "a" * 64,
            "--manifest", __file__, "--manifest-keys", "k1:AAAA",
            "--tls-cert", __file__, "--tls-key", __file__,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("missing from this checkout", result.stdout + result.stderr)


class QuickstartRuntimeFileListTests(SimpleTestCase):
    """The list this script copies (runbook 1.5) actually resolves, on disk,
    independent of a subprocess run — the direct check for what the dry-run
    test above only proves indirectly."""

    def test_every_listed_runtime_file_exists(self):
        text = SCRIPT.read_text(encoding="utf-8")
        block = text[text.index("for relative in") : text.index("do\n", text.index("for relative in"))]
        names = [
            token.rstrip("\\").strip()
            for line in block.splitlines()[1:]
            for token in line.split()
            if token.strip("\\").strip()
        ]
        self.assertTrue(names)
        for relative in names:
            with self.subTest(relative=relative):
                self.assertTrue(
                    (REPOSITORY_ROOT / relative).is_file(), f"{relative} is listed but missing"
                )
