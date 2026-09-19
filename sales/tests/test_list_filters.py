"""The two list filters reworked on 2026-09-19.

* **Customers** («صفحه مشتریان باید فیلتر های بیشتری داشته باشه») gained four:
  استان, شهر, دسته‌بندی and وضعیت. Every one is a real column on
  `sales.Customer`; none of them groups by anything the model does not store.
* **Leads** («فیلتر وضعیت معلوم نیست چیکار میکنه و کاراییش باید بهتر باشه») had
  a free-text box labelled «کد دقیق وضعیت». A person had to guess the model's
  own internal value, and a typo — `pendign` — answered an empty page that
  looked exactly like a filter that had worked and found nothing.

Two properties matter enough to pin, and they are the ones a filter gets wrong:

1. **It must narrow, never widen.** `customers_for` / `leads_for` decide what a
   role may read at all, and a filter parameter must not be able to reach past
   that. Tested from a marketer's own session, not only an admin's.
2. **A value the backend cannot honour must be an error, not an empty page.**
   That is the whole lead-status fix, and the same rule the existing `kind` and
   date-window parameters already follow.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from sales.models import Customer, Lead


PASSWORD = "Strong-pass-411!"


class CustomerFilterTests(TestCase):
    def setUp(self):
        # Throttle buckets are keyed by user id and rolled-back tests reuse
        # those ids, so without this a test inherits the previous one's spend.
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="cf.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="cf.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )
        make = lambda **kwargs: Customer.objects.create(created_by=self.manager, **kwargs)
        self.tehran = make(full_name="مشتری تهرانی", province="تهران", city="تهران", category="طلایی")
        self.isfahan = make(full_name="مشتری اصفهانی", province="اصفهان", city="کاشان", category="نقره‌ای")
        self.retired = make(full_name="مشتری غیرفعال", province="تهران", city="ری", category="طلایی", is_active=False)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def _names(self, query):
        response = self.client.get(f"/api/v1/customers/?{query}")
        self.assertEqual(response.status_code, 200, response.data)
        return {row["full_name"] for row in response.data["results"]}

    def test_province_matches_exactly(self):
        """Exact, because the form offers a fixed list built from the same
        `iran-provinces.json` the map reads — so "filter by استان" and "the map
        placed this customer in استان" can never disagree."""
        self.assertEqual(
            self._names("kind=individual&province=تهران"),
            {"مشتری تهرانی", "مشتری غیرفعال"},
        )

    def test_city_matches_a_fragment(self):
        """Free text on the model, so part of a name is what a person means."""
        self.assertEqual(self._names("kind=individual&city=کاش"), {"مشتری اصفهانی"})

    def test_category_matches_a_fragment(self):
        self.assertEqual(
            self._names("kind=individual&category=طلا"),
            {"مشتری تهرانی", "مشتری غیرفعال"},
        )

    def test_the_status_filter_reaches_deactivated_customers(self):
        """The only way to list them at all: nothing else on this page narrows
        by `is_active`."""
        self.assertEqual(self._names("kind=individual&is_active=false"), {"مشتری غیرفعال"})
        self.assertEqual(
            self._names("kind=individual&is_active=true"),
            {"مشتری تهرانی", "مشتری اصفهانی"},
        )

    def test_filters_combine(self):
        self.assertEqual(
            self._names("kind=individual&province=تهران&is_active=true"),
            {"مشتری تهرانی"},
        )

    def test_an_empty_filter_narrows_nothing(self):
        """«همه» is the absence of a value, not a value meaning everything."""
        self.assertEqual(
            self._names("kind=individual&province=&city=&category=&is_active="),
            {"مشتری تهرانی", "مشتری اصفهانی", "مشتری غیرفعال"},
        )

    def test_an_unknown_status_is_a_request_error_not_an_empty_page(self):
        response = self.client.get("/api/v1/customers/?kind=individual&is_active=maybe")
        self.assertEqual(response.status_code, 400)
        self.assertIn("is_active", response.data)

    def test_a_filter_cannot_reach_past_the_callers_own_scope(self):
        """A marketer sees only customers they entered themselves. Asking for
        a province full of someone else's customers must answer nothing, not
        somebody else's book."""
        client = APIClient()
        client.force_authenticate(self.agent)
        response = client.get("/api/v1/customers/?kind=individual&province=تهران")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["results"], [])

    def test_each_new_filter_is_a_declared_parameter(self):
        """`StrictQueryParametersMixin` rejects anything undeclared, so a
        filter the form sends but the viewset never listed would 400 on every
        page load."""
        from sales.views import CustomerViewSet

        for name in ("province", "city", "category", "is_active"):
            with self.subTest(parameter=name):
                self.assertIn(name, CustomerViewSet.list_query_parameters)


class LeadStatusFilterTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.manager = User.objects.create_user(
            username="lf.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        for status in (Lead.Status.PENDING, Lead.Status.COMPLETED, Lead.Status.CANCELLED):
            Lead.objects.create(created_by=self.manager, status=status, source=f"src-{status}")
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def test_each_real_status_narrows_to_its_own_leads(self):
        for status in Lead.Status.values:
            with self.subTest(status=status):
                response = self.client.get(f"/api/v1/leads/?status={status}")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["count"], 1)
                self.assertEqual(response.data["results"][0]["status"], status)

    def test_a_value_outside_the_three_is_refused_with_a_reason(self):
        """The defect this fixes: `pendign` used to answer an empty page that
        looked like a working filter finding nothing."""
        response = self.client.get("/api/v1/leads/?status=pendign")
        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.data)

    def test_an_empty_status_means_every_status(self):
        """The filter form's own first option, «همهٔ وضعیت‌ها»."""
        response = self.client.get("/api/v1/leads/?status=")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 3)

    def test_the_board_still_loads_each_column(self):
        """The Kanban board asks for one status per column through this same
        parameter; the validation above must not have broken it."""
        for status in Lead.Status.values:
            with self.subTest(status=status):
                response = self.client.get(
                    f"/api/v1/leads/?status={status}&ordering=-created_at&page=1"
                )
                self.assertEqual(response.status_code, 200, response.data)
