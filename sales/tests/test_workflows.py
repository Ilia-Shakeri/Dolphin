from decimal import Decimal
from importlib import import_module
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from sales.models import CUSTOMER_ADDRESS_MAX_LENGTH, CUSTOMER_CATEGORY_MAX_LENGTH, CUSTOMER_POSTAL_CODE_MAX_LENGTH, FREE_TEXT_MAX_LENGTH, Customer, CustomerPhone, Interaction, Lead, LeadAssignmentHistory, Product, Sale
from sales.selectors import customers_for, leads_for
from sales.services import assign_lead, cancel_or_correct_sale, cancel_sale, create_customer_phone, create_customer_with_phone, create_lead, deactivate_product, mark_sale, reassign_lead, record_interaction, update_customer, update_customer_phone, update_lead, update_product
from sales.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales.views import CustomerViewSet, LeadViewSet, ProductViewSet, SaleViewSet
from common.throttles import SensitiveRateThrottle


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

    def _create_other_private_sales_objects(self):
        customer = create_customer_with_phone(
            actor=self.other,
            full_name="Private Customer",
            phone={"raw_phone": "09123334444", "is_primary": True},
        )
        lead = create_lead(actor=self.other, customer=customer, source="private")
        assign_lead(actor=self.manager, lead=lead, to_user=self.other, reason="private")
        interaction = Interaction.objects.create(
            lead=lead,
            customer=customer,
            agent=self.other,
            phone="09123334444",
            direction=Interaction.Direction.OUTBOUND,
            outcome="answered",
            occurred_at=timezone.now(),
        )
        sale = mark_sale(actor=self.other, lead=lead, total_amount=10, sold_at=timezone.now())
        return customer, lead, interaction, sale

    def test_free_text_limits_reject_api_and_service_writes(self):
        expected_fields = (
            (Customer, "address", CUSTOMER_ADDRESS_MAX_LENGTH),
            (Customer, "notes", FREE_TEXT_MAX_LENGTH),
            (Product, "description", FREE_TEXT_MAX_LENGTH),
            (Lead, "notes", FREE_TEXT_MAX_LENGTH),
            (Interaction, "notes", FREE_TEXT_MAX_LENGTH),
            (Sale, "notes", FREE_TEXT_MAX_LENGTH),
        )
        for model, field_name, limit in expected_fields:
            with self.subTest(model=model.__name__, field=field_name):
                self.assertEqual(model._meta.get_field(field_name).max_length, limit)

        client = APIClient()
        client.force_authenticate(self.agent)
        before_customers = Customer.objects.count()
        customer_response = client.post(
            "/api/v1/customers/",
            {"full_name": "Too Long", "address": "x" * (CUSTOMER_ADDRESS_MAX_LENGTH + 1)},
            format="json",
        )
        self.assertEqual(customer_response.status_code, 400)
        self.assertIn("address", customer_response.data)
        self.assertEqual(Customer.objects.count(), before_customers)

        before_interactions = Interaction.objects.count()
        interaction_response = client.post(
            "/api/v1/interactions/",
            {
                "lead": self.lead.pk,
                "phone": "09121234567",
                "direction": Interaction.Direction.OUTBOUND,
                "outcome": "answered",
                "occurred_at": timezone.now().isoformat(),
                "notes": "x" * (FREE_TEXT_MAX_LENGTH + 1),
            },
            format="json",
        )
        self.assertEqual(interaction_response.status_code, 400)
        self.assertIn("notes", interaction_response.data)
        with self.assertRaises(BusinessRuleError):
            record_interaction(
                actor=self.agent,
                lead=self.lead,
                phone="09121234567",
                direction=Interaction.Direction.OUTBOUND,
                outcome="answered",
                occurred_at=timezone.now(),
                notes="x" * (FREE_TEXT_MAX_LENGTH + 1),
            )
        self.assertEqual(Interaction.objects.count(), before_interactions)

    def test_text_limit_migration_preflight_lists_ids_not_values(self):
        marker = "private-oversized-text-marker"
        oversized = Customer.objects.create(
            full_name="Legacy Oversized",
            created_by=self.agent,
            notes=marker + "x" * FREE_TEXT_MAX_LENGTH,
        )
        migration = import_module("sales.migrations.0009_bounded_free_text")

        with self.assertRaises(RuntimeError) as caught:
            migration.reject_oversized_text(django_apps, None)

        self.assertIn(str(oversized.pk), str(caught.exception))
        self.assertNotIn(marker, str(caught.exception))

    def test_interaction_contract_rejects_bad_api_and_service_input(self):
        self.assertFalse(Interaction._meta.get_field("direction").blank)
        self.assertFalse(Interaction._meta.get_field("outcome").blank)
        self.assertEqual(
            {value for value, _ in Interaction.Direction.choices},
            {"inbound", "outbound"},
        )
        client = APIClient()
        client.force_authenticate(self.agent)
        base_payload = {
            "lead": self.lead.pk,
            "phone": "09121234567",
            "occurred_at": timezone.now().isoformat(),
        }
        invalid_payloads = (
            {**base_payload, "outcome": "answered"},
            {**base_payload, "direction": "sideways", "outcome": "answered"},
            {**base_payload, "direction": Interaction.Direction.OUTBOUND},
            {**base_payload, "direction": Interaction.Direction.OUTBOUND, "outcome": "   "},
        )
        before = Interaction.objects.count()
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = client.post("/api/v1/interactions/", payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertEqual(Interaction.objects.count(), before)

        invalid_service_data = (
            {"outcome": "answered"},
            {"direction": "sideways", "outcome": "answered"},
            {"direction": Interaction.Direction.OUTBOUND},
            {"direction": Interaction.Direction.OUTBOUND, "outcome": "   "},
            {"direction": Interaction.Direction.OUTBOUND, "outcome": "x" * 81},
        )
        for fields in invalid_service_data:
            with self.subTest(fields=fields), self.assertRaises(BusinessRuleError):
                record_interaction(
                    actor=self.agent,
                    lead=self.lead,
                    phone="09121234567",
                    occurred_at=timezone.now(),
                    **fields,
                )
        self.assertEqual(Interaction.objects.count(), before)

    def test_interaction_contract_has_database_and_migration_guards(self):
        invalid_rows = (
            ("sideways", "answered"),
            (Interaction.Direction.OUTBOUND, ""),
            (Interaction.Direction.OUTBOUND, "   "),
        )
        for direction, outcome in invalid_rows:
            with self.subTest(direction=direction, outcome=outcome), self.assertRaises(IntegrityError), transaction.atomic():
                Interaction.objects.create(
                    lead=self.lead,
                    customer=self.customer,
                    agent=self.agent,
                    phone="09121234567",
                    direction=direction,
                    outcome=outcome,
                    occurred_at=timezone.now(),
                )

        marker = "private-interaction-outcome"
        fake_rows = mock.Mock()
        fake_rows.values_list.return_value = fake_rows
        fake_rows.iterator.return_value = iter([(77, "sideways", marker)])
        fake_model = mock.Mock()
        fake_model.objects = fake_rows
        fake_apps = mock.Mock()
        fake_apps.get_model.return_value = fake_model
        migration = import_module("sales.migrations.0010_interaction_contract")
        with self.assertRaises(RuntimeError) as caught:
            migration.reject_invalid_interactions(fake_apps, None)
        self.assertIn("77", str(caught.exception))
        self.assertNotIn(marker, str(caught.exception))

    def test_customer_can_have_multiple_leads(self):
        create_lead(actor=self.agent, customer=self.customer, source="repeat")
        self.assertEqual(self.customer.leads.count(), 2)

    def test_customer_profile_fields_and_primary_phone_are_backward_compatible(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.post(
            "/api/v1/customers/",
            {
                "full_name": "Profile Customer",
                "postal_code": "Postal text 123",
                "category": "Priority customer",
                "address": "Profile address",
                "phone": {
                    "raw_phone": "09125556666",
                    "label": "mobile",
                    "is_primary": True,
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["postal_code"], "Postal text 123")
        self.assertEqual(response.data["category"], "Priority customer")
        self.assertEqual(
            response.data["primary_phone"],
            {
                "id": response.data["primary_phone"]["id"],
                "raw_phone": "09125556666",
                "normalized_phone": "+989125556666",
                "label": "mobile",
            },
        )

        legacy = client.post(
            "/api/v1/customers/",
            {"full_name": "Legacy Payload Customer"},
            format="json",
        )
        self.assertEqual(legacy.status_code, 201)
        self.assertEqual(legacy.data["postal_code"], "")
        self.assertEqual(legacy.data["category"], "")
        self.assertIsNone(legacy.data["primary_phone"])

        updated = client.patch(
            f"/api/v1/customers/{response.data['id']}/",
            {"postal_code": "Updated postal", "category": "Updated category"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["postal_code"], "Updated postal")
        self.assertEqual(updated.data["category"], "Updated category")
        server_owned = client.patch(
            f"/api/v1/customers/{response.data['id']}/",
            {"primary_phone": None},
            format="json",
        )
        self.assertEqual(server_owned.status_code, 400)
        self.assertIn("primary_phone", server_owned.data)
        searched = client.get("/api/v1/customers/?search=Updated+category")
        self.assertEqual(searched.status_code, 200)
        self.assertEqual([row["id"] for row in searched.data["results"]], [response.data["id"]])

        self.assertEqual(Customer._meta.get_field("postal_code").max_length, CUSTOMER_POSTAL_CODE_MAX_LENGTH)
        self.assertEqual(Customer._meta.get_field("category").max_length, CUSTOMER_CATEGORY_MAX_LENGTH)
        with self.assertRaises(BusinessRuleError):
            update_customer(
                actor=self.agent,
                customer=Customer.objects.get(pk=response.data["id"]),
                category="x" * (CUSTOMER_CATEGORY_MAX_LENGTH + 1),
            )

    def test_customer_related_views_are_paginated_and_keep_existing_scope(self):
        own_interaction = record_interaction(
            actor=self.agent,
            lead=self.lead,
            phone="09121234567",
            direction=Interaction.Direction.OUTBOUND,
            outcome="answered",
            occurred_at=timezone.now(),
        )
        own_sale = mark_sale(
            actor=self.agent,
            lead=self.lead,
            total_amount=Decimal("125.00"),
            sold_at=timezone.now(),
        )
        hidden_customer, hidden_lead, hidden_interaction, hidden_sale = self._create_other_private_sales_objects()
        client = APIClient()
        client.force_authenticate(self.agent)

        expected = {
            "leads": (self.lead.pk, hidden_lead.pk),
            "interactions": (own_interaction.pk, hidden_interaction.pk),
            "sales": (own_sale.pk, hidden_sale.pk),
        }
        for action_name, (visible_id, hidden_id) in expected.items():
            with self.subTest(action=action_name):
                response = client.get(
                    f"/api/v1/customers/{self.customer.pk}/{action_name}/?page=1"
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["count"], 1)
                self.assertEqual([row["id"] for row in response.data["results"]], [visible_id])
                self.assertNotIn(hidden_id, [row["id"] for row in response.data["results"]])
                hidden = client.get(
                    f"/api/v1/customers/{hidden_customer.pk}/{action_name}/?page=1"
                )
                self.assertEqual(hidden.status_code, 404)

        unknown_query = client.get(
            f"/api/v1/customers/{self.customer.pk}/leads/?search=blocked"
        )
        self.assertEqual(unknown_query.status_code, 400)
        self.assertIn("search", unknown_query.data)

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
        other_customer = create_customer_with_phone(actor=self.agent, full_name="Other Customer")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomerPhone.objects.create(
                customer=other_customer,
                raw_phone="09121234567",
                normalized_phone="+989121234567",
            )
        self.assertEqual(CustomerPhone.objects.filter(customer=self.customer, is_active=True).count(), 1)

    def test_phone_identity_rejects_non_ascii_digit_bypass(self):
        wide_duplicate = "\uff19\uff11\uff12\uff11\uff12\uff13\uff14\uff15\uff16\uff17"
        before = CustomerPhone.objects.count()
        with self.assertRaises(DjangoValidationError):
            create_customer_phone(
                actor=self.agent,
                customer=self.customer,
                raw_phone=wide_duplicate,
            )
        self.assertEqual(CustomerPhone.objects.count(), before)

        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.post(
            "/api/v1/customer-phones/",
            {"customer": self.customer.pk, "raw_phone": wide_duplicate},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.assertEqual(CustomerPhone.objects.count(), before)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CustomerPhone.objects.create(
                customer=self.customer,
                raw_phone=wide_duplicate,
                normalized_phone=f"+98{wide_duplicate}",
                is_active=False,
            )

    def test_phone_partial_uniqueness_boundaries(self):
        with self.assertRaises(BusinessRuleError):
            create_customer_with_phone(
                actor=self.agent,
                full_name="Blocked Duplicate",
                phone={"raw_phone": "09121234567", "is_primary": True},
            )
        self.assertFalse(Customer.objects.filter(full_name="Blocked Duplicate").exists())
        other_customer = create_customer_with_phone(actor=self.agent, full_name="Other Customer")
        inactive = create_customer_phone(
            actor=self.agent,
            customer=other_customer,
            raw_phone="09121234567",
            is_active=False,
        )
        self.assertFalse(inactive.is_active)
        with self.assertRaises(BusinessRuleError):
            update_customer_phone(actor=self.agent, phone=inactive, is_active=True)

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

    def test_phone_customer_cannot_be_changed(self):
        other_customer = create_customer_with_phone(actor=self.agent, full_name="Other Customer")
        phone = self.customer.phones.get()
        client = APIClient()
        client.force_authenticate(self.agent)

        response = client.patch(
            f"/api/v1/customer-phones/{phone.pk}/",
            {"customer": other_customer.pk},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("customer", response.data)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        phone.refresh_from_db()
        self.assertEqual(phone.customer, self.customer)

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

    def test_reassignment_rejects_server_group_identity_without_mutation(self):
        self.other.groups.add(Group.objects.create(name="server-ops"))
        with self.assertRaises(BusinessRuleError):
            reassign_lead(actor=self.manager, lead=self.lead, to_user=self.other)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to, self.agent)
        self.assertEqual(LeadAssignmentHistory.objects.filter(lead=self.lead).count(), 1)

        client = APIClient()
        client.force_authenticate(self.manager)
        response = client.post(
            f"/api/v1/leads/{self.lead.pk}/reassign/",
            {"to_user": self.other.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "validation_error")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_to, self.agent)

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

    def test_database_rejects_non_positive_product_price(self):
        for sku, price in (("NEGATIVE", Decimal("-1.00")), ("ZERO", Decimal("0.00"))):
            with self.subTest(price=price), self.assertRaises(IntegrityError), transaction.atomic():
                Product.objects.create(
                    sku=sku,
                    name="Bad Product",
                    current_price=price,
                    created_by=self.manager,
                    updated_by=self.manager,
                )

    def test_api_conflicts_use_409_and_stable_code(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        duplicate_phone = client.post(
            "/api/v1/customer-phones/",
            {"customer": self.customer.pk, "raw_phone": "+98 912 123 4567"},
            format="json",
            HTTP_X_REQUEST_ID="phone-conflict-1",
        )
        self.assertEqual(duplicate_phone.status_code, 409)
        self.assertEqual(
            duplicate_phone.data["error"],
            {"code": "conflict", "request_id": "phone-conflict-1"},
        )

        sale = mark_sale(actor=self.agent, lead=self.lead, total_amount=10, sold_at=timezone.now())
        client.force_authenticate(self.manager)
        self.assertEqual(client.post(f"/api/v1/sales/{sale.pk}/cancel/", {}, format="json").status_code, 200)
        repeated = client.post(
            f"/api/v1/sales/{sale.pk}/cancel/",
            {},
            format="json",
            HTTP_X_REQUEST_ID="sale-conflict-1",
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(
            repeated.data["error"],
            {"code": "conflict", "request_id": "sale-conflict-1"},
        )

    @mock.patch.object(SensitiveRateThrottle, "get_rate", lambda self: "1/min")
    def test_sensitive_workflow_actions_are_throttled(self):
        cache.clear()
        self.assertEqual(LeadViewSet.sensitive_actions, frozenset({"reassign"}))
        self.assertEqual(SaleViewSet.sensitive_actions, frozenset({"create", "cancel"}))
        self.assertEqual(CustomerViewSet.sensitive_actions, frozenset({"deactivate"}))
        self.assertEqual(
            ProductViewSet.sensitive_actions,
            frozenset({"create", "update", "partial_update", "deactivate"}),
        )

        manager_client = APIClient()
        manager_client.force_authenticate(self.manager)
        first_reassign = manager_client.post(
            f"/api/v1/leads/{self.lead.pk}/reassign/",
            {"to_user": self.other.pk},
            format="json",
        )
        second_reassign = manager_client.post(
            f"/api/v1/leads/{self.lead.pk}/reassign/",
            {"to_user": self.agent.pk},
            format="json",
        )
        self.assertEqual(first_reassign.status_code, 200)
        self.assertEqual(second_reassign.status_code, 429)

        seller_client = APIClient()
        seller_client.force_authenticate(self.other)
        first_sale = seller_client.post(
            "/api/v1/sales/",
            {"lead": self.lead.pk, "total_amount": "10.00"},
            format="json",
        )
        second_sale = seller_client.post(
            "/api/v1/sales/",
            {"lead": self.lead.pk, "total_amount": "11.00"},
            format="json",
        )
        self.assertEqual(first_sale.status_code, 201)
        self.assertEqual(second_sale.status_code, 429)

        company_it = User.objects.create_user(
            username="throttle-it",
            password="strong-pass-1",
            role=User.Role.COMPANY_IT,
        )
        cancel_client = APIClient()
        cancel_client.force_authenticate(company_it)
        first_cancel = cancel_client.post(
            f"/api/v1/sales/{first_sale.data['id']}/cancel/",
            {},
            format="json",
        )
        second_cancel = cancel_client.post(
            f"/api/v1/sales/{first_sale.data['id']}/cancel/",
            {},
            format="json",
        )
        self.assertEqual(first_cancel.status_code, 200)
        self.assertEqual(second_cancel.status_code, 429)
        self.assertEqual(second_cancel.data["error"]["code"], "throttled")

        cache.clear()
        first_product = manager_client.post(
            "/api/v1/products/",
            {"sku": "THROTTLE-ONE", "name": "Throttle One", "current_price": "1.00"},
            format="json",
        )
        second_product = manager_client.post(
            "/api/v1/products/",
            {"sku": "THROTTLE-TWO", "name": "Throttle Two", "current_price": "1.00"},
            format="json",
        )
        self.assertEqual(first_product.status_code, 201)
        self.assertEqual(second_product.status_code, 429)

        cache.clear()
        customer = create_customer_with_phone(actor=self.manager, full_name="Throttle Customer")
        first_deactivate = manager_client.post(f"/api/v1/customers/{customer.pk}/deactivate/")
        second_deactivate = manager_client.post(f"/api/v1/customers/{customer.pk}/deactivate/")
        self.assertEqual(first_deactivate.status_code, 200)
        self.assertEqual(second_deactivate.status_code, 429)
        cache.clear()

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

    def test_company_it_and_platform_admin_have_key_write_parity(self):
        for index, role in enumerate((User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN), start=1):
            with self.subTest(role=role):
                actor = User.objects.create_user(
                    username=f"elevated-{index}",
                    password="strong-pass-1",
                    role=role,
                )
                target = User.objects.create_user(
                    username=f"target-{index}",
                    password="strong-pass-1",
                    role=User.Role.SALES_AGENT,
                )
                client = APIClient()
                client.force_authenticate(actor)

                customer_response = client.post(
                    "/api/v1/customers/",
                    {"full_name": f"Elevated Customer {index}"},
                    format="json",
                )
                self.assertEqual(customer_response.status_code, 201)
                customer_id = customer_response.data["id"]
                self.assertEqual(
                    client.patch(
                        f"/api/v1/customers/{customer_id}/",
                        {"notes": "updated"},
                        format="json",
                    ).status_code,
                    200,
                )

                phone_response = client.post(
                    "/api/v1/customer-phones/",
                    {
                        "customer": customer_id,
                        "raw_phone": f"0912300000{index}",
                        "is_primary": True,
                    },
                    format="json",
                )
                self.assertEqual(phone_response.status_code, 201)
                self.assertEqual(
                    client.patch(
                        f"/api/v1/customer-phones/{phone_response.data['id']}/",
                        {"label": "main"},
                        format="json",
                    ).status_code,
                    200,
                )

                product_response = client.post(
                    "/api/v1/products/",
                    {
                        "sku": f"ELEVATED-{index}",
                        "name": f"Elevated Product {index}",
                        "current_price": "10.00",
                    },
                    format="json",
                )
                self.assertEqual(product_response.status_code, 201)
                product_id = product_response.data["id"]
                self.assertEqual(
                    client.patch(
                        f"/api/v1/products/{product_id}/",
                        {"description": "updated"},
                        format="json",
                    ).status_code,
                    200,
                )

                lead_response = client.post(
                    "/api/v1/leads/",
                    {
                        "customer": customer_id,
                        "interested_product": product_id,
                        "source": "manual",
                    },
                    format="json",
                )
                self.assertEqual(lead_response.status_code, 201)
                lead_id = lead_response.data["id"]
                self.assertEqual(
                    client.post(
                        f"/api/v1/leads/{lead_id}/reassign/",
                        {"to_user": target.pk},
                        format="json",
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.patch(
                        f"/api/v1/leads/{lead_id}/",
                        {"notes": "updated"},
                        format="json",
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(
                        "/api/v1/interactions/",
                        {
                            "lead": lead_id,
                            "phone": f"0912300000{index}",
                            "direction": Interaction.Direction.OUTBOUND,
                            "outcome": "answered",
                            "occurred_at": timezone.now().isoformat(),
                        },
                        format="json",
                    ).status_code,
                    201,
                )

                sale_response = client.post(
                    "/api/v1/sales/",
                    {
                        "lead": lead_id,
                        "product": product_id,
                        "quantity": 1,
                        "sold_at": timezone.now().isoformat(),
                    },
                    format="json",
                )
                self.assertEqual(sale_response.status_code, 201)
                self.assertEqual(
                    client.post(
                        f"/api/v1/sales/{sale_response.data['id']}/cancel/",
                        {},
                        format="json",
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.post(f"/api/v1/products/{product_id}/deactivate/").status_code,
                    200,
                )
                self.assertEqual(
                    client.post(f"/api/v1/customers/{customer_id}/deactivate/").status_code,
                    200,
                )

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
        self.assertEqual(second.status_code, 409)
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
        payload = {
            "phone": "09121234567",
            "direction": Interaction.Direction.OUTBOUND,
            "outcome": "answered",
            "occurred_at": timezone.now().isoformat(),
        }
        hidden = client.post("/api/v1/interactions/", {**payload, "lead": other_lead.pk}, format="json")
        missing = client.post("/api/v1/interactions/", {**payload, "lead": 999999}, format="json")
        self.assertEqual(hidden.status_code, 400)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(hidden.data["lead"], missing.data["lead"])
        self.assertEqual(hidden.data["error"]["code"], "validation_error")
        self.assertEqual(missing.data["error"]["code"], "validation_error")
        self.assertEqual(hidden.data["error"]["request_id"], hidden["X-Request-ID"])
        self.assertEqual(missing.data["error"]["request_id"], missing["X-Request-ID"])
        self.assertNotEqual(hidden["X-Request-ID"], missing["X-Request-ID"])

    def test_hidden_sale_lead_and_missing_lead_have_same_safe_error(self):
        _, other_lead, _, _ = self._create_other_private_sales_objects()
        client = APIClient()
        client.force_authenticate(self.agent)
        payload = {"total_amount": "10.00", "sold_at": timezone.now().isoformat()}

        hidden = client.post(
            "/api/v1/sales/",
            {**payload, "lead": other_lead.pk},
            format="json",
        )
        missing = client.post(
            "/api/v1/sales/",
            {**payload, "lead": 999999},
            format="json",
        )

        self.assertEqual(hidden.status_code, 400)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(hidden.data["lead"], missing.data["lead"])
        self.assertEqual(hidden.data["error"]["code"], "validation_error")
        self.assertEqual(missing.data["error"]["code"], "validation_error")

    def test_interactions_are_append_only(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        created = client.post("/api/v1/interactions/", {
            "lead": self.lead.pk,
            "phone": "09121234567",
            "direction": Interaction.Direction.OUTBOUND,
            "outcome": "answered",
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
        product_update_response = client.patch(
            f"/api/v1/products/{product.pk}/",
            {"name": "Blocked"},
            format="json",
        )
        product_deactivate_response = client.post(f"/api/v1/products/{product.pk}/deactivate/")
        reassign_response = client.post(f"/api/v1/leads/{self.lead.pk}/reassign/", {"to_user": self.other.pk}, format="json")
        cancel_response = client.post(f"/api/v1/sales/{sale.pk}/cancel/", {}, format="json")
        deactivate_customer_response = client.post(f"/api/v1/customers/{self.customer.pk}/deactivate/", {}, format="json")
        self.assertEqual(product_response.status_code, 403)
        self.assertEqual(product_update_response.status_code, 403)
        self.assertEqual(product_deactivate_response.status_code, 403)
        self.assertEqual(reassign_response.status_code, 403)
        self.assertEqual(cancel_response.status_code, 403)
        self.assertEqual(deactivate_customer_response.status_code, 403)
        product.refresh_from_db()
        self.assertEqual(product.name, "Product")
        self.assertTrue(product.is_active)
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
            "direction": Interaction.Direction.OUTBOUND,
            "outcome": "answered",
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
        other_customer, other_lead, interaction, sale = self._create_other_private_sales_objects()
        phone = other_customer.phones.get()
        client = APIClient()
        client.force_authenticate(self.agent)
        hidden_paths = [
            f"/api/v1/customers/{other_customer.pk}/",
            f"/api/v1/customer-phones/{phone.pk}/",
            f"/api/v1/leads/{other_lead.pk}/",
            f"/api/v1/interactions/{interaction.pk}/",
            f"/api/v1/sales/{sale.pk}/",
        ]
        for path in hidden_paths:
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 404)

    def test_interaction_lead_cannot_be_changed(self):
        other_customer = create_customer_with_phone(actor=self.other, full_name="Private")
        other_lead = create_lead(actor=self.other, customer=other_customer)
        assign_lead(actor=self.manager, lead=other_lead, to_user=self.other)
        client = APIClient()
        client.force_authenticate(self.agent)
        created = client.post("/api/v1/interactions/", {
            "lead": self.lead.pk,
            "phone": "09121234567",
            "direction": Interaction.Direction.OUTBOUND,
            "outcome": "answered",
            "occurred_at": timezone.now().isoformat(),
        }, format="json")
        self.assertEqual(created.status_code, 201)
        response = client.patch(f"/api/v1/interactions/{created.data['id']}/", {"lead": other_lead.pk}, format="json")
        self.assertEqual(response.status_code, 405)
