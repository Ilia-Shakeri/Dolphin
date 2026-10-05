"""`manual-paid/` is API only (2.40.15).

The panel never posts to it — the paid figure is the sum of real allocations —
while the endpoint and its rules stay for existing integrations
(BACKEND_SPEC.md, «Manual settlement of an invoice»).
"""

from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[2]


class ManualPaidSurfaceTests(SimpleTestCase):
    def test_no_panel_script_or_template_posts_to_it(self):
        for root in (ROOT / "common" / "static" / "common" / "js", ROOT / "common" / "templates", ROOT / "profiles" / "templates"):
            for path in root.rglob("*"):
                if path.suffix not in {".js", ".html", ".inc"}:
                    continue
                text = path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(("//", "*", "/*", "{%", "{#")):
                        continue
                    self.assertNotIn("manual-paid", line, f"{path.name}: {stripped[:80]}")

    def test_the_endpoint_still_exists_for_integrations(self):
        self.assertEqual(reverse("invoice-manual-paid", kwargs={"pk": 1}), "/api/v1/invoices/1/manual-paid/")

    def test_the_contract_is_documented(self):
        spec = (ROOT / "BACKEND_SPEC.md").read_text(encoding="utf-8")
        self.assertIn("**Status (2.40.15): API only, kept for compatibility.**", spec)
