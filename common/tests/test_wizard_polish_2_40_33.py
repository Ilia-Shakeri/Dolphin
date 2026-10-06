"""Wizards and delete controls (2.40.33).

Product owner, 2026-10-07: a red asterisk on required fields; «قبلی» with a
chevron pointing right; a red halo on a dialog's close button; delete as a
red trash icon with motion; campaigns and their members get selection and
bulk delete; a sub-campaign reads «کمپین (زیرکمپین)»; the supply-request
review counts product variety.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.models import User
from sales.campaigns import add_campaign_member, create_campaign
from sales.models import TargetAudienceMember

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "common" / "static" / "common" / "js"
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
TEMPLATES = [path for base in ("common/templates", "profiles/templates") for path in (ROOT / base).rglob("*.html")]


class WizardChromeTests(SimpleTestCase):
    def test_every_previous_button_points_right_and_next_points_left(self):
        # The RTL icon sheet mirrors direction glyphs: `di-left` draws «›».
        for path in TEMPLATES:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r'data-dolphin-stepper-action="previous"><i class="([^"]+)"', text):
                with self.subTest(path=path.name):
                    self.assertIn("di-left", match.group(1))
            for match in re.finditer(r'data-dolphin-stepper-action="next">[^<]*<i class="([^"]+)"', text):
                with self.subTest(path=path.name):
                    self.assertIn("di-right", match.group(1))

    def test_required_labels_are_read_from_the_controls(self):
        module = (JS / "ui" / "required-labels.js").read_text(encoding="utf-8")
        self.assertIn('label.classList.toggle("required", control.required || control.hasAttribute("aria-required"))', module)
        self.assertIn("setupRequiredLabels();", (JS / "main.js").read_text(encoding="utf-8"))

    def test_the_close_button_has_its_halo_over_the_kits_hover(self):
        self.assertIn("dialog .btn.btn-icon[data-close-dialog]:not(.btn-active):hover", CSS)
        self.assertIn("background-color: var(--bs-danger) !important;", CSS)


class TrashTests(SimpleTestCase):
    def test_bulk_delete_is_a_trash_icon_everywhere(self):
        for path in TEMPLATES:
            for button in re.findall(r'<button[^>]*select="delete_selected"[^>]*>', path.read_text(encoding="utf-8")):
                with self.subTest(path=path.name):
                    self.assertIn("btn-trash", button)
                    self.assertIn('aria-label="', button)

    def test_single_deletes_use_the_shared_button_and_motion(self):
        for name in ("ui/attachments.js", "features/customers/person-profile.js", "features/billing/shared.js"):
            with self.subTest(module=name):
                text = (JS / name).read_text(encoding="utf-8")
                self.assertIn("trashButton(", text)
                self.assertIn("removeWithMotion(", text)


class LabelTests(SimpleTestCase):
    def test_a_sub_campaign_reads_parent_then_child_in_brackets(self):
        labels = (JS / "core" / "labels.js").read_text(encoding="utf-8")
        self.assertIn("`${campaign.parent_name} (${campaign.name})`", labels)
        for name in ("features/leads/leads.js", "features/billing/invoices.js", "features/campaigns/campaign-analytics.js"):
            self.assertIn("campaignLabel(campaign)", (JS / name).read_text(encoding="utf-8"))

    def test_the_supply_request_review_counts_products(self):
        orders = (JS / "features" / "billing" / "orders.js").read_text(encoding="utf-8")
        self.assertIn('["تنوع محصولات"', orders)
        self.assertNotIn('["تعداد اقلام"', orders)


class MemberBulkDeleteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="mb.admin", password="Strong-pass-274!", role=User.Role.PLATFORM_ADMIN)
        self.agent = User.objects.create_user(username="mb.agent", password="Strong-pass-274!", role=User.Role.SALES_AGENT)
        self.campaign = create_campaign(actor=self.admin, name="آزمون حذف")
        self.member = add_campaign_member(actor=self.admin, campaign=self.campaign, full_name="شخص", raw_phone="09125550111")

    def post(self, actor):
        client = APIClient()
        client.force_login(actor)
        return client.post("/api/v1/campaign-members/bulk-delete/", {"ids": [self.member.pk]}, format="json")

    def test_an_admin_removes_a_member(self):
        response = self.post(self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["deleted"], [self.member.pk])
        self.assertFalse(TargetAudienceMember.objects.filter(pk=self.member.pk).exists())

    def test_a_marketer_without_the_delete_permission_cannot(self):
        self.assertIn(self.post(self.agent).status_code, (403, 404))
        self.assertTrue(TargetAudienceMember.objects.filter(pk=self.member.pk).exists())
