"""Customer and lead writes must leave an audit trail.

Products, warehouses, sales, documents, money and user administration were all
recorded; customers, their phone numbers and leads were not. A staff member
could change the number a customer is reached on, or reassign what a lead wants,
and nothing recorded that it had happened or who did it.

The payload stays field names and row ids — never the customer's own data —
which is what lets an audit row be read at a lower privilege than the record it
describes.
"""

from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from auditlog.models import ActivityLog
from sales.services import (
    create_customer_phone,
    create_customer_with_phone,
    create_lead,
    update_customer,
    update_customer_phone,
    update_lead,
)


PASSWORD = "Strong-pass-937!"


class CustomerAuditTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="audit.trail", password=PASSWORD, role=User.Role.SALES_MANAGER
        )

    def _operations(self):
        return list(ActivityLog.objects.values_list("operation", flat=True))

    def test_creating_a_customer_is_recorded(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری ثبت",
            phone={"raw_phone": "09121230001", "is_primary": True},
        )
        self.assertIn("customer.created", self._operations())
        entry = ActivityLog.objects.get(operation="customer.created")
        self.assertEqual(entry.actor, self.manager)
        self.assertEqual(entry.object_id, str(customer.pk))

    def test_creating_a_phone_is_recorded(self):
        create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری تلفن",
            phone={"raw_phone": "09121230002", "is_primary": True},
        )
        self.assertIn("customer_phone.created", self._operations())

    def test_changing_a_customer_is_recorded_with_the_fields_touched(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری ویرایش",
            phone={"raw_phone": "09121230003", "is_primary": True},
        )
        update_customer(actor=self.manager, customer=customer, city="تهران", address="نشانی تازه")
        entry = ActivityLog.objects.filter(operation="customer.updated").latest("id")
        self.assertEqual(entry.safe_changes["fields"], ["address", "city"])
        # The values themselves are customer data and stay out of the payload.
        self.assertNotIn("تهران", str(entry.safe_changes))

    def test_changing_a_phone_number_is_recorded(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری شماره",
            phone={"raw_phone": "09121230004", "is_primary": True},
        )
        phone = customer.phones.get()
        update_customer_phone(actor=self.manager, phone=phone, raw_phone="09121230005")
        entry = ActivityLog.objects.filter(operation="customer_phone.updated").latest("id")
        self.assertIn("raw_phone", entry.safe_changes["fields"])
        self.assertNotIn("09121230005", str(entry.safe_changes))
        self.assertNotIn("+989121230005", str(entry.safe_changes))

    def test_creating_and_changing_a_lead_are_both_recorded(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری سرنخ",
            phone={"raw_phone": "09121230006", "is_primary": True},
        )
        lead = create_lead(actor=self.manager, customer=customer, source="manual")
        self.assertIn("lead.created", self._operations())

        update_lead(actor=self.manager, lead=lead, notes="یادداشت تازه")
        entry = ActivityLog.objects.filter(operation="lead.updated").latest("id")
        self.assertEqual(entry.safe_changes["fields"], ["notes"])
        self.assertEqual(entry.safe_changes["customer"], customer.pk)

    def test_an_unchanged_update_records_nothing(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری بدون تغییر",
            phone={"raw_phone": "09121230007", "is_primary": True},
        )
        before = ActivityLog.objects.count()
        update_customer(actor=self.manager, customer=customer, full_name="مشتری بدون تغییر")
        self.assertEqual(ActivityLog.objects.count(), before)

    def test_a_second_phone_is_recorded_against_its_customer(self):
        customer = create_customer_with_phone(
            actor=self.manager,
            full_name="مشتری دوم",
            phone={"raw_phone": "09121230008", "is_primary": True},
        )
        create_customer_phone(actor=self.manager, customer=customer, raw_phone="09121230009")
        entry = ActivityLog.objects.filter(operation="customer_phone.created").latest("id")
        self.assertEqual(entry.safe_changes["customer"], customer.pk)
