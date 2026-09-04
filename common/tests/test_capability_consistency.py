"""An export answers what its list endpoint answers — 403, not an empty file.

`sales.permissions.HasSalesCapability` (1.7.13) established the rule: a
caller holding no capability for a module gets `403`, not `200` with an
empty page, because the selectors already return nothing for them and "here
is an empty list" reads as "there is nothing" rather than "this is not
yours". `after_sales` and `billing` followed.

Three readers were still outside it, found by sweeping every route as every
role with real seeded data (the 1.8.5 debug pass): the outbound-SMS log and
the customer and product XLSX exports. Each returned `200` and an empty
payload to a role its own list endpoint refuses — never a leak, since the
rows were already scoped away, but a different answer to the same question
depending on which URL was asked.

These tests hold the pairing itself rather than a list of status codes, so
a future reader added beside a list endpoint has to agree with it.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from sales.services import create_customer_with_phone, create_product

PASSWORD = "Strong-pass-512!"

#: reader endpoint -> the list endpoint whose answer it must match.
PAIRS = {
    "/api/v1/exports/customers.xlsx": "/api/v1/customers/",
    "/api/v1/exports/products.xlsx": "/api/v1/products/",
}


class ExportMatchesItsListEndpointTests(TestCase):
    def setUp(self):
        self.platform = User.objects.create_user(
            username="cap.platform", password=PASSWORD, role=User.Role.PLATFORM_ADMIN
        )
        self.manager = User.objects.create_user(
            username="cap.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.company_it = User.objects.create_user(
            username="cap.it", password=PASSWORD, role=User.Role.COMPANY_IT
        )
        self.agent = User.objects.create_user(
            username="cap.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        self.after_sales = User.objects.create_user(
            username="cap.aftersales", password=PASSWORD, role=User.Role.SALES_AGENT,
            workstream=User.Workstream.AFTER_SALES,
        )
        create_customer_with_phone(
            actor=self.manager, full_name="مشتری سازگاری",
            phone={"raw_phone": "09151110001", "is_primary": True},
        )
        create_product(
            actor=self.manager, sku="CAP-1", name="کالای سازگاری",
            current_price=Decimal("100000.00"),
        )

    def client_for(self, actor):
        client = APIClient()
        client.force_authenticate(actor)
        return client

    def test_each_export_answers_exactly_what_its_list_endpoint_answers(self):
        roles = [self.platform, self.manager, self.company_it, self.agent, self.after_sales]
        for actor in roles:
            client = self.client_for(actor)
            for export, listing in PAIRS.items():
                with self.subTest(role=actor.role, workstream=actor.workstream, export=export):
                    self.assertEqual(
                        client.get(export).status_code,
                        client.get(listing).status_code,
                        f"{export} disagrees with {listing} for {actor.username}",
                    )

    def test_a_role_without_the_capability_is_refused_rather_than_given_an_empty_file(self):
        client = self.client_for(self.after_sales)
        for export in PAIRS:
            with self.subTest(export=export):
                self.assertEqual(client.get(export).status_code, 403)

    def test_the_fix_did_not_narrow_anyone_who_holds_the_capability(self):
        """The marketer still exports their own book — scoped, not refused."""
        for actor in (self.platform, self.manager, self.company_it, self.agent):
            client = self.client_for(actor)
            for export in PAIRS:
                with self.subTest(role=actor.role, export=export):
                    self.assertEqual(client.get(export).status_code, 200)


class OutboundSmsLogMatchesItsPageTests(TestCase):
    """The log and the `/sms/` page that reads it must agree."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="sms.cap.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="sms.cap.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def test_a_role_the_page_refuses_is_refused_by_the_log_too(self):
        self.client.force_login(self.agent)
        page = self.client.get("/sms/")
        api = APIClient()
        api.force_authenticate(self.agent)
        self.assertEqual(page.status_code, 403)
        self.assertEqual(api.get("/api/v1/outbound-sms/").status_code, 403)

    def test_a_role_the_page_allows_still_reads_the_log(self):
        self.client.force_login(self.manager)
        api = APIClient()
        api.force_authenticate(self.manager)
        self.assertEqual(self.client.get("/sms/").status_code, 200)
        self.assertEqual(api.get("/api/v1/outbound-sms/").status_code, 200)
