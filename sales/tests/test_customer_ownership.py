"""Customer ownership and managed categories (2.35.0).

A marketer's scope follows `Customer.owner`; a manager may hand a customer
over. Categories are a managed list whose text is mirrored onto the legacy
`category` column. The backfill is idempotent, has a dry run, and never merges
spellings that merely look alike.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.customer_backfill import loose_key, normalize_label, run_backfill
from sales.models import Customer, CustomerCategory
from sales.selectors import customers_for
from sales.services import (
    create_customer_category,
    create_customer_with_phone,
    rename_customer_category,
    set_customer_category_active,
    transfer_customer_category,
    update_customer,
)

PASSWORD = "Strong-pass-937!"


class Fixtures(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="own.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="own.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other_agent = User.objects.create_user(username="own.agent2", password=PASSWORD, role=User.Role.SALES_AGENT)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client


class OwnershipTests(Fixtures):
    def test_a_new_customer_belongs_to_whoever_created_it(self):
        customer = create_customer_with_phone(actor=self.agent, full_name="الف")
        self.assertEqual(customer.owner, self.agent)

    def test_the_model_never_leaves_a_customer_without_an_owner(self):
        customer = Customer.objects.create(full_name="ب", created_by=self.manager)
        self.assertEqual(customer.owner_id, self.manager.pk)

    def test_a_manager_may_create_a_customer_for_a_marketer(self):
        customer = create_customer_with_phone(actor=self.manager, full_name="ج", owner=self.agent)
        self.assertEqual(customer.owner, self.agent)
        self.assertIn(customer, customers_for(self.agent))

    def test_a_marketer_cannot_name_an_owner(self):
        with self.assertRaises(BusinessPermissionDenied):
            create_customer_with_phone(actor=self.agent, full_name="د", owner=self.other_agent)
        self.assertEqual(Customer.objects.count(), 0)

    def test_the_api_refuses_a_marketer_naming_an_owner(self):
        response = self.client_for(self.agent).post(
            "/api/v1/customers/", {"full_name": "ه", "owner": self.other_agent.pk}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_scope_follows_the_owner_not_the_creator(self):
        mine = create_customer_with_phone(actor=self.agent, full_name="من")
        update_customer(actor=self.manager, customer=mine, owner=self.other_agent)
        mine.refresh_from_db()
        self.assertEqual(mine.owner, self.other_agent)
        self.assertEqual(mine.created_by, self.agent)
        self.assertNotIn(mine, customers_for(self.agent))
        self.assertIn(mine, customers_for(self.other_agent))
        response = self.client_for(self.agent).get(f"/api/v1/customers/{mine.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_an_owner_must_be_an_active_sales_user(self):
        inactive = User.objects.create_user(username="own.gone", password=PASSWORD, role=User.Role.SALES_AGENT, is_active=False)
        with self.assertRaises(BusinessRuleError):
            create_customer_with_phone(actor=self.manager, full_name="و", owner=inactive)

    def test_reassigning_is_audited(self):
        from auditlog.models import ActivityLog

        mine = create_customer_with_phone(actor=self.agent, full_name="ز")
        update_customer(actor=self.manager, customer=mine, owner=self.other_agent)
        entry = ActivityLog.objects.filter(operation="customer.updated").latest("id")
        self.assertIn("owner", entry.safe_changes["fields"])


class CategoryServiceTests(Fixtures):
    def test_only_a_manager_manages_categories(self):
        with self.assertRaises(BusinessPermissionDenied):
            create_customer_category(actor=self.agent, name="عمده")
        category = create_customer_category(actor=self.manager, name="  عمده   فروش ")
        self.assertEqual(category.name, "عمده فروش")

    def test_spellings_that_differ_only_by_letters_or_digits_are_one_category(self):
        create_customer_category(actor=self.manager, name="سطح ۱")
        with self.assertRaises(BusinessConflictError):
            create_customer_category(actor=self.manager, name="سطح 1")
        with self.assertRaises(BusinessConflictError):
            create_customer_category(actor=self.manager, name="سطح ١")

    def test_choosing_a_category_mirrors_its_name_and_a_rename_follows(self):
        category = create_customer_category(actor=self.manager, name="ویژه")
        customer = create_customer_with_phone(actor=self.manager, full_name="ح", category_ref=category)
        self.assertEqual(customer.category, "ویژه")
        rename_customer_category(actor=self.manager, category=category, name="ویژه‌ها")
        customer.refresh_from_db()
        self.assertEqual(customer.category, "ویژه‌ها")

    def test_an_inactive_category_cannot_be_assigned_but_keeps_its_customers(self):
        category = create_customer_category(actor=self.manager, name="قدیمی")
        customer = create_customer_with_phone(actor=self.manager, full_name="ط", category_ref=category)
        set_customer_category_active(actor=self.manager, category=category, active=False)
        customer.refresh_from_db()
        self.assertEqual(customer.category_ref, category)
        with self.assertRaises(BusinessRuleError):
            create_customer_with_phone(actor=self.manager, full_name="ی", category_ref=category)

    def test_a_category_in_use_cannot_be_deleted_but_can_be_transferred(self):
        source = create_customer_category(actor=self.manager, name="الف")
        target = create_customer_category(actor=self.manager, name="ب")
        customer = create_customer_with_phone(actor=self.manager, full_name="ک", category_ref=source)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            source.delete()
        moved = transfer_customer_category(actor=self.manager, category=source, target=target)
        customer.refresh_from_db()
        self.assertEqual((moved, customer.category_ref, customer.category), (1, target, "ب"))
        source.refresh_from_db()
        self.assertFalse(source.is_active)

    def test_legacy_text_that_names_an_active_category_links_to_it(self):
        category = create_customer_category(actor=self.manager, name="vip")
        customer = create_customer_with_phone(actor=self.manager, full_name="ل", category="VIP")
        self.assertEqual(customer.category_ref, category)

    def test_api_permissions(self):
        create = self.client_for(self.agent).post("/api/v1/customer-categories/", {"name": "x"}, format="json")
        self.assertEqual(create.status_code, 403)
        ok = self.client_for(self.manager).post("/api/v1/customer-categories/", {"name": "مهم"}, format="json")
        self.assertEqual(ok.status_code, 201)
        listing = self.client_for(self.agent).get("/api/v1/customer-categories/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        delete = self.client_for(self.manager).delete(f"/api/v1/customer-categories/{ok.data['id']}/")
        self.assertEqual(delete.status_code, 403)  # `customer_categories.delete` is the platform admin's


class BackfillTests(Fixtures):
    def make_legacy(self, name, category):
        customer = Customer.objects.create(full_name=name, category=category, created_by=self.agent)
        Customer.objects.filter(pk=customer.pk).update(owner=None)
        return customer

    def test_normalisation_unifies_letters_digits_and_spacing_but_keeps_half_spaces(self):
        self.assertEqual(normalize_label("  كيف   ۱۲ "), normalize_label("کیف 12"))
        self.assertNotEqual(normalize_label("پخش کننده"), normalize_label("پخش‌کننده"))
        self.assertEqual(loose_key("پخش کننده"), loose_key("پخش‌کننده"))

    def test_dry_run_writes_nothing_and_apply_is_idempotent(self):
        a = self.make_legacy("1", "عمده")
        b = self.make_legacy("2", "عمده ")
        c = self.make_legacy("3", "پخش کننده")
        d = self.make_legacy("4", "پخش‌کننده")
        out = StringIO()
        call_command("backfill_customer_ownership", "--dry-run", stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("ambiguous category groups (need review): 1", out.getvalue())
        self.assertEqual(CustomerCategory.objects.count(), 0)
        self.assertEqual(Customer.objects.filter(owner__isnull=True).count(), 4)

        call_command("backfill_customer_ownership", stdout=StringIO())
        for customer in (a, b, c, d):
            customer.refresh_from_db()
            self.assertEqual(customer.owner, self.agent)
        self.assertEqual(a.category_ref, b.category_ref)
        # Near-identical spellings are kept apart for a person to decide.
        self.assertNotEqual(c.category_ref, d.category_ref)
        self.assertEqual(CustomerCategory.objects.count(), 3)
        self.assertEqual(a.category, "عمده")  # the text column is untouched

        again = run_backfill(Customer, CustomerCategory, apply=True)
        self.assertEqual((again.owners_to_fill, again.categories_to_create, again.customers_to_link), (0, 0, 0))
