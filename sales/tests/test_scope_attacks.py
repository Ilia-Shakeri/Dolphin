from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from sales.models import Interaction
from sales.services import (
    assign_lead,
    create_customer_with_phone,
    create_lead,
    mark_sale,
    record_interaction,
)


class SalesAgentCollectionScopeAttackTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="scope-manager",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_MANAGER,
        )
        self.agent = User.objects.create_user(
            username="scope-agent",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_AGENT,
        )
        self.other = User.objects.create_user(
            username="scope-other",
            password="Long-Safe-Pass-741!",
            role=User.Role.SALES_AGENT,
        )
        self.own_customer, self.own_lead, self.own_interaction, self.own_sale = self._graph(
            actor=self.agent,
            name="Owned Visible",
            phone="09121111111",
            status="owned-status",
        )
        self.hidden_customer, self.hidden_lead, self.hidden_interaction, self.hidden_sale = self._graph(
            actor=self.other,
            name="PrivateLeakMarker",
            phone="09122222222",
            status="hidden-status",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.agent)

    def _graph(self, *, actor, name, phone, status):
        customer = create_customer_with_phone(
            actor=actor,
            full_name=name,
            phone={"raw_phone": phone, "is_primary": True},
        )
        lead = create_lead(actor=actor, customer=customer, source=name, notes=name)
        assign_lead(actor=self.manager, lead=lead, to_user=actor, reason="scope proof")
        type(lead).objects.filter(pk=lead.pk).update(status=status)
        lead.refresh_from_db()
        interaction = record_interaction(
            actor=actor,
            lead=lead,
            phone=phone,
            direction=Interaction.Direction.OUTBOUND,
            outcome=name,
            occurred_at=timezone.now(),
            notes=name,
        )
        sale = mark_sale(
            actor=actor,
            lead=lead,
            total_amount=10,
            sold_at=timezone.now(),
            notes=name,
        )
        return customer, lead, interaction, sale

    def _result_ids(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        return {row["id"] for row in response.data["results"]}

    def test_search_and_order_never_reveal_other_agent_rows(self):
        attacks = (
            ("/api/v1/customers/?search=PrivateLeakMarker&ordering=-created_at", self.hidden_customer.pk),
            ("/api/v1/customer-phones/?search=09122222222&ordering=-created_at", self.hidden_customer.phones.get().pk),
            ("/api/v1/leads/?search=PrivateLeakMarker&ordering=-created_at", self.hidden_lead.pk),
            ("/api/v1/interactions/?search=PrivateLeakMarker&ordering=-occurred_at", self.hidden_interaction.pk),
            ("/api/v1/sales/?search=PrivateLeakMarker&ordering=-sold_at", self.hidden_sale.pk),
        )
        for url, hidden_id in attacks:
            with self.subTest(url=url):
                self.assertNotIn(hidden_id, self._result_ids(url))

    def test_status_filters_run_after_lead_and_sale_scope(self):
        self.assertEqual(
            self._result_ids("/api/v1/leads/?status=hidden-status&ordering=-created_at"),
            set(),
        )
        self.assertEqual(
            self._result_ids("/api/v1/leads/?status=owned-status&ordering=-created_at"),
            {self.own_lead.pk},
        )
        confirmed_ids = self._result_ids(
            "/api/v1/sales/?status=confirmed&ordering=-sold_at",
        )
        self.assertEqual(confirmed_ids, {self.own_sale.pk})
        self.assertNotIn(self.hidden_sale.pk, confirmed_ids)
