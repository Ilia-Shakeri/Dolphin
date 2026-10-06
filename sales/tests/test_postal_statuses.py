"""Every Iran Post status, each with its own icon (2.40.26).

The four stages stay the stepper; the post office's own statuses — the
coded ones of the web service and the ones its tracking page shows without a
code — are one table in `sales.postal`, each with an icon of its own, the
stage it sits on (or none: a return, a seizure), and a tone.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.models import User
from sales import ebazar, postal
from sales.models import PostalShipment
from sales.services import create_customer_with_phone, register_sales_document

ROOT = Path(__file__).resolve().parents[2]
ICON_CSS = (ROOT / "common" / "static" / "common" / "ui" / "css" / "dolphin-plugins.rtl.css").read_text(encoding="utf-8")


class TableTests(SimpleTestCase):
    def test_every_coded_and_uncoded_status_is_in_the_table(self):
        labels = {status.label for status in postal.CARRIER_STATUSES}
        self.assertLessEqual({label for label, _stage in ebazar.PARCEL_STATUSES.values()}, labels)
        self.assertLessEqual(set(ebazar.UNCODED_STATUSES), labels)

    def test_the_coded_statuses_keep_the_services_stage(self):
        for code, (_label, stage) in ebazar.PARCEL_STATUSES.items():
            with self.subTest(code=code):
                self.assertEqual(postal.carrier_status_for(code=code).stage, stage)

    def test_no_two_statuses_share_an_icon_and_every_icon_exists(self):
        everything = list(postal.POSTAL_STATES) + list(postal.CARRIER_STATUSES)
        icons = [status.icon for status in everything]
        self.assertEqual(len(icons), len(set(icons)))
        for status in everything:
            with self.subTest(status=status.key):
                paths = set(re.findall(rf"\.{re.escape(status.icon)} \.path(\d+):before", ICON_CSS))
                self.assertEqual(paths, {str(n) for n in range(1, status.icon_paths + 1)})

    def test_a_status_sits_on_its_stage_or_none(self):
        self.assertEqual(postal.state_for("with_postman").key, "out_for_delivery")
        self.assertIsNone(postal.state_for("returned"))
        self.assertEqual(postal.label_for("returned"), "برگشتی نهایی")
        self.assertEqual(postal.badge_for(code=9)["icon"], "di-lock")
        self.assertEqual(postal.badge_for(text="مراجعه دوم")["key"], "second_visit")


class ListTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="ps.manager", password="Strong-pass-661!", role=User.Role.SALES_MANAGER)
        customer = create_customer_with_phone(actor=self.manager, full_name="گیرنده", phone={"raw_phone": "09125550101", "is_primary": True})
        self.tracked = register_sales_document(actor=self.manager, customer=customer, document_number="PS-1", postal_status="with_post")
        PostalShipment.objects.create(
            document=self.tracked, service_type=1, pay_type=1, city_id=1, weight_grams=100, goods_price_rial=100000,
            carrier_status_code=10, carrier_status_text="پیش برگشتی", created_by=self.manager,
        )
        self.manual = register_sales_document(actor=self.manager, customer=customer, document_number="PS-2", postal_status="returned")
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_each_row_carries_its_badge(self):
        rows = {row["document_number"]: row for row in self.client.get("/api/v1/sales-documents/").json()["results"]}
        self.assertEqual(rows["PS-1"]["postal_badge"]["key"], "pre_return")
        self.assertEqual(rows["PS-2"]["postal_badge"]["key"], "returned")
        self.assertEqual(rows["PS-2"]["postal_stepper"], [])

    def test_the_filter_finds_a_status_stored_or_reported(self):
        def numbers(value):
            return {row["document_number"] for row in self.client.get(f"/api/v1/sales-documents/?postal_status={value}").json()["results"]}

        self.assertEqual(numbers("pre_return"), {"PS-1"})
        self.assertEqual(numbers("returned"), {"PS-2"})
        self.assertEqual(numbers("with_post"), {"PS-1"})
