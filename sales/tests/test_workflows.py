from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from sales.models import Customer, CustomerPhone, Interaction, LeadAssignmentHistory, Product, Sale
from sales.selectors import customers_for, leads_for
from sales.services import assign_lead, cancel_or_correct_sale, cancel_sale, create_customer_phone, create_customer_with_phone, create_lead, deactivate_product, mark_sale, reassign_lead, update_customer, update_customer_phone, update_lead, update_product
from sales.exceptions import BusinessPermissionDenied, BusinessRuleError


class CoreWorkflowTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="manager", password="strong-pass-1", role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="agent", password="strong-pass-1", role=User.Role.SALES_AGENT)
        self.other = User.objects.create_user(username="other", password="strong-pass-1", role=User.Role.SALES_AGENT)
        self.customer = create_customer_with_phone(
            actor=self.agent,
            full_name="Test Customer",
            phone={"raw_phone": "09121234567", "is_primary": True},
        )
        self.lead = create_lead(actor=self.agent, customer=self.customer, source="manual")
        assign_lead(actor=self.manager, lead=self.lead, to_user=self.agent, reason="initial")

    def test_customer_can_have_multiple_leads(self):
        create_lead(actor=self.agent, customer=self.customer, source="repeat")
        self.assertEqual(self.customer.leads.count(), 2)

    def test_phone_duplicate_and_primary_constraints(self):
        with self.assertRaises(BusinessRuleError):
            create_customer_phone(actor=self.agent, customer=self.customer, raw_phone="+98 912 123 4567")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomerPhone.objects.create(
                customer=self.customer,
                raw_phone="+98 912 123 4567",
                normalized_phone="+989121234567",
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomerPhone.objects.create(
                customer=self.customer,
                raw_phone="09123334444",
                normalized_phone="+989123334444",
                is_primary=True,
            )
        self.assertEqual(CustomerPhone.objects.filter(customer=self.customer, is_active=True).count(), 1)

    def test_phone_partial_uniqueness_boundaries(self):
        other_customer = create_customer_with_phone(
            actor=self.agent,
            full_name="Other Customer",
            phone={"raw_phone": "09121234567", "is_primary": True},
        )
        self.assertEqual(other_customer.phones.get().normalized_phone, "+989121234567")
        inactive = create_customer_phone(
            actor=self.agent,
            customer=self.customer,
            raw_phone="09121234567",
            is_active=False,
        )
        self.assertFalse(inactive.is_active)
        with self.assertRaises(BusinessRuleError):
            create_customer_phone(actor=self.agent, customer=self.customer, raw_phone="09121234567")

    def test_phone_update_conflict_rolls_back(self):
        duplicate = create_customer_phone(
            actor=self.agent,
            customer=self.customer,
            raw_phone="09121234567",
            is_active=False,
        )
        with self.assertRaises(BusinessRuleError):
            update_customer_phone(actor=self.agent, phone=duplicate, is_active=True)
        duplicate.refresh_from_db()
        self.assertFalse(duplicate.is_active)
        self.assertEqual(duplicate.normalized_phone, "+989121234567")

        second_primary = create_customer_phone(
            actor=self.agent,
            customer=self.customer,
            raw_phone="09123334444",
            is_primary=True,
            is_active=False,
        )
        with self.assertRaises(BusinessRuleError):
            update_customer_phone(actor=self.agent, phone=second_primary, is_active=True)
        second_primary.refresh_from_db()
        self.assertFalse(second_primary.is_active)
        self.assertTrue(second_primary.is_primary)

    def test_reassignment_has_history_audit_and_removes_old_scope(self):
        initial = LeadAssignmentHistory.objects.get(lead=self.lead)
        self.assertIsNone(initial.from_user)
        self.assertEqual(initial.to_user, self.agent)
        self.assertEqual(initial.changed_by, self.manager)
        self.assertEqual(initial.reason, "initial")
        reassign_lead(actor=self.manager, lead=self.lead, to_user=self.other, reason="load")
        self.assertEqual(LeadAssignmentHistory.objects.filter(lead=self.lead).count(), 2)
        latest = LeadAssignmentHistory.objects.filter(lead=self.lead).order_by("-changed_at", "-id").first()
        self.assertEqual(latest.from_user, self.agent)
        self.assertEqual(latest.to_user, self.other)
        self.assertEqual(latest.changed_by, self.manager)
        self.assertEqual(latest.reason, "load")
        initial.refresh_from_db()
        self.assertIsNone(initial.from_user)
        self.assertEqual(initial.to_user, self.agent)
        self.assertTrue(ActivityLog.objects.filter(operation="lead.reassigned", object_id=str(self.lead.pk)).exists())
        self.assertFalse(leads_for(self.agent).filter(pk=self.lead.pk).exists())
        self.assertTrue(leads_for(self.other).filter(pk=self.lead.pk).exists())

    def test_assignment_rejects_inactive_target(self):
        self.other.is_active = False
        self.other.save(update_fields=["is_active", "updated_at"])
        with self.assertRaises(BusinessRuleError):
            reassign_lead(actor=self.manager, lead=self.lead, to_user=self.other)
        self.assertEqual(LeadAssignmentHistory.objects.filter(lead=self.lead).count(), 1)

    def test_reassignment_rolls_back_when_audit_write_fails(self):
        with mock.patch("sales.services.log_activity", side_effect=RuntimeError("audit failed")):
            with self.assertRaises(RuntimeError):
                reassign_lead(actor=self.manager, lead=self.lead, to_user=self.other)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to, self.agent)
        self.assertEqual(LeadAssignmentHistory.objects.filter(lead=self.lead).count(), 1)

    def test_assignment_fields_must_be_all_set_or_all_empty(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.customer.leads.create(created_by=self.agent, assigned_to=self.agent)

    def test_sale_price_is_snapshotted(self):
        product = Product.objects.create(
            sku="SKU-1",
            name="Product",
            current_price=Decimal("100.00"),
            created_by=self.manager,
            updated_by=self.manager,
        )
        sale = mark_sale(actor=self.agent, lead=self.lead, product=product, quantity=2, sold_at=timezone.now())
        product.current_price = Decimal("150.00")
        product.save(update_fields=["current_price", "updated_at"])
        sale.refresh_from_db()
        self.assertEqual(sale.customer, self.lead.customer)
        self.assertEqual(sale.sold_by, self.agent)
        self.assertEqual(sale.unit_price_snapshot, Decimal("100.00"))
        self.assertEqual(sale.total_amount, Decimal("200.00"))

    def test_database_rejects_negative_money(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(
                sku="NEGATIVE",
                name="Bad Product",
                current_price=Decimal("-1.00"),
                created_by=self.manager,
                updated_by=self.manager,
            )

    def test_inactive_actor_cannot_use_service(self):
        self.agent.is_active = False
        self.agent.save(update_fields=["is_active", "updated_at"])
        with self.assertRaises(BusinessPermissionDenied):
            create_customer_with_phone(actor=self.agent, full_name="Blocked")

    def test_unknown_role_fails_closed(self):
        invalid = User(username="invalid", role="bad_role")
        self.assertFalse(customers_for(invalid).exists())
        self.assertFalse(leads_for(invalid).exists())

    def test_lead_service_rejects_server_status(self):
        with self.assertRaises(BusinessRuleError):
            create_lead(actor=self.agent, customer=self.customer, status="bypass")

    def test_company_it_operational_writes_fail_closed(self):
        company_it = User.objects.create_user(username="company-it", password="strong-pass-1", role=User.Role.COMPANY_IT)
        client = APIClient()
        client.force_authenticate(company_it)
        self.assertEqual(client.get("/api/v1/customers/").status_code, 200)
        self.assertEqual(client.post("/api/v1/customers/", {"full_name": "Blocked"}, format="json").status_code, 403)

    def test_large_computed_sale_amount_is_rejected(self):
        product = Product.objects.create(
            sku="MAX",
            name="Max Product",
            current_price=Decimal("1.00"),
            created_by=self.manager,
            updated_by=self.manager,
        )
        with self.assertRaises(BusinessRuleError):
            mark_sale(actor=self.agent, lead=self.lead, product=product, quantity=10000000000000000, sold_at=timezone.now())

    def test_database_rejects_invalid_sale_state(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sale.objects.create(
                lead=self.lead,
                customer=self.customer,
                sold_by=self.agent,
                quantity=1,
                total_amount=1,
                status="bad",
                sold_at=timezone.now(),
            )

    def test_database_rejects_invalid_sale_amount_snapshots(self):
        product = Product.objects.create(
            sku="SNAPSHOT-GUARD",
            name="Snapshot Guard",
            current_price=2,
            created_by=self.manager,
            updated_by=self.manager,
        )
        invalid_rows = [
            {"product": None, "unit_price_snapshot": 1, "quantity": 1, "total_amount": 1},
            {"product": product, "unit_price_snapshot": -1, "quantity": 1, "total_amount": 1},
            {"product": product, "unit_price_snapshot": 1, "quantity": 1, "total_amount": -1},
            {"product": product, "unit_price_snapshot": 2, "quantity": 3, "total_amount": 5},
        ]
        for fields in invalid_rows:
            with self.subTest(fields=fields), self.assertRaises(IntegrityError), transaction.atomic():
                Sale.objects.create(
                    lead=self.lead,
                    customer=self.customer,
                    sold_by=self.agent,
                    sold_at=timezone.now(),
                    **fields,
                )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sale.objects.create(
                lead=self.lead,
                customer=self.customer,
                sold_by=self.agent,
                quantity=0,
                total_amount=0,
                sold_at=timezone.now(),
            )
        product = Product.objects.create(
            sku="NO-SNAPSHOT",
            name="No Snapshot",
            current_price=1,
            created_by=self.manager,
            updated_by=self.manager,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sale.objects.create(
                lead=self.lead,
                customer=self.customer,
                sold_by=self.agent,
                product=product,
                quantity=1,
                unit_price_snapshot=None,
                total_amount=1,
                sold_at=timezone.now(),
            )

    def test_stale_updates_do_not_undo_reassignment_or_deactivation(self):
        stale_lead = self.lead
        stale_customer = Customer.objects.get(pk=self.customer.pk)
        reassign_lead(actor=self.manager, lead=self.lead, to_user=self.other)
        update_lead(actor=self.manager, lead=stale_lead, notes="manager note")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to, self.other)
        client = APIClient()
        client.force_authenticate(self.manager)
        client.post(f"/api/v1/customers/{self.customer.pk}/deactivate/")
        update_customer(actor=self.manager, customer=stale_customer, notes="kept")
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_repeat_deactivation_is_rejected_without_false_audit(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        first = client.post(f"/api/v1/customers/{self.customer.pk}/deactivate/")
        second = client.post(f"/api/v1/customers/{self.customer.pk}/deactivate/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(ActivityLog.objects.filter(operation="customer.deactivated", object_id=str(self.customer.pk)).count(), 1)
        product = Product.objects.create(sku="DEACT", name="Deact", current_price=1, created_by=self.manager, updated_by=self.manager)
        deactivate_product(actor=self.manager, product=product)
        with self.assertRaises(BusinessRuleError):
            deactivate_product(actor=self.manager, product=product)
        self.assertEqual(ActivityLog.objects.filter(operation="product.deactivated", object_id=str(product.pk)).count(), 1)

    def test_hidden_lead_id_and_missing_id_both_fail_validation(self):
        other_customer = create_customer_with_phone(actor=self.other, full_name="Hidden")
        other_lead = create_lead(actor=self.other, customer=other_customer)
        assign_lead(actor=self.manager, lead=other_lead, to_user=self.other)
        client = APIClient()
        client.force_authenticate(self.agent)
        payload = {"phone": "09121234567", "occurred_at": timezone.now().isoformat()}
        hidden = client.post("/api/v1/interactions/", {**payload, "lead": other_lead.pk}, format="json")
        missing = client.post("/api/v1/interactions/", {**payload, "lead": 999999}, format="json")
        self.assertEqual(hidden.status_code, 400)
        self.assertEqual(hidden.data, missing.data)

    def test_interactions_are_append_only(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        created = client.post("/api/v1/interactions/", {
            "lead": self.lead.pk,
            "phone": "09121234567",
            "occurred_at": timezone.now().isoformat(),
        }, format="json")
        self.assertEqual(created.status_code, 201)
        interaction = Interaction.objects.get(pk=created.data["id"])
        self.assertEqual(interaction.customer, self.customer)
        self.assertEqual(interaction.agent, self.agent)
        self.assertEqual(client.patch(f"/api/v1/interactions/{created.data['id']}/", {"notes": "rewrite"}, format="json").status_code, 405)

    def test_manager_cancellation_is_audited_and_cannot_repeat(self):
        sale = mark_sale(actor=self.agent, lead=self.lead, total_amount=10, sold_at=timezone.now())
        cancelled = cancel_sale(actor=self.manager, sale=sale, reason="business correction")
        self.assertEqual(cancelled.status, Sale.Status.CANCELLED)
        log = ActivityLog.objects.get(operation="sale.cancelled", object_id=str(sale.pk))
        self.assertEqual(log.safe_changes, {"reason_provided": True})
        self.assertNotIn("business correction", str(log.safe_changes))
        with self.assertRaises(BusinessRuleError):
            cancel_sale(actor=self.manager, sale=sale)
        with self.assertRaises(BusinessRuleError):
            cancel_or_correct_sale(actor=self.manager, sale=sale, operation="correct", correction={"total_amount": 5})

    def test_history_blocks_customer_hard_delete(self):
        with self.assertRaises(ProtectedError):
            self.customer.delete()

    def test_agent_cannot_manage_product_reassign_or_cancel(self):
        product = Product.objects.create(sku="SKU-2", name="Product", current_price=1, created_by=self.manager, updated_by=self.manager)
        sale = mark_sale(actor=self.agent, lead=self.lead, product=product, sold_at=timezone.now())
        client = APIClient()
        client.force_authenticate(self.agent)
        product_response = client.post("/api/v1/products/", {"sku": "NO", "name": "No", "current_price": "1.00"}, format="json")
        reassign_response = client.post(f"/api/v1/leads/{self.lead.pk}/reassign/", {"to_user": self.other.pk}, format="json")
        cancel_response = client.post(f"/api/v1/sales/{sale.pk}/cancel/", {}, format="json")
        self.assertEqual(product_response.status_code, 403)
        self.assertEqual(reassign_response.status_code, 403)
        self.assertEqual(cancel_response.status_code, 403)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)

    def test_product_changes_are_locked_and_audited(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        created = client.post("/api/v1/products/", {"sku": "AUDIT", "name": "First", "current_price": "10.00"}, format="json")
        self.assertEqual(created.status_code, 201)
        stale = Product.objects.get(pk=created.data["id"])
        updated = client.patch(f"/api/v1/products/{stale.pk}/", {"name": "Second"}, format="json")
        self.assertEqual(updated.status_code, 200)
        deactivate_product(actor=self.manager, product=stale)
        update_product(actor=self.manager, product=stale, description="kept")
        stale.refresh_from_db()
        self.assertFalse(stale.is_active)
        operations = set(ActivityLog.objects.filter(object_id=str(stale.pk), object_type="sales.product").values_list("operation", flat=True))
        self.assertEqual(operations, {"product.created", "product.updated", "product.deactivated"})

    def test_customer_server_fields_are_rejected(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.post("/api/v1/customers/", {"full_name": "Bad", "created_by": self.other.pk}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("created_by", response.data)

    def test_workflow_ownership_fields_are_rejected(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        lead_response = client.post("/api/v1/leads/", {
            "customer": self.customer.pk,
            "assigned_to": self.other.pk,
        }, format="json")
        self.assertEqual(lead_response.status_code, 400)
        self.assertIn("assigned_to", lead_response.data)
        interaction_response = client.post("/api/v1/interactions/", {
            "lead": self.lead.pk,
            "phone": "09121234567",
            "occurred_at": timezone.now().isoformat(),
            "agent": self.other.pk,
        }, format="json")
        self.assertEqual(interaction_response.status_code, 400)
        self.assertIn("agent", interaction_response.data)
        sale_response = client.post("/api/v1/sales/", {
            "lead": self.lead.pk,
            "total_amount": "10.00",
            "sold_by": self.other.pk,
        }, format="json")
        self.assertEqual(sale_response.status_code, 400)
        self.assertIn("sold_by", sale_response.data)

    def test_historical_objects_have_no_delete_route(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        self.assertEqual(client.delete(f"/api/v1/customers/{self.customer.pk}/").status_code, 405)
        self.assertEqual(client.delete(f"/api/v1/leads/{self.lead.pk}/").status_code, 405)

    def test_agent_cannot_retrieve_other_agents_objects_by_id(self):
        other_customer = create_customer_with_phone(actor=self.other, full_name="Private")
        other_lead = create_lead(actor=self.other, customer=other_customer)
        assign_lead(actor=self.manager, lead=other_lead, to_user=self.other)
        client = APIClient()
        client.force_authenticate(self.agent)
        self.assertEqual(client.get(f"/api/v1/customers/{other_customer.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/v1/leads/{other_lead.pk}/").status_code, 404)

    def test_interaction_lead_cannot_be_changed(self):
        other_customer = create_customer_with_phone(actor=self.other, full_name="Private")
        other_lead = create_lead(actor=self.other, customer=other_customer)
        assign_lead(actor=self.manager, lead=other_lead, to_user=self.other)
        client = APIClient()
        client.force_authenticate(self.agent)
        created = client.post("/api/v1/interactions/", {
            "lead": self.lead.pk,
            "phone": "09121234567",
            "occurred_at": timezone.now().isoformat(),
        }, format="json")
        self.assertEqual(created.status_code, 201)
        response = client.patch(f"/api/v1/interactions/{created.data['id']}/", {"lead": other_lead.pk}, format="json")
        self.assertEqual(response.status_code, 405)
