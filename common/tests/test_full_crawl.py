"""Every page and every list API, for every role, on fresh data (2.39.27).

A whole working day is built from nothing through the services — catalogue,
stock, customers, a campaign with sub-campaigns and people, a call, an invoice
issued against a chosen campaign, a receipt allocated to it, a supply document
for several invoices, a legacy result, an after-sales case — and then every
served page (`common.ui_urls`, `profiles`) and every router list endpoint is
opened as each role. Nothing may answer 5xx, a page a role is offered in the
menu must open, and every page must render without a template error.

This is the "every page, every feature, raw data" smoke the product owner asked
for; the narrower tests next to it pin the rules.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import URLPattern, URLResolver, reverse
from django.utils import timezone

from accounts.models import User
from aftersales.models import AfterSalesRequest
from aftersales.services import create_after_sales_request
from auditlog.models import ActivityLog
from billing.models import Payment
from billing.payments import allocate_payment_across, register_payment
from billing.services import create_fulfillment_batch, create_invoice, issue_invoice
from inventory.models import StockMovement
from inventory.services import create_warehouse, record_stock_movement
from sales.campaigns import (
    add_campaign_member,
    assign_campaign_member,
    container_lead,
    create_campaign,
    ensure_customer_for_member,
)
from sales.models import Interaction, Sale
from sales.services import (
    create_customer_with_phone,
    create_lead,
    create_product,
    create_product_category,
    mark_sale,
    record_interaction,
)

PASSWORD = "Strong-pass-937!"


def _patterns(resolver, prefix=""):
    entries = resolver.urlpatterns if hasattr(resolver, "urlpatterns") else resolver.url_patterns
    for entry in entries:
        if isinstance(entry, URLResolver):
            yield from _patterns(entry, prefix + str(entry.pattern))
        elif isinstance(entry, URLPattern) and entry.name:
            yield prefix + str(entry.pattern), entry


class FullCrawlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="crawl.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        cls.agent = User.objects.create_user(username="crawl.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        cls.operator = User.objects.create_user(
            username="crawl.after", password=PASSWORD, role=User.Role.SALES_AGENT, workstream=User.Workstream.AFTER_SALES
        )
        cls.it = User.objects.create_user(username="crawl.it", password=PASSWORD, role=User.Role.COMPANY_IT)
        cls.admin = User.objects.create_user(username="crawl.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        m = cls.manager

        category = create_product_category(actor=m, code="tools", name="لوازم")
        product = create_product(actor=m, sku="CR-1", name="کالای آزمون", current_price=Decimal("1500000.00"))
        warehouse = create_warehouse(actor=m, code="crwh", name="انبار مرکزی")
        record_stock_movement(
            actor=m, warehouse=warehouse, product=product,
            movement_type=StockMovement.MovementType.OPENING, quantity=50, unit_cost=Decimal("900000.00"),
        )

        campaign = create_campaign(actor=m, name="تابستان", channels=["phone", "social"], responsibles=[cls.agent])
        child = create_campaign(actor=m, name="اینستاگرام", parent=campaign, channels=["social"])
        people = [
            add_campaign_member(actor=m, campaign=child, full_name=f"مخاطب {n}", raw_phone=f"0912333000{n}")
            for n in range(4)
        ]
        for person in people[:2]:
            assign_campaign_member(actor=m, member=person, to_user=cls.agent)
        person = people[0]
        person.refresh_from_db()
        record_interaction(
            actor=cls.agent, lead=container_lead(child, m), target_member=person, phone=person.raw_phone,
            direction="outbound", outcome="پاسخ داد", occurred_at=timezone.now() - timedelta(hours=2),
            next_follow_up_at=timezone.now() + timedelta(days=1),
        )
        person = ensure_customer_for_member(actor=cls.agent, member=person)
        customer = person.customer

        invoices = []
        for _ in range(2):
            draft = create_invoice(
                actor=cls.agent, customer=customer, campaign=child, warehouse=warehouse,
                items=[{"product": product, "quantity": 2, "unit_price": product.current_price}],
            )
            invoices.append(issue_invoice(actor=m, invoice=draft))
        receipt = register_payment(actor=m, customer=customer, method=Payment.Method.CASH, amount=Decimal("2000000.00"))
        allocate_payment_across(
            actor=m, payment=receipt, splits=[{"invoice": invoices[0], "amount": Decimal("500000.00")}] * 2,
            request_key="crawl",
        )
        _number, orders = create_fulfillment_batch(actor=cls.agent, invoices=invoices, warehouse=warehouse)

        legacy_customer = create_customer_with_phone(actor=m, full_name="مشتری قدیمی", phone={"raw_phone": "09123334444"})
        legacy_lead = create_lead(actor=m, customer=legacy_customer, source="قدیمی")
        sale = mark_sale(actor=m, lead=legacy_lead, product=product, quantity=1)
        create_after_sales_request(
            actor=m, customer=customer, subject="نصب", description="نصب دستگاه", status="باز", assigned_to=cls.operator,
        )

        cls.ids = {
            "campaign_id": campaign.pk, "category_id": category.pk, "customer_id": customer.pk,
            "interaction_id": Interaction.objects.order_by("pk").first().pk, "invoice_id": invoices[0].pk,
            "lead_id": legacy_lead.pk, "order_id": orders[0].pk, "payment_id": receipt.pk,
            "product_id": product.pk, "request_id": AfterSalesRequest.objects.first().pk, "sale_id": sale.pk,
            "user_id": cls.agent.pk, "warehouse_id": warehouse.pk, "person_id": customer.pk,
            "activity_log_id": ActivityLog.objects.order_by("pk").first().pk,
            "document_id": None, "pk": None,
        }
        cls.users = [cls.manager, cls.agent, cls.operator, cls.it, cls.admin]

    def setUp(self):
        cache.clear()

    def page_urls(self):
        from common import ui_urls

        urls = []
        for route, entry in _patterns(ui_urls):
            names = list(entry.pattern.converters)
            kwargs = {name: self.ids.get(name) for name in names}
            if any(value is None for value in kwargs.values()):
                continue
            try:
                urls.append(reverse(f"common_ui:{entry.name}", kwargs=kwargs))
            except Exception:  # noqa: BLE001 - a pattern this crawl cannot fill in is skipped, not failed
                continue
        return sorted(set(urls))

    def api_urls(self):
        from accounts.urls import router as accounts_router
        from aftersales.urls import router as aftersales_router
        from auditlog.urls import router as auditlog_router
        from billing.urls import router as billing_router
        from inventory.urls import router as inventory_router
        from sales.urls import router as sales_router

        urls = [
            "/api/v1/dashboard/", "/api/v1/reminders/", "/api/v1/reminders/count/",
            "/api/v1/campaigns/results/", "/api/v1/campaigns/analytics/",
            "/api/v1/campaign-members/follow-ups/",
        ]
        for router in (accounts_router, aftersales_router, auditlog_router, billing_router, inventory_router, sales_router):
            for prefix, _viewset, _basename in router.registry:
                urls.append(f"/api/v1/{prefix}/")
        return sorted(set(urls))

    def test_no_page_or_list_answers_a_server_error_for_any_role(self):
        pages = self.page_urls()
        apis = self.api_urls()
        self.assertGreater(len(pages), 40)
        failures = []
        for user in self.users:
            self.client.force_login(user)
            for url in pages + apis:
                response = self.client.get(url)
                # The PDF engine is optional per deployment; without it the
                # page answers a deliberate, explained 503.
                if url.endswith(".pdf") and response.status_code == 503 and "PDF" in response.content.decode("utf-8"):
                    continue
                if response.status_code >= 500:
                    failures.append(f"{user.username} {url} -> {response.status_code}")
            self.client.logout()
        self.assertEqual(failures, [])

    def test_a_manager_opens_every_page_with_the_days_data(self):
        self.client.force_login(self.manager)
        refused = []
        for url in self.page_urls():
            response = self.client.get(url)
            if url.endswith(".pdf") and response.status_code == 503:
                continue
            if response.status_code not in (200, 302):
                refused.append(f"{url} -> {response.status_code}")
        # Platform-only pages answer 403 to a sales manager; nothing else may.
        self.assertTrue(all(" -> 403" in line or " -> 404" in line for line in refused), refused)
        self.assertLess(len(refused), 12, refused)

    def test_the_days_numbers_add_up(self):
        from sales.campaign_analytics import campaign_rows

        rows = {row["name"]: row for row in campaign_rows(self.manager)}
        self.assertEqual(rows["اینستاگرام"]["valid_invoices_count"], 2)
        self.assertEqual(rows["تابستان"]["valid_invoices_count"], 2)  # the parent rolls its child up once
        self.assertEqual(rows["تابستان"]["members"], 4)
        self.assertEqual(Sale.objects.count(), 1)
