import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


class HtmlBrandingRegressionTests(SimpleTestCase):
    def test_first_party_html_has_only_kariz_branding(self):
        root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, str(root / "scripts" / "check_html_branding.py")],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
