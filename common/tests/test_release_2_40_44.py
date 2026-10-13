"""The printed invoice, and each company's own print layout (2.40.44).

A new design for the printed invoice, and `print_customization`: the company's
logo, stamp, accent, line, footer and paper size, and three optional parts it
may leave off. Presentation only — every part the official invoice sets out
prints whatever is stored. Three controls, as everywhere: the feature, the
`print_settings.manage` capability, and the stored row.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common import print_settings
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES, DEFAULT_OFF_FEATURES, FEATURE_DEPENDENCIES
from common.models import PrintSettings
from common.tests.test_dashboard_insights import DashboardFixtures
from common.tests.test_ui_overhaul_console_avatars import ONE_PIXEL_PNG

PASSWORD = "Strong-pass-744!"
API = "/api/v1/print-settings/"
#: What the official invoice sets out; none of it may depend on the settings.
LEGAL_PARTS = (
    "مشخصات فروشنده", "مشخصات خریدار", "مشخصات کالا یا خدمات", "جمع مبلغ کل بعلاوه جمع مالیات و عوارض",
    "مبلغ به حروف:", "مهر و امضای فروشنده", "مهر و امضای خریدار",
)


def without_print_customization():
    return DeploymentProfile(
        profile_id="client-1", features=frozenset(ALL_FEATURES) - {"print_customization"}, source="signed-manifest",
    )


class PrintLayoutFixtures(DashboardFixtures):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="print.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.api = APIClient()
        self.api.force_login(self.admin)

    def post(self, client=None, **data):
        return (client or self.api).post(API, data, format="multipart")

    def print_page(self, invoice, user=None):
        self.client.force_login(user or self.admin)
        return self.client.get(f"/invoices/{invoice.pk}/print/")


class FeatureAndCapabilityTests(PrintLayoutFixtures):
    def test_it_is_an_opt_in_feature_that_needs_invoices(self):
        self.assertIn("print_customization", DEFAULT_OFF_FEATURES)
        self.assertEqual(FEATURE_DEPENDENCIES["print_customization"], frozenset({"invoices"}))

    def test_the_platform_admin_holds_the_capability_and_a_manager_does_not(self):
        self.assertEqual(self.api.get(API).status_code, 200)
        manager = APIClient()
        manager.force_login(self.manager)
        self.assertEqual(manager.get(API).status_code, 403)
        self.assertEqual(self.post(manager, tagline="x").status_code, 403)
        from accounts.module_permissions import MODULES_BY_KEY

        self.assertEqual(MODULES_BY_KEY["print_settings"].read, ("print_settings.manage",))

    def test_without_the_feature_the_api_is_absent_and_the_stored_row_is_ignored(self):
        self.post(accent_color="#123456", tagline="خط شرکت")
        invoice = self._an_issued_invoice()
        with override_active_profile(without_print_customization()):
            self.assertEqual(self.api.get(API).status_code, 404)
            layout = print_settings.effective_print_settings()
            page = self.print_page(invoice)
        self.assertFalse(layout["customized"])
        self.assertEqual(layout["accent_color"], print_settings.DEFAULT_ACCENT)
        self.assertNotContains(page, "خط شرکت")
        self.assertContains(page, f"--print-accent: {print_settings.DEFAULT_ACCENT};")
        # Turning the feature off keeps what was stored.
        self.assertEqual(PrintSettings.objects.get().tagline, "خط شرکت")


class UpdateTests(PrintLayoutFixtures):
    def test_a_partial_update_leaves_every_unsent_field_alone(self):
        self.post(show_warehouse="false", tagline="نخست")
        response = self.post(footer_text="شمارهٔ حساب: ۱۲۳\nشبا: IR00")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertFalse(data["show_warehouse"])
        self.assertTrue(data["show_payment_summary"])
        self.assertEqual(data["tagline"], "نخست")
        self.assertEqual(data["footer_text"], "شمارهٔ حساب: ۱۲۳\nشبا: IR00")

    def test_shapes_are_checked(self):
        self.assertEqual(self.post(accent_color="red").status_code, 400)
        self.assertEqual(self.post(paper_size="a3").status_code, 400)
        self.assertEqual(self.post(tagline="x" * 121).status_code, 400)
        refused = self.post(logo=SimpleUploadedFile("logo.png", b"not an image", content_type="image/png"))
        self.assertEqual(refused.status_code, 400)

    def test_images_are_stored_served_and_removed(self):
        response = self.post(logo=SimpleUploadedFile("l.png", ONE_PIXEL_PNG, content_type="image/png"),
                             stamp=SimpleUploadedFile("s.png", ONE_PIXEL_PNG, content_type="image/png"))
        self.assertTrue(response.json()["has_logo"] and response.json()["has_stamp"])
        image = self.api.get(f"{API}logo/")
        self.assertEqual((image.status_code, image["Content-Type"]), (200, "image/png"))
        self.assertEqual(self.api.get(f"{API}other/").status_code, 404)
        self.assertFalse(self.post(remove_logo="true").json()["has_logo"])
        self.assertEqual(self.api.get(f"{API}logo/").status_code, 404)
        self.assertTrue(ActivityLog.objects.filter(operation="print_settings.updated").exists())


class PrintedInvoiceTests(PrintLayoutFixtures):
    def test_the_company_layout_prints_and_the_legal_parts_always_do(self):
        self.post(
            accent_color="#aa3300", tagline="واردکنندهٔ قطعات", footer_text="شبا: IR000",
            show_warehouse="false", show_payment_summary="false", show_issuer="false",
            logo=SimpleUploadedFile("l.png", ONE_PIXEL_PNG, content_type="image/png"),
            stamp=SimpleUploadedFile("s.png", ONE_PIXEL_PNG, content_type="image/png"),
        )
        page = self.print_page(self._an_issued_invoice())
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "--print-accent: #aa3300;")
        self.assertContains(page, '<img class="print-logo" src="data:image/png;base64,')
        self.assertContains(page, '<img class="print-stamp" src="data:image/png;base64,')
        self.assertContains(page, "واردکنندهٔ قطعات")
        self.assertContains(page, '<div class="print-footer-text">شبا: IR000</div>')
        for part in ("<span>انبار:</span>", "<span>پرداخت‌شده</span>", "<span>مانده</span>", "صادرکننده:"):
            self.assertNotContains(page, part)
        for part in LEGAL_PARTS:
            self.assertContains(page, part)
        head = page.content.decode().split("<thead>")[1].split("</thead>")[0]
        self.assertEqual(head.count("<th>"), 11)  # the official invoice's eleven columns

    def test_the_standard_layout_keeps_every_optional_part(self):
        page = self.print_page(self._an_issued_invoice())
        for part in ("<span>انبار:</span>", "<span>پرداخت‌شده</span>", "<span>مانده</span>", "صادرکننده:"):
            self.assertContains(page, part)
        self.assertNotContains(page, "@page { size: A5")

    def test_a5_prints_on_a5(self):
        self.post(paper_size="a5")
        page = self.print_page(self._an_issued_invoice())
        self.assertContains(page, "<style>@page { size: A5; margin: 8mm; }</style>")
        self.assertContains(page, 'class="print-doc print-a5"')


class SamplePreviewTests(PrintLayoutFixtures):
    URL = "/invoices/print/sample/"

    def test_the_preview_is_a_labelled_sample_and_reads_no_invoice(self):
        self.client.force_login(self.admin)
        page = self.client.get(self.URL)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "پیش‌نمایش با دادهٔ نمونه — این سند واقعی نیست.")
        self.assertContains(page, "<h1>صورتحساب فروش کالا و خدمات</h1>")  # the sample is an official invoice
        for part in LEGAL_PARTS:
            self.assertContains(page, part)
        self.assertContains(page, "/settings/?tab=print")

    def test_only_the_preview_may_be_framed_and_only_by_this_site(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.URL)["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(self.client.get("/settings/")["X-Frame-Options"], "DENY")
        invoice = self._an_issued_invoice()
        self.assertEqual(self.print_page(invoice)["X-Frame-Options"], "DENY")

    def test_the_preview_needs_the_feature_and_the_capability(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(self.URL).status_code, 403)
        self.client.force_login(self.admin)
        with override_active_profile(without_print_customization()):
            self.assertEqual(self.client.get(self.URL).status_code, 404)

    def test_the_settings_page_offers_the_tab_only_to_whoever_may_use_it(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/settings/"), 'id="settings-tab-print"')
        self.client.force_login(self.manager)
        self.assertNotContains(self.client.get("/settings/"), 'id="settings-tab-print"')
        self.client.force_login(self.admin)
        with override_active_profile(without_print_customization()):
            self.assertNotContains(self.client.get("/settings/"), 'id="settings-tab-print"')
