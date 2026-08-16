"""Server-generated PDF: off by default, real when configured, never dishonest.

The renderer needs a browser binary, so most of this module runs with the
feature switched off — which is the state every current deployment is in. The
one test that produces an actual PDF is skipped where no browser exists, and
says so rather than passing vacuously.
"""

import shutil
import unittest
from decimal import Decimal
from pathlib import Path

from django.test import TestCase, override_settings

from accounts.models import User
from billing.services import create_invoice, issue_invoice
from common.pdf import (
    PdfRendererUnavailable,
    configured_renderer,
    render_html_to_pdf,
    renderer_is_available,
)
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product


def _browser_on_this_host():
    windows_chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    if windows_chrome.is_file():
        return str(windows_chrome)
    for candidate in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(candidate)
        if found:
            return found
    return ""


BROWSER = _browser_on_this_host()

SELF_CONTAINED_HTML = (
    '<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
    "<style>body{font-family:Tahoma,sans-serif}</style></head>"
    "<body><h1>فاکتور فروش</h1><p>مشتری آزمون — ۱۲۳۴</p></body></html>"
)


class RendererConfigurationTests(TestCase):
    def test_the_feature_is_off_unless_a_deployment_asks_for_it(self):
        self.assertEqual(configured_renderer(), "")
        self.assertFalse(renderer_is_available())

    @override_settings(PDF_RENDERER="chromium", PDF_CHROMIUM_BINARY="/nonexistent/browser")
    def test_a_configured_renderer_whose_binary_is_missing_is_not_available(self):
        self.assertFalse(renderer_is_available())
        with self.assertRaises(PdfRendererUnavailable):
            render_html_to_pdf(SELF_CONTAINED_HTML)

    def test_rendering_without_a_configured_renderer_raises_rather_than_returning_junk(self):
        with self.assertRaises(PdfRendererUnavailable):
            render_html_to_pdf(SELF_CONTAINED_HTML)

    @override_settings(PDF_RENDERER="weasyprint")
    def test_an_unsupported_renderer_name_is_refused_rather_than_guessed(self):
        self.assertFalse(renderer_is_available())
        with self.assertRaises(PdfRendererUnavailable):
            render_html_to_pdf(SELF_CONTAINED_HTML)


@unittest.skipUnless(BROWSER, "No Chromium/Chrome on this host to print with.")
class RealPdfOutputTests(TestCase):
    """Actually produce a PDF, because 'it would work' is not evidence."""

    def test_a_persian_page_becomes_a_real_pdf_with_embedded_fonts(self):
        with override_settings(PDF_RENDERER="chromium", PDF_CHROMIUM_BINARY=BROWSER):
            self.assertTrue(renderer_is_available())
            payload = render_html_to_pdf(SELF_CONTAINED_HTML)
        self.assertTrue(payload.startswith(b"%PDF"), payload[:16])
        self.assertGreater(len(payload), 2000)
        # Embedded fonts rather than a rasterised image: the text is real text,
        # which is what makes Persian shaping correct instead of merely pretty.
        self.assertIn(b"/Font", payload)

    @override_settings(PDF_RENDER_TIMEOUT_SECONDS=0)
    def test_a_timeout_is_reported_as_unavailable_not_as_an_empty_file(self):
        with override_settings(PDF_RENDERER="chromium", PDF_CHROMIUM_BINARY=BROWSER):
            with self.assertRaises(PdfRendererUnavailable):
                render_html_to_pdf(SELF_CONTAINED_HTML)


class DocumentPdfEndpointTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="pdf.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.other = User.objects.create_user(
            username="pdf.agent", password="Strong-pass-937!", role=User.Role.SALES_AGENT
        )
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری پی‌دی‌اف",
            phone={"raw_phone": "09121112222", "is_primary": True},
        )
        product = create_product(
            actor=self.manager, sku="PDF-1", name="کالای پی‌دی‌اف", current_price=Decimal("150.00")
        )
        warehouse = create_warehouse(actor=self.manager, code="pdfwh", name="انبار پی‌دی‌اف")
        record_stock_movement(
            actor=self.manager,
            warehouse=warehouse,
            product=product,
            movement_type=StockMovement.MovementType.OPENING,
            quantity=20,
            unit_cost=Decimal("90.00"),
        )
        self.invoice = issue_invoice(
            actor=self.manager,
            invoice=create_invoice(
                actor=self.manager,
                customer=customer,
                items=[{"product": product, "quantity": 2}],
                warehouse=warehouse,
            ),
        )
        self.client.force_login(self.manager)

    def test_the_print_page_hides_the_download_when_no_renderer_exists(self):
        content = self.client.get(f"/invoices/{self.invoice.pk}/print/").content.decode("utf-8")
        self.assertIn("چاپ / ذخیره PDF", content)
        self.assertNotIn("دانلود PDF", content)
        self.assertNotIn("print.pdf", content)

    @override_settings(PDF_RENDERER="chromium", PDF_CHROMIUM_BINARY=BROWSER or __file__)
    def test_the_print_page_offers_the_download_once_a_renderer_exists(self):
        content = self.client.get(f"/invoices/{self.invoice.pk}/print/").content.decode("utf-8")
        self.assertIn("دانلود PDF", content)
        self.assertIn(f"/invoices/{self.invoice.pk}/print.pdf", content)

    def test_without_a_renderer_the_endpoint_explains_itself_in_persian(self):
        response = self.client.get(f"/invoices/{self.invoice.pk}/print.pdf")
        self.assertEqual(response.status_code, 503)
        self.assertIn("تولید PDF در دسترس نیست", response.content.decode("utf-8"))

    def test_the_pdf_route_keeps_the_print_pages_object_scope(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(f"/invoices/{self.invoice.pk}/print.pdf").status_code, 404)
        self.assertEqual(self.client.get(f"/invoices/{self.invoice.pk}/print/").status_code, 404)

    def test_the_pdf_route_is_absent_when_the_feature_is_disabled(self):
        from common.deployment.profile import DeploymentProfile, override_active_profile
        from common.deployment.registry import ALL_FEATURES

        reduced = DeploymentProfile(
            profile_id="client-1",
            features=frozenset(ALL_FEATURES) - {"invoices"},
            source="signed-manifest",
        )
        with override_active_profile(reduced):
            self.assertEqual(self.client.get(f"/invoices/{self.invoice.pk}/print.pdf").status_code, 404)

    @unittest.skipUnless(BROWSER, "No Chromium/Chrome on this host to print with.")
    def test_a_configured_deployment_downloads_a_real_invoice_pdf(self):
        with override_settings(PDF_RENDERER="chromium", PDF_CHROMIUM_BINARY=BROWSER):
            response = self.client.get(f"/invoices/{self.invoice.pk}/print.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f"invoice-{self.invoice.number}.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    @unittest.skipUnless(BROWSER, "No Chromium/Chrome on this host to print with.")
    def test_the_printed_html_is_self_contained_so_the_renderer_fetches_nothing(self):
        from django.template.loader import render_to_string

        from common.pdf import inline_stylesheet

        response = self.client.get(f"/invoices/{self.invoice.pk}/print/")
        context = dict(response.context_data)
        context.update(pdf_mode=True, inline_css=inline_stylesheet())
        html = render_to_string("common/invoices/print.html", context)
        # No stylesheet link, no script, no favicon, and no toolbar: nothing for
        # the rendering browser to go and fetch. The toolbar is checked as
        # markup rather than as a bare string, because the inlined stylesheet
        # legitimately still contains the `.print-toolbar` rule.
        for reference in ("<link", "<script", "/static/", 'class="print-toolbar"'):
            self.assertNotIn(reference, html, reference)
        self.assertIn("<style>", html)
        self.assertIn(self.invoice.number, html)
