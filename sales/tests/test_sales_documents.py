from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from sales.models import PostalStatusHistory, SalesDocument
from sales.services import (
    assign_lead,
    create_customer_with_phone,
    create_lead,
    mark_sale,
    register_sales_document,
    transition_postal_status,
)


class SalesDocumentContractTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="doc-manager", password="Strong-pass-983!", role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="doc-agent", password="Strong-pass-983!", role=User.Role.SALES_AGENT)
        self.other_agent = User.objects.create_user(username="doc-other-agent", password="Strong-pass-983!", role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.agent, full_name="مشتری سند", province="تهران", city="تهران",
            postal_code="1234567890", address="نشانی نخست",
        )
        self.lead = create_lead(actor=self.agent, customer=self.customer, source="manual")
        assign_lead(actor=self.manager, lead=self.lead, to_user=self.agent, reason="document scope")
        self.sale = mark_sale(actor=self.agent, lead=self.lead, total_amount=Decimal("10.00"), sold_at=timezone.now())
        self.document = register_sales_document(
            actor=self.manager, customer=self.customer, sale=self.sale,
            document_number="DOC-100", postal_status="ثبت اولیه", notes="یادداشت",
        )

    def test_registration_snapshots_address_and_creates_history_and_safe_audit(self):
        self.customer.province = "فارس"
        self.customer.city = "شیراز"
        self.customer.postal_code = "9999999999"
        self.customer.address = "نشانی دوم"
        self.customer.save(update_fields=["province", "city", "postal_code", "address", "updated_at"])
        self.document.refresh_from_db()
        self.assertEqual(
            (self.document.province_snapshot, self.document.city_snapshot, self.document.postal_code_snapshot, self.document.address_snapshot),
            ("تهران", "تهران", "1234567890", "نشانی نخست"),
        )
        history = self.document.postal_history.get()
        self.assertEqual((history.from_status, history.to_status, history.changed_by), ("", "ثبت اولیه", self.manager))
        log = ActivityLog.objects.get(operation="sales_document.registered", object_id=str(self.document.pk))
        self.assertNotIn("یادداشت", str(log.safe_changes))
        self.assertNotIn("نشانی نخست", str(log.safe_changes))

    def test_transition_is_service_owned_append_only_and_audited(self):
        changed = transition_postal_status(
            actor=self.manager, document=self.document, to_status="تحویل پست", reason="تحویل حضوری",
        )
        self.assertEqual(changed.postal_status, "تحویل پست")
        self.assertEqual(changed.postal_history.count(), 2)
        latest = changed.postal_history.first()
        self.assertEqual((latest.from_status, latest.to_status), ("ثبت اولیه", "تحویل پست"))
        log = ActivityLog.objects.get(operation="sales_document.postal_status_changed", object_id=str(changed.pk))
        self.assertEqual(log.safe_changes["postal_from"], "ثبت اولیه")
        self.assertTrue(log.safe_changes["reason_provided"])
        with self.assertRaises(ProtectedError):
            changed.delete()

    def test_audit_failure_rolls_back_registration_and_transition(self):
        with mock.patch("sales.services.log_activity", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                register_sales_document(
                    actor=self.manager, customer=self.customer,
                    document_number="DOC-ROLLBACK", postal_status="ثبت",
                )
        self.assertFalse(SalesDocument.objects.filter(document_number="DOC-ROLLBACK").exists())
        old_status = self.document.postal_status
        with mock.patch("sales.services.log_activity", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                transition_postal_status(actor=self.manager, document=self.document, to_status="در مسیر")
        self.document.refresh_from_db()
        self.assertEqual(self.document.postal_status, old_status)
        self.assertEqual(self.document.postal_history.count(), 1)

    def test_api_scopes_direct_ids_and_blocks_agent_mutation(self):
        hidden_customer = create_customer_with_phone(actor=self.other_agent, full_name="مشتری پنهان")
        hidden_lead = create_lead(actor=self.other_agent, customer=hidden_customer)
        assign_lead(actor=self.manager, lead=hidden_lead, to_user=self.other_agent, reason="hidden")
        hidden_document = register_sales_document(
            actor=self.manager, customer=hidden_customer,
            document_number="DOC-HIDDEN", postal_status="ثبت",
        )
        client = APIClient()
        client.force_authenticate(self.agent)
        self.assertEqual(client.get(f"/api/v1/sales-documents/{self.document.pk}/").status_code, 200)
        self.assertEqual(client.get(f"/api/v1/sales-documents/{hidden_document.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/v1/sales-documents/{hidden_document.pk}/postal-history/").status_code, 404)
        self.assertEqual(client.post("/api/v1/sales-documents/", {"customer": self.customer.pk, "document_number": "BAD", "postal_status": "ثبت"}, format="json").status_code, 403)
        self.assertEqual(client.post(f"/api/v1/sales-documents/{self.document.pk}/transition-postal-status/", {"to_status": "بد"}, format="json").status_code, 403)
        self.assertEqual(client.post(f"/api/v1/sales-documents/{self.document.pk}/deactivate/").status_code, 403)
        # Both verbs are unsupported by this viewset for anyone — but DRF
        # checks permissions before it checks whether the verb even exists
        # (`APIView.dispatch` calls `initial()`, which includes
        # `check_permissions()`, before it looks up a handler), so a caller
        # who also lacks the write capability sees 403, not 405. A caller who
        # *does* hold it would still get 405 — the verb is simply never
        # wired to anything, for anyone.
        self.assertEqual(client.delete(f"/api/v1/sales-documents/{self.document.pk}/").status_code, 403)
        self.assertEqual(client.patch(f"/api/v1/sales-documents/{self.document.pk}/", {"postal_status": "بد"}, format="json").status_code, 403)

    def test_manager_filters_validates_relations_and_deactivates_without_delete(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        filtered = client.get("/api/v1/sales-documents/?province=تهران&city=تهران&postal_status=ثبت%20اولیه&is_active=true")
        self.assertEqual(filtered.status_code, 200, filtered.data)
        self.assertEqual(filtered.data["count"], 1)
        mismatch_customer = create_customer_with_phone(actor=self.manager, full_name="مشتری دوم")
        mismatch = client.post(
            "/api/v1/sales-documents/",
            {"customer": mismatch_customer.pk, "sale": self.sale.pk, "document_number": "DOC-MISMATCH", "postal_status": "ثبت"},
            format="json",
        )
        self.assertEqual(mismatch.status_code, 400)
        duplicate = client.post(
            "/api/v1/sales-documents/",
            {"customer": self.customer.pk, "document_number": "DOC-100", "postal_status": "ثبت"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 409)
        deactivated = client.post(f"/api/v1/sales-documents/{self.document.pk}/deactivate/")
        self.assertEqual(deactivated.status_code, 200)
        self.assertFalse(deactivated.data["is_active"])
        blocked = client.post(
            f"/api/v1/sales-documents/{self.document.pk}/transition-postal-status/",
            {"to_status": "در مسیر"}, format="json",
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertTrue(SalesDocument.objects.filter(pk=self.document.pk).exists())

    def test_server_fields_and_multiline_identity_values_are_rejected(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        server_field = client.post(
            "/api/v1/sales-documents/",
            {"customer": self.customer.pk, "document_number": "DOC-X", "postal_status": "ثبت", "province_snapshot": "جعلی"},
            format="json",
        )
        self.assertEqual(server_field.status_code, 400)
        self.assertIn("province_snapshot", server_field.data)
        multiline = client.post(
            "/api/v1/sales-documents/",
            {"customer": self.customer.pk, "document_number": "DOC\nBAD", "postal_status": "ثبت"},
            format="json",
        )
        self.assertEqual(multiline.status_code, 400)


class SalesDocumentReportTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="report-doc-manager", password="Strong-pass-983!", role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="report-doc-agent", password="Strong-pass-983!", role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(actor=self.agent, full_name="مشتری گزارش", province="تهران", city="تهران")
        self.lead = create_lead(actor=self.agent, customer=self.customer)
        assign_lead(actor=self.manager, lead=self.lead, to_user=self.agent, reason="report scope")
        self.document = register_sales_document(
            actor=self.manager, customer=self.customer, document_number="DOC-REPORT", postal_status="ثبت اولیه",
        )

    def test_report_uses_actor_scope_snapshots_current_status_and_filters(self):
        transition_postal_status(actor=self.manager, document=self.document, to_status="در مسیر")
        query = {
            "period_start": (timezone.now() - timedelta(days=1)).isoformat(),
            "period_end": (timezone.now() + timedelta(days=1)).isoformat(),
        }
        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.get("/api/v1/reports/sales-documents/", query)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], 1, response.data)
        self.assertEqual(response.data["by_geography"], [{"province": "تهران", "city": "تهران", "count": 1}])
        self.assertEqual(response.data["by_postal_status"], [{"postal_status": "در مسیر", "count": 1}])
        no_match = client.get("/api/v1/reports/sales-documents/", {**query, "province": "فارس"})
        self.assertEqual(no_match.data["total"], 0)
        invalid = client.get("/api/v1/reports/sales-documents/", {"period_start": query["period_end"], "period_end": query["period_start"]})
        self.assertEqual(invalid.status_code, 400)

    def test_browser_routes_are_scoped_and_controls_match_role(self):
        self.client.force_login(self.agent)
        own = self.client.get(f"/sales-documents/{self.document.pk}/")
        self.assertEqual(own.status_code, 200)
        self.assertNotContains(own, 'id="postal-transition-form"')
        self.assertContains(own, "اسناد فروش داخلی")
        self.client.force_login(self.manager)
        manager = self.client.get(f"/sales-documents/{self.document.pk}/")
        self.assertContains(manager, 'id="postal-transition-form"')
        self.assertEqual(self.client.get("/reports/sales-documents/").status_code, 200)
