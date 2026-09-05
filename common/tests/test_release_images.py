import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase
import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yml"
RESTORE_COMPOSE = ROOT / "compose.restore-verify.yml"
DOCKERFILE = ROOT / "Dockerfile"
VALIDATOR = ROOT / "scripts" / "validate_release_images.py"
# SECURITY_SCANS.md was merged into DOLPHIN_DEPLOYMENT_RUNBOOK.md (2026-09-01,
# one ops doc per direct product-owner decision); its content is intact as one
# section of that file, isolated below so an `assertNotIn` over `source` still
# means "not in the security-scans procedure" rather than "not anywhere in the
# whole 5000-line merged file" (which a phrase like "docker build" legitimately
# appears elsewhere in, in an unrelated context).
SECURITY_SCANS = ROOT / "docs" / "ops" / "DOLPHIN_DEPLOYMENT_RUNBOOK.md"


def _security_scans_section():
    text = SECURITY_SCANS.read_text(encoding="utf-8")
    marker = "*(from `docs/ops/SECURITY_SCANS.md`)*"
    start = text.index(marker) + len(marker)
    next_marker = text.find("*(from `docs/ops/", start)
    end = next_marker if next_marker != -1 else len(text)
    return text[start:end]


class ReleaseImageContractTests(SimpleTestCase):
    def test_security_scan_runbook_binds_source_image_tools_and_outputs(self):
        source = _security_scans_section()
        for variable in (
            "$approvedReleaseCommit",
            "$appImage",
            "$postgresImage",
            "$nginxImage",
            "$pythonBaseImage",
            "$gitleaksImage",
            "$pipAuditImage",
            "$syftImage",
            "$grypeImage",
            "$testsslImage",
        ):
            self.assertIn(variable, source)
        for artifact in (
            "source-secrets.redacted.json",
            "python-dependencies.json",
            "tls-public.json",
        ):
            self.assertIn(artifact, source)
        for artifact_pattern in (
            "${artifactName}-sbom.cdx.json",
            "${artifactName}-sbom.syft.json",
            "${artifactName}-vulnerabilities.json",
        ):
            self.assertIn(artifact_pattern, source)
        self.assertIn("runtime_images = $runtimeImages", source)
        self.assertIn("python_build_base_image = $pythonBaseImage", source)
        self.assertIn("repository@sha256", source)
        self.assertIn("--require-hashes --disable-pip --strict", source)
        self.assertIn("--redact=100", source)
        self.assertIn("--fail-on high", source)
        self.assertNotIn(":latest", source)
        self.assertNotIn("docker build", source)

    def test_compose_uses_only_required_digest_inputs(self):
        source = COMPOSE.read_text(encoding="utf-8")
        compose = yaml.safe_load(source)
        services = compose["services"]

        for service in ("db", "db-bootstrap", "db-finalize", "backup"):
            self.assertIn("${DOLPHIN_POSTGRES_IMAGE:?", services[service]["image"])
        for service in ("migrate", "web"):
            self.assertIn("${DOLPHIN_APP_IMAGE:?", services[service]["image"])
            self.assertNotIn("build", services[service])
        self.assertIn("${DOLPHIN_NGINX_IMAGE:?", services["nginx"]["image"])
        for mutable_ref in ("postgres:17-alpine", "nginx:1.27-alpine", "build: ."):
            self.assertNotIn(mutable_ref, source)

        restore_source = RESTORE_COMPOSE.read_text(encoding="utf-8")
        restore_service = yaml.safe_load(restore_source)["services"]["restore-verify"]
        self.assertIn("${DOLPHIN_POSTGRES_IMAGE:?", restore_service["image"])
        self.assertNotIn("build", restore_service)
        self.assertNotIn("postgres:17-alpine", restore_source)

    def test_dockerfile_requires_a_reviewed_base_input(self):
        source = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("ARG PYTHON_BASE_IMAGE", source)
        self.assertGreaterEqual(source.count("ARG PYTHON_BASE_IMAGE"), 2)
        self.assertIn("FROM ${PYTHON_BASE_IMAGE}", source)
        self.assertNotIn("FROM python:", source)
        self.assertIn("@sha256:[0-9a-f]{64}", source)
        self.assertIn("sys.implementation.name == 'cpython'", source)
        self.assertIn("sys.version_info[:2] == (3, 13)", source)
        self.assertGreaterEqual(source.count("ARG TARGETPLATFORM"), 2)
        self.assertIn('test "${TARGETPLATFORM}" = "linux/amd64"', source)
        self.assertIn("--only-binary=:all:", source)
        self.assertIn("--require-hashes", source)

    def test_validator_checks_all_four_refs_without_printing_them(self):
        source = VALIDATOR.read_text(encoding="utf-8")
        for name in (
            "DOLPHIN_APP_IMAGE",
            "PYTHON_BASE_IMAGE",
            "DOLPHIN_POSTGRES_IMAGE",
            "DOLPHIN_NGINX_IMAGE",
        ):
            self.assertIn(f'"{name}"', source)
        self.assertNotIn("print(value", source)

    def test_validator_accepts_exact_refs_and_rejects_mutable_or_bad_digest(self):
        exact = "registry.example/dolphin@sha256:" + "a" * 64
        environment = {
            **os.environ,
            "DOLPHIN_APP_IMAGE": exact,
            "PYTHON_BASE_IMAGE": exact,
            "DOLPHIN_POSTGRES_IMAGE": exact,
            "DOLPHIN_NGINX_IMAGE": exact,
        }
        accepted = subprocess.run(
            [sys.executable, str(VALIDATOR)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertNotIn(exact, accepted.stdout + accepted.stderr)

        for bad_ref in ("postgres:17-alpine", "repo/app@sha256:" + "A" * 64, "repo/app@sha256:abc"):
            with self.subTest(bad_ref=bad_ref):
                rejected_environment = {**environment, "DOLPHIN_APP_IMAGE": bad_ref}
                rejected = subprocess.run(
                    [sys.executable, str(VALIDATOR)],
                    cwd=ROOT,
                    env=rejected_environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertNotEqual(rejected.returncode, 0)
                self.assertNotIn(bad_ref, rejected.stdout + rejected.stderr)
