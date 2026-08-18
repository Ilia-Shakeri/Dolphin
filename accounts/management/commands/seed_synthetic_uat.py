import os
import re
import tempfile
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from accounts.models import User
from aftersales.models import AfterSalesRequest
from aftersales.services import create_after_sales_request
from auditlog.models import ActivityLog
from auditlog.services import log_activity
from sales.models import Customer, Interaction, Lead, Product, ProductCategory, Sale
from sales.services import (
    create_customer_with_phone,
    create_lead,
    create_product,
    create_product_category,
    mark_sale,
    reassign_lead,
    record_interaction,
)


POSTGRES_UAT_NAME = re.compile(r"\Auat_forooshbin_[a-z0-9]+(?:_[a-z0-9]+)*\Z")
SQLITE_MEMORY_TEST_NAME = re.compile(
    r"\Afile:memorydb_[A-Za-z0-9_]+\?mode=memory&cache=shared\Z"
)
SEED_LOCK_KEY = 5422700358370087253
GUARDED_MODELS = (
    User,
    Customer,
    ProductCategory,
    Product,
    Lead,
    Interaction,
    Sale,
    AfterSalesRequest,
    ActivityLog,
)
USER_FIXTURES = (
    ("uat_sales_agent", "بازاریاب", "ساختگی", User.Role.SALES_AGENT, User.Workstream.SALES),
    (
        "uat_after_sales_operator",
        "اپراتور خدمات پس از فروش",
        "ساختگی",
        User.Role.SALES_AGENT,
        User.Workstream.AFTER_SALES,
    ),
    ("uat_sales_manager", "مدیر فروشگاه", "ساختگی", User.Role.SALES_MANAGER, User.Workstream.SALES),
    ("uat_company_it", "مدیر فنی مشتری", "ساختگی", User.Role.COMPANY_IT, User.Workstream.SALES),
    ("uat_platform_admin", "مدیر پلتفرم", "ساختگی", User.Role.PLATFORM_ADMIN, User.Workstream.SALES),
)


def database_identity_is_allowed(vendor, name, *, django_test_settings=False):
    name = str(name)
    if vendor == "sqlite":
        is_memory = name == ":memory:" or bool(
            SQLITE_MEMORY_TEST_NAME.fullmatch(name)
        )
        test_file = Path(tempfile.gettempdir()) / f"test_forooshbin_{os.getpid()}.sqlite3"
        is_process_test_file = Path(name).resolve() == test_file.resolve()
        return django_test_settings and (is_memory or is_process_test_file)
    if vendor == "postgresql":
        return len(name) <= 63 and bool(POSTGRES_UAT_NAME.fullmatch(name))
    return False


class Command(BaseCommand):
    help = "Seed fixed synthetic data into an empty, isolated UAT database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm-synthetic-data",
            action="store_true",
            help="Confirm that the target is an empty isolated UAT database.",
        )

    def handle(self, *args, **options):
        if os.environ.get("KARIZ_ALLOW_UAT_SEED") != "1":
            raise CommandError("UAT seed environment gate is closed.")
        if not options["confirm_synthetic_data"]:
            raise CommandError("Synthetic-data confirmation flag is required.")
        if not self._database_is_allowed():
            raise CommandError("Database is not an allowed isolated UAT target.")
        self._assert_guarded_tables_empty()

        password = os.environ.get("KARIZ_UAT_PASSWORD")
        if not password:
            raise CommandError("KARIZ_UAT_PASSWORD is required.")
        users = self._build_and_validate_users(password)

        with transaction.atomic():
            self._lock_seed()
            self._assert_guarded_tables_empty()
            created_users = {}
            for user in users:
                user.set_password(password)
                user.save(force_insert=True)
                created_users[user.username] = user
                log_activity(
                    actor=None,
                    operation="user.uat_seeded",
                    instance=user,
                    changes={
                        "fields": ["username", "role", "is_active"],
                        "password_set": True,
                    },
                    request_id="",
                    ip_address=None,
                )
            password = None

            agent = created_users["uat_sales_agent"]
            after_sales_operator = created_users["uat_after_sales_operator"]
            manager = created_users["uat_sales_manager"]
            category = create_product_category(
                actor=manager,
                code="uat-synthetic",
                name="دسته ساختگی آزمون پذیرش",
                description="فقط داده ساختگی آزمون پذیرش",
                display_order=1,
            )
            product = create_product(
                actor=manager,
                sku="UAT-SYNTHETIC-001",
                name="محصول ساختگی آزمون پذیرش",
                category=category,
                brand="برند ساختگی",
                barcode="UAT-SYNTHETIC-001",
                current_price=Decimal("125000.00"),
                description="فقط داده ساختگی آزمون پذیرش",
            )
            customer = create_customer_with_phone(
                actor=agent,
                full_name="مشتری ساختگی آزمون پذیرش",
                email="uat-customer@example.invalid",
                province="استان ساختگی",
                city="شهر ساختگی",
                address="نشانی ساختگی؛ فاقد کاربرد واقعی",
                notes="فقط داده ساختگی آزمون پذیرش",
                phone={
                    "raw_phone": "09000000000",
                    "label": "شماره ساختگی",
                    "is_primary": True,
                },
            )
            lead = create_lead(
                actor=agent,
                customer=customer,
                interested_product=product,
                source="داده ساختگی آزمون پذیرش",
                campaign_or_batch="UAT-SYNTHETIC-001",
                notes="فقط داده ساختگی آزمون پذیرش",
            )
            lead = reassign_lead(
                actor=manager,
                lead=lead,
                to_user=agent,
                reason="تخصیص ساختگی آزمون پذیرش",
            )
            event_time = timezone.now()
            record_interaction(
                actor=agent,
                lead=lead,
                phone="09000000000",
                direction=Interaction.Direction.OUTBOUND,
                outcome="answered",
                occurred_at=event_time,
                notes="تعامل ساختگی آزمون پذیرش",
            )
            sale = mark_sale(
                actor=agent,
                lead=lead,
                product=product,
                quantity=2,
                sold_at=event_time,
                notes="فروش ساختگی آزمون پذیرش",
            )
            create_after_sales_request(
                actor=manager,
                customer=customer,
                sale=sale,
                assigned_to=after_sales_operator,
                subject="پرونده ساختگی خدمات پس از فروش",
                description="فقط داده ساختگی آزمون پذیرش",
                status="جدید",
            )

        self.stdout.write(self.style.SUCCESS("Synthetic UAT data created."))

    @staticmethod
    def _database_is_allowed():
        return database_identity_is_allowed(
            connection.vendor,
            connection.settings_dict.get("NAME", ""),
            django_test_settings=settings.SETTINGS_MODULE == "config.test_settings",
        )

    @staticmethod
    def _assert_guarded_tables_empty():
        if any(model.objects.exists() for model in GUARDED_MODELS):
            raise CommandError("UAT seed requires empty guarded tables.")

    @staticmethod
    def _build_and_validate_users(password):
        users = []
        try:
            for username, first_name, last_name, role, workstream in USER_FIXTURES:
                user = User(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                    workstream=workstream,
                    is_active=True,
                    is_staff=False,
                    is_superuser=False,
                )
                user.full_clean(
                    exclude=("password",),
                    validate_unique=False,
                    validate_constraints=False,
                )
                validate_password(password, user=user)
                users.append(user)
        except ValidationError as exc:
            raise CommandError(
                "UAT password or fixed fixture failed configured validation."
            ) from exc
        return users

    @staticmethod
    def _lock_seed():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    [SEED_LOCK_KEY],
                )
        else:
            for model in GUARDED_MODELS:
                list(model.objects.select_for_update().values_list("pk", flat=True))
