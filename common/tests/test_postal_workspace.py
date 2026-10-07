"""Postal tracking in two panes (2.40.34).

Product owner, 2026-10-07: «صفحهٔ رهگیری پستی باید شبیه صفحهٔ گفت‌وگوها شود و
۲ تکه شود و ظاهر بهتر و اپشن‌های بیشتر داشته باشد».
"""

from pathlib import Path

from django.test import SimpleTestCase, TestCase

from accounts.models import User

ROOT = Path(__file__).resolve().parents[2]
JS = ROOT / "common" / "static" / "common" / "js" / "features" / "sales"
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")


class PageTests(TestCase):
    def test_the_page_has_the_list_beside_the_shipment(self):
        manager = User.objects.create_user(username="pw.manager", password="Strong-pass-274!", role=User.Role.SALES_MANAGER)
        self.client.force_login(manager)
        page = self.client.get("/sales-documents/").content.decode("utf-8")
        self.assertIn('id="postal-workspace"', page)
        self.assertIn('class="postal-list-pane', page)
        self.assertIn('id="postal-detail"', page)
        self.assertIn('data-can-manage="true"', page)
        # What the list had stays: search, filters, creation, paging.
        for marker in ('id="sales-document-search"', 'id="sales-document-filter-toggle"', 'id="open-create-sales-document"', 'id="sales-documents-pagination"'):
            self.assertIn(marker, page)


class ScriptTests(SimpleTestCase):
    def test_a_card_opens_its_shipment_and_the_address_keeps_it(self):
        listing = (JS / "sales-documents.js").read_text(encoding="utf-8")
        self.assertIn('url.searchParams.set("doc", id)', listing)
        self.assertIn('new URLSearchParams(window.location.search).get("doc")', listing)
        self.assertIn('onRealtime(["sales_document"]', listing)

    def test_the_pane_offers_the_everyday_actions(self):
        pane = (JS / "postal-pane.js").read_text(encoding="utf-8")
        for needle in ("transition-postal-status/", "navigator.clipboard.writeText(item.document_number)",
                       "/postal-history/", "`/customers/${item.customer}/`", "`/sales-documents/${item.id}/`",
                       'workspace.dataset.canManage === "true"'):
            self.assertIn(needle, pane)

    def test_a_phone_shows_one_pane_at_a_time(self):
        self.assertIn(".postal-workspace.is-viewing .postal-list-pane { display: none; }", CSS)
