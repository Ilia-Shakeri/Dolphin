from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "ops" / "SECURITY_SCANS.md"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell") or shutil.which(
    "powershell.exe"
)


class SecurityScanRunbookTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = RUNBOOK.read_text(encoding="utf-8")
        cls.powershell_blocks = re.findall(
            r"```powershell\r?\n(.*?)\r?\n```",
            cls.source,
            flags=re.DOTALL,
        )
        cls.powershell = "\n".join(cls.powershell_blocks)

    def test_all_artifact_and_scanner_images_are_digest_and_version_bound(self):
        for variable in (
            "$appImage",
            "$gitleaksImage",
            "$pipAuditImage",
            "$syftImage",
            "$grypeImage",
            "$testsslImage",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, self.powershell)
        self.assertIn("@sha256:[a-f0-9]{64}", self.powershell)
        self.assertIn(
            "exact released tool version was reviewed and resolved to an immutable registry digest",
            self.source,
        )
        self.assertIn("docker pull --platform linux/amd64", self.powershell)
        self.assertIn("Assert-LocalDigest", self.powershell)
        self.assertNotRegex(self.powershell, r"(?i):latest(?:\s|@|$)")
        self.assertNotIn("docker login", self.powershell.lower())

    def test_secret_scan_report_cannot_store_the_match_or_secret(self):
        template = self.source.split("$safeGitleaksTemplate = @'", maxsplit=1)[
            1
        ].split("'@", maxsplit=1)[0]
        for safe_field in ("RuleID", "File", "StartLine", "EndLine", "Commit"):
            self.assertIn(safe_field, template)
        for unsafe_field in (
            "{{ quote .Line }}",
            "{{ quote .Match }}",
            "{{ quote .Secret }}",
            "{{ quote .Author }}",
            "{{ quote .Email }}",
            "{{ quote .Message }}",
        ):
            self.assertNotIn(unsafe_field, template)
        self.assertIn("--redact=100", self.powershell)
        self.assertIn("gitleaks-safe-report.tmpl", self.powershell)
        self.assertNotIn("--baseline", self.powershell)

    def test_dependency_sbom_image_and_tls_commands_are_fail_closed(self):
        for option in (
            "--require-hashes",
            "--disable-pip",
            "--strict",
            "--vulnerability-service pypi",
        ):
            self.assertIn(option, self.powershell)
        self.assertNotIn("--ignore-vuln", self.powershell)
        self.assertIn("cyclonedx-json=/evidence/application-sbom.cdx.json", self.powershell)
        self.assertIn("syft-json=/evidence/application-sbom.syft.json", self.powershell)
        self.assertIn("GRYPE_DB_AUTO_UPDATE=false", self.powershell)
        self.assertIn("--fail-on high", self.powershell)
        self.assertNotIn("--only-fixed", self.powershell)
        self.assertIn("--jsonfile /evidence/tls-public.json", self.powershell)
        self.assertIn("$tlsTarget", self.powershell)
        self.assertIn("Any nonzero exit is no-go", self.source)

    def test_evidence_root_and_sealed_file_set_are_guarded(self):
        self.assertIn("must be outside the repository", self.source)
        self.assertIn("$repoParentPrefix", self.powershell)
        self.assertIn("$evidencePrefix.StartsWith($repoParentPrefix", self.powershell)
        self.assertIn("ReparsePoint", self.powershell)
        self.assertIn("INCOMPLETE", self.powershell)
        self.assertIn("COMPLETE_REVIEW_REQUIRED", self.powershell)
        self.assertIn("integrity.sha256", self.powershell)
        self.assertIn("out-of-band evidence anchor", self.source)
        self.assertIn("Duplicate integrity manifest path", self.powershell)
        self.assertIn("Sealed evidence file set changed", self.powershell)
        self.assertIn("Sealed evidence contains an unlisted file", self.powershell)
        self.assertNotIn("Remove-Item", self.powershell)
        self.assertIn("no broad or recursive delete command", self.source)
        self.assertIn("Only execution on the approved scan host", self.source)

    @unittest.skipUnless(POWERSHELL, "PowerShell is not installed.")
    def test_every_powershell_block_parses(self):
        self.assertGreaterEqual(len(self.powershell_blocks), 10)
        with tempfile.TemporaryDirectory() as temp_directory:
            for index, block in enumerate(self.powershell_blocks):
                with self.subTest(block=index):
                    script_path = Path(temp_directory) / f"scan-block-{index}.ps1"
                    script_path.write_text(block, encoding="utf-8")
                    escaped_path = str(script_path).replace("'", "''")
                    parser_command = (
                        "$tokens = $null; $errors = $null; "
                        "[System.Management.Automation.Language.Parser]::"
                        f"ParseFile('{escaped_path}', [ref]$tokens, [ref]$errors) "
                        "| Out-Null; if ($errors.Count -gt 0) { exit 1 }"
                    )
                    result = subprocess.run(
                        [
                            POWERSHELL,
                            "-NoProfile",
                            "-NonInteractive",
                            "-Command",
                            parser_command,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
