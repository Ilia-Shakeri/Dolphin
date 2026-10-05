"""What the image build may see (2.40.0): never a signed manifest or dev settings."""

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]


class DockerContextTests(SimpleTestCase):
    def test_the_signed_manifest_and_dev_settings_never_reach_the_image(self):
        ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        for entry in ("manifest.json", "config/devcheck_settings.py", ".claude", "docs", "*.md"):
            self.assertIn(entry, ignored)
        validator = (ROOT / "scripts" / "validate_image_content.py").read_text(encoding="utf-8")
        self.assertIn('"manifest.json"', validator)
        self.assertNotIn(".editorconfig", ignored)
