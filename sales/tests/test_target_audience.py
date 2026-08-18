"""The campaign target audience ("جامعه هدف").

Its status is the interesting part: two of the four values are conclusions the
system draws from real activity rather than things a person types, and the
priority between them is fixed. These tests pin both rules and the scope that
decides who may edit the list at all.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales.models import Interaction, TargetAudienceMember
from sales.services import (
    add_target_audience_member,
    create_customer_with_phone,
    create_lead,
    record_interaction,
    update_target_audience_member,
)
from django.utils import timezone


PASSWORD = "Strong-pass-937!"


class TargetAudienceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="ta.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="ta.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری کمپین",
            phone={"raw_phone": "09120001111", "is_primary": True},
        )
        self.lead = create_lead(actor=self.manager, customer=self.customer, source="manual")

    def _add(self, name="فرد هدف", phone="09120002222", **kwargs):
        return add_target_audience_member(
            actor=self.manager, lead=self.lead, full_name=name, raw_phone=phone, **kwargs
        )

    # --- the list itself ---------------------------------------------------

    def test_an_identity_starts_as_a_lead_and_is_audited(self):
        member = self._add()
        self.assertEqual(member.status, TargetAudienceMember.Status.LEAD)
        self.assertEqual(member.normalized_phone, "+989120002222")
        self.assertTrue(
            ActivityLog.objects.filter(operation="target_audience.added", object_id=str(member.pk)).exists()
        )

    def test_the_same_number_cannot_appear_twice_in_one_campaign(self):
        self._add(phone="09120003333")
        from common.exceptions import BusinessConflictError

        with self.assertRaises(BusinessConflictError):
            self._add(name="کس دیگر", phone="09120003333")

    def test_a_blank_name_is_refused(self):
        with self.assertRaises(BusinessRuleError):
            self._add(name="   ")

    # --- derived status ----------------------------------------------------

    def test_logging_a_call_moves_the_identity_to_engaged(self):
        member = self._add(phone="09120004444")
        record_interaction(
            actor=self.manager,
            lead=self.lead,
            target_member=member,
            phone="09120004444",
            direction=Interaction.Direction.OUTBOUND,
            outcome="پاسخ داد",
            occurred_at=timezone.now(),
        )
        member.refresh_from_db()
        self.assertEqual(member.status, TargetAudienceMember.Status.ENGAGED)

    def test_becoming_a_customer_outranks_being_engaged(self):
        member = self._add(phone="09120005555")
        record_interaction(
            actor=self.manager,
            lead=self.lead,
            target_member=member,
            phone="09120005555",
            direction=Interaction.Direction.OUTBOUND,
            outcome="پاسخ داد",
            occurred_at=timezone.now(),
        )
        member.refresh_from_db()
        self.assertEqual(member.status, TargetAudienceMember.Status.ENGAGED)

        # The same number now exists in the customer book.
        created = create_customer_with_phone(
            actor=self.manager,
            full_name="فرد هدف",
            phone={"raw_phone": "09120005555", "is_primary": True},
        )
        member.refresh_from_db()
        self.assertEqual(member.status, TargetAudienceMember.Status.CUSTOMER)
        self.assertEqual(member.customer_id, created.pk)

    def test_an_identity_already_in_the_customer_book_starts_as_a_customer(self):
        member = self._add(name="مشتری کمپین", phone="09120001111")
        self.assertEqual(member.status, TargetAudienceMember.Status.CUSTOMER)
        self.assertEqual(member.customer_id, self.customer.pk)

    def test_a_hand_set_failure_survives_a_call_but_not_a_customer_record(self):
        member = self._add(phone="09120006666", status=TargetAudienceMember.Status.FAILED)
        record_interaction(
            actor=self.manager,
            lead=self.lead,
            target_member=member,
            phone="09120006666",
            direction=Interaction.Direction.OUTBOUND,
            outcome="پاسخ نداد",
            occurred_at=timezone.now(),
        )
        member.refresh_from_db()
        # A judgement about the person is not overwritten by activity alone.
        self.assertEqual(member.status, TargetAudienceMember.Status.FAILED)

        create_customer_with_phone(
            actor=self.manager,
            full_name="فرد هدف",
            phone={"raw_phone": "09120006666", "is_primary": True},
        )
        member.refresh_from_db()
        self.assertEqual(member.status, TargetAudienceMember.Status.CUSTOMER)

    def test_the_derived_statuses_cannot_be_set_by_hand(self):
        member = self._add(phone="09120007777")
        for status in (TargetAudienceMember.Status.ENGAGED, TargetAudienceMember.Status.CUSTOMER):
            with self.subTest(status=status):
                with self.assertRaises(BusinessRuleError):
                    update_target_audience_member(actor=self.manager, member=member, status=status)

    # --- scope and permission ----------------------------------------------

    def test_a_marketer_may_not_add_or_edit(self):
        member = self._add(phone="09120008888")
        with self.assertRaises(BusinessPermissionDenied):
            add_target_audience_member(
                actor=self.agent, lead=self.lead, full_name="نفوذی", raw_phone="09120009999"
            )
        with self.assertRaises(BusinessPermissionDenied):
            update_target_audience_member(actor=self.agent, member=member, full_name="تغییر")

    def test_a_marketer_reads_only_the_audience_of_assigned_campaigns(self):
        mine = self._add(phone="09120001212")
        other_customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دیگر",
            phone={"raw_phone": "09120001313", "is_primary": True},
        )
        other_lead = create_lead(actor=self.manager, customer=other_customer, source="manual")
        add_target_audience_member(
            actor=self.manager, lead=other_lead, full_name="بیرون از دامنه", raw_phone="09120001414"
        )
        self.lead.assigned_to = self.agent
        self.lead.assigned_by = self.manager
        self.lead.assigned_at = timezone.now()
        self.lead.save(update_fields=["assigned_to", "assigned_by", "assigned_at"])

        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.get("/api/v1/target-audience/")
        self.assertEqual(response.status_code, 200)
        identifiers = {row["id"] for row in response.data["results"]}
        self.assertIn(mine.pk, identifiers)
        self.assertEqual(len(identifiers), 1)

    def test_the_api_refuses_a_marketer_write(self):
        self.lead.assigned_to = self.agent
        self.lead.assigned_by = self.manager
        self.lead.assigned_at = timezone.now()
        self.lead.save(update_fields=["assigned_to", "assigned_by", "assigned_at"])
        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.post(
            "/api/v1/target-audience/",
            {"lead": self.lead.pk, "full_name": "نفوذی", "raw_phone": "09120001515"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(TargetAudienceMember.objects.filter(full_name="نفوذی").exists())

    def test_the_api_creates_and_lists_for_a_manager(self):
        client = APIClient()
        client.force_authenticate(self.manager)
        created = client.post(
            "/api/v1/target-audience/",
            {"lead": self.lead.pk, "full_name": "فرد تازه", "raw_phone": "09120001616"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.data["status"], TargetAudienceMember.Status.LEAD)
        self.assertEqual(created.data["normalized_phone"], "+989120001616")

        listing = client.get(f"/api/v1/target-audience/?lead={self.lead.pk}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
