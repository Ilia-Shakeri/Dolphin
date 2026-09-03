"""White-label branding: `common.branding`, `common.models.BrandSettings`,
the `/api/v1/branding/` API, and what every page actually renders.

Three things are worth proving separately, matching the three controls the
feature deliberately keeps apart:

* the `custom_branding` feature gate really does override everything else —
  a row full of a customer's own name and logo still renders as Dolphin the
  moment the feature is off, exactly as if the row had never been written;
* only a Platform Admin may change it, at the API layer, not merely hidden
  from a lower role's navigation;
* the stored choice really does reach every surface that promised it would —
  the page `<title>`, the sidebar, the login screen, and the public logo
  route the login screen depends on before anyone has signed in.
"""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from billing.services import create_invoice, issue_invoice
from common import branding
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from common.models import MAX_LOGO_BYTES, BrandSettings
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-983!"
REAL_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
REAL_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
NOT_AN_IMAGE = b"this is not an image, just text pretending to be one"


def without_custom_branding():
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset({"custom_branding"}),
        source="signed-manifest",
    )


class BrandingFixtures(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user(username="brand.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="brand.agent", password=PASSWORD, role=User.Role.SALES_AGENT)


class ServiceTests(BrandingFixtures):
    def test_get_brand_settings_creates_the_singleton_once(self):
        first = branding.get_brand_settings()
        second = branding.get_brand_settings()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(BrandSettings.objects.count(), 1)

    def test_effective_brand_is_dolphin_when_the_feature_is_off(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        with override_active_profile(without_custom_branding()):
            result = branding.effective_brand()
        self.assertFalse(result["is_custom"])
        self.assertEqual(result["name"], branding.DEFAULT_BRAND_NAME)

    def test_effective_brand_is_dolphin_when_feature_on_but_nothing_set(self):
        result = branding.effective_brand()
        self.assertFalse(result["is_custom"])
        self.assertEqual(result["name"], branding.DEFAULT_BRAND_NAME)

    def test_effective_brand_reflects_a_saved_name(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        result = branding.effective_brand()
        self.assertTrue(result["is_custom"])
        self.assertEqual(result["name"], "تیارا")
        self.assertEqual(result["subtitle"], "")

    def test_a_database_failure_falls_back_to_dolphin_not_a_crash(self):
        """Rendered on every page, including the 500 handler itself — this
        must degrade, never raise a second exception on top of the first.
        """
        with patch("common.models.BrandSettings.objects") as mocked:
            mocked.get_or_create.side_effect = DatabaseError("connection lost")
            result = branding.effective_brand()
        self.assertFalse(result["is_custom"])
        self.assertEqual(result["name"], branding.DEFAULT_BRAND_NAME)

    def test_only_a_platform_admin_may_update_it(self):
        with self.assertRaises(BusinessPermissionDenied):
            branding.update_brand_settings(actor=self.agent, display_name="تیارا")
        self.assertEqual(branding.get_brand_settings().display_name, "")

    def test_a_name_only_update_leaves_a_previously_set_logo_alone(self):
        branding.update_brand_settings(actor=self.admin, logo_bytes=REAL_JPEG, logo_original_filename="a.jpg")
        branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        row = branding.get_brand_settings()
        self.assertEqual(row.display_name, "تیارا")
        self.assertTrue(row.has_logo)

    def test_a_logo_only_update_leaves_a_previously_set_name_alone(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        branding.update_brand_settings(actor=self.admin, logo_bytes=REAL_PNG, logo_original_filename="a.png")
        row = branding.get_brand_settings()
        self.assertEqual(row.display_name, "تیارا")
        self.assertEqual(row.logo_content_type, "image/png")

    def test_the_stored_content_type_is_sniffed_not_taken_from_the_caller(self):
        row = branding.update_brand_settings(
            actor=self.admin, logo_bytes=REAL_JPEG, logo_original_filename="lying-name.png",
        )
        self.assertEqual(row.logo_content_type, "image/jpeg")

    def test_a_non_image_upload_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            branding.update_brand_settings(actor=self.admin, logo_bytes=NOT_AN_IMAGE)
        self.assertFalse(branding.get_brand_settings().has_logo)

    def test_an_oversized_upload_is_refused(self):
        oversized = REAL_JPEG + b"\x00" * MAX_LOGO_BYTES
        with self.assertRaises(BusinessRuleError):
            branding.update_brand_settings(actor=self.admin, logo_bytes=oversized)

    def test_an_empty_upload_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            branding.update_brand_settings(actor=self.admin, logo_bytes=b"")

    def test_remove_logo_clears_every_logo_field(self):
        branding.update_brand_settings(actor=self.admin, logo_bytes=REAL_JPEG, logo_original_filename="a.jpg")
        branding.update_brand_settings(actor=self.admin, remove_logo=True)
        row = branding.get_brand_settings()
        self.assertFalse(row.has_logo)
        self.assertEqual(row.logo_content_type, "")
        self.assertIsNone(row.logo_size_bytes)

    def test_remove_and_replace_together_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            branding.update_brand_settings(actor=self.admin, logo_bytes=REAL_JPEG, remove_logo=True)

    def test_a_successful_update_is_audit_logged(self):
        row = branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        self.assertTrue(
            ActivityLog.objects.filter(operation="brand_settings.updated", object_id=str(row.pk)).exists()
        )

    def test_a_name_over_the_length_limit_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            branding.update_brand_settings(actor=self.admin, display_name="ا" * 81)


class BrandingAPITests(BrandingFixtures):
    def client_for(self, user):
        client = APIClient()
        client.force_login(user)
        return client

    def test_get_requires_platform_admin(self):
        response = self.client_for(self.agent).get("/api/v1/branding/")
        self.assertEqual(response.status_code, 403)

    def test_get_is_404_when_the_feature_is_off(self):
        with override_active_profile(without_custom_branding()):
            response = self.client_for(self.admin).get("/api/v1/branding/")
        self.assertEqual(response.status_code, 404)

    def test_platform_admin_can_read_and_update(self):
        client = self.client_for(self.admin)
        empty = client.get("/api/v1/branding/")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data["display_name"], "")
        self.assertFalse(empty.data["has_logo"])

        updated = client.post("/api/v1/branding/", {"display_name": "تیارا"}, format="multipart")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["display_name"], "تیارا")

    def test_a_sales_agent_cannot_update_even_with_a_well_formed_request(self):
        response = self.client_for(self.agent).post(
            "/api/v1/branding/", {"display_name": "تیارا"}, format="multipart",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(branding.get_brand_settings().display_name, "")

    def test_uploading_a_logo_makes_it_downloadable_at_the_public_route(self):
        client = self.client_for(self.admin)
        response = client.post(
            "/api/v1/branding/",
            {"logo": SimpleUploadedFile("logo.jpg", REAL_JPEG, content_type="image/jpeg")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["has_logo"])

        # Public: no login needed, exactly like the default static logo it replaces.
        logo = APIClient().get("/api/v1/branding/logo/")
        self.assertEqual(logo.status_code, 200)
        self.assertEqual(logo.content, REAL_JPEG)
        self.assertEqual(logo["Content-Type"], "image/jpeg")

    def test_the_public_logo_route_is_404_with_no_logo_set(self):
        response = APIClient().get("/api/v1/branding/logo/")
        self.assertEqual(response.status_code, 404)

    def test_the_public_logo_route_is_404_when_the_feature_is_off_even_with_a_logo_saved(self):
        branding.update_brand_settings(actor=self.admin, logo_bytes=REAL_JPEG)
        with override_active_profile(without_custom_branding()):
            response = APIClient().get("/api/v1/branding/logo/")
        self.assertEqual(response.status_code, 404)

    def test_a_disallowed_file_is_refused_with_400_and_nothing_is_stored(self):
        client = self.client_for(self.admin)
        response = client.post(
            "/api/v1/branding/",
            {"logo": SimpleUploadedFile("note.txt", NOT_AN_IMAGE, content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(branding.get_brand_settings().has_logo)

    def test_remove_logo_through_the_api(self):
        client = self.client_for(self.admin)
        client.post(
            "/api/v1/branding/",
            {"logo": SimpleUploadedFile("logo.png", REAL_PNG, content_type="image/png")},
            format="multipart",
        )
        response = client.post("/api/v1/branding/", {"remove_logo": "true"}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["has_logo"])
        self.assertEqual(APIClient().get("/api/v1/branding/logo/").status_code, 404)


class TemplateRenderingTests(BrandingFixtures):
    """What a browser actually receives — not just what the API returns."""

    def test_default_pages_still_say_dolphin(self):
        page = self.client.get("/login/")
        self.assertContains(page, "Dolphin", status_code=200)
        self.assertNotContains(page, "/api/v1/branding/logo/")

    def test_a_custom_brand_reaches_the_pre_login_page(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا", logo_bytes=REAL_JPEG)
        page = self.client.get("/login/")
        self.assertContains(page, "تیارا", status_code=200)
        self.assertContains(page, "/api/v1/branding/logo/")

    def test_the_title_tag_uses_the_custom_name(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        self.client.force_login(self.admin)
        page = self.client.get("/")
        self.assertContains(page, "| تیارا</title>", status_code=200)
        self.assertNotContains(page, "| Dolphin</title>")

    def test_disabling_the_feature_reverts_every_page_to_dolphin_even_with_a_saved_row(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا", logo_bytes=REAL_JPEG)
        with override_active_profile(without_custom_branding()):
            page = self.client.get("/login/")
        self.assertNotContains(page, "تیارا", status_code=200)
        self.assertContains(page, "Dolphin")


class OtherSurfacesTests(BrandingFixtures):
    """Every page-eyebrow/footer mention this feature touched outside
    `base.html` itself — each was found and fixed by a live browser check
    that spotted a leftover hardcoded "Dolphin | دلفین" the automated tests
    up to that point had not looked at.
    """

    def test_the_dashboard_eyebrow_uses_the_custom_name(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        self.client.force_login(self.admin)
        page = self.client.get("/")
        self.assertContains(page, ">تیارا<", status_code=200)
        self.assertNotContains(page, "Dolphin | دلفین")

    def test_the_printed_invoice_brand_line_uses_the_custom_name(self):
        branding.update_brand_settings(actor=self.admin, display_name="تیارا")
        manager = User.objects.create_user(username="brand.mgr", password=PASSWORD, role=User.Role.SALES_MANAGER)
        customer = create_customer_with_phone(
            actor=manager, full_name="مشتری برند", phone={"raw_phone": "09121230000", "is_primary": True},
        )
        product = create_product(actor=manager, sku="BRAND-1", name="کالای برند", current_price=Decimal("100.00"))
        warehouse = create_warehouse(actor=manager, code="brandwh", name="انبار برند")
        record_stock_movement(
            actor=manager, warehouse=warehouse, product=product,
            movement_type=StockMovement.MovementType.OPENING, quantity=5, unit_cost=Decimal("50.00"),
        )
        invoice = issue_invoice(actor=manager, invoice=create_invoice(
            actor=manager, customer=customer, items=[{"product": product, "quantity": 1}], warehouse=warehouse,
        ))
        self.client.force_login(manager)
        page = self.client.get(f"/invoices/{invoice.pk}/print/")
        self.assertContains(page, '<p class="print-brand">تیارا</p>', status_code=200)
        self.assertContains(page, "این سند از سامانه تیارا صادر شده است")
        self.assertNotContains(page, "Dolphin | دلفین")


class SettingsPageAccessTests(BrandingFixtures):
    def test_a_platform_admin_can_open_the_settings_page(self):
        """Status code alone is not enough here — a wrong `template_name`
        still answers 200 with a different page's content, which is exactly
        the bug this test caught once (a stray leftover line, discovered
        through live browser verification, left `DolphinBrandingSettingsView.
        template_name` reassigned to the stock-valuation report's template
        after the class body's real assignment)."""
        self.client.force_login(self.admin)
        response = self.client.get("/branding/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "branding-form")
        self.assertTemplateUsed(response, "common/branding/settings.html")

    def test_a_sales_agent_gets_a_403_card_not_a_crash(self):
        self.client.force_login(self.agent)
        response = self.client.get("/branding/")
        self.assertEqual(response.status_code, 403)

    def test_the_page_is_404_when_the_feature_is_off(self):
        self.client.force_login(self.admin)
        with override_active_profile(without_custom_branding()):
            response = self.client.get("/branding/")
        self.assertEqual(response.status_code, 404)

    def test_the_nav_link_only_shows_for_a_platform_admin_with_the_feature_on(self):
        self.client.force_login(self.admin)
        with_feature = self.client.get("/")
        self.assertContains(with_feature, "برند و لوگوی پنل", status_code=200)
        with override_active_profile(without_custom_branding()):
            without_feature = self.client.get("/")
        self.assertNotContains(without_feature, "برند و لوگوی پنل", status_code=200)

        self.client.force_login(self.agent)
        agent_view = self.client.get("/")
        self.assertNotContains(agent_view, "برند و لوگوی پنل", status_code=200)
