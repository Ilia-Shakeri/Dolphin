from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


CUSTOMER_ADDRESS_MAX_LENGTH = 2000
CUSTOMER_CATEGORY_MAX_LENGTH = 100
CUSTOMER_POSTAL_CODE_MAX_LENGTH = 32
FREE_TEXT_MAX_LENGTH = 4000
INTERACTION_OUTCOME_MAX_LENGTH = 80
SALES_DOCUMENT_NUMBER_MAX_LENGTH = 64
POSTAL_STATUS_MAX_LENGTH = 80
PRODUCT_CATEGORY_DESCRIPTION_MAX_LENGTH = 2000
PRODUCT_CATEGORY_NAME_MAX_LENGTH = 120
PRODUCT_BRAND_MAX_LENGTH = 120
PRODUCT_BARCODE_MAX_LENGTH = 64


class Customer(TimeStampedModel):
    full_name = models.CharField(max_length=255, db_index=True)
    national_id = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    province = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=CUSTOMER_POSTAL_CODE_MAX_LENGTH, blank=True)
    category = models.CharField(max_length=CUSTOMER_CATEGORY_MAX_LENGTH, blank=True)
    address = models.CharField(max_length=CUSTOMER_ADDRESS_MAX_LENGTH, blank=True)
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_customers")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["created_by", "is_active", "-created_at"])]


class CustomerPhone(TimeStampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="phones")
    raw_phone = models.CharField(max_length=40)
    normalized_phone = models.CharField(max_length=20, db_index=True, editable=False)
    label = models.CharField(max_length=40, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-is_primary", "id"]
        constraints = [
            models.UniqueConstraint(fields=["normalized_phone"], condition=Q(is_active=True), name="uniq_active_normalized_phone"),
            models.UniqueConstraint(fields=["customer"], condition=Q(is_active=True, is_primary=True), name="uniq_active_primary_phone"),
            models.CheckConstraint(
                condition=Q(normalized_phone__regex=r"\A\+98[1-9][0-9]{9}\Z"),
                name="customer_phone_normalized_shape",
            ),
        ]


class ProductCategory(TimeStampedModel):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=PRODUCT_CATEGORY_NAME_MAX_LENGTH)
    normalized_name = models.CharField(max_length=PRODUCT_CATEGORY_NAME_MAX_LENGTH, unique=True, editable=False)
    description = models.CharField(max_length=PRODUCT_CATEGORY_DESCRIPTION_MAX_LENGTH, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_product_categories")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_product_categories")

    class Meta:
        ordering = ["display_order", "name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(code__regex=r"\A[a-z0-9][a-z0-9_-]{0,63}\Z"),
                name="product_category_code_shape",
            ),
            models.CheckConstraint(
                condition=Q(name__regex=r"\S"),
                name="product_category_name_nonblank",
            ),
            models.CheckConstraint(
                condition=Q(normalized_name__regex=r"\S"),
                name="product_category_normalized_name_nonblank",
            ),
        ]


class Product(TimeStampedModel):
    sku = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255, db_index=True)
    category = models.ForeignKey(
        ProductCategory,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="products",
    )
    brand = models.CharField(max_length=PRODUCT_BRAND_MAX_LENGTH, blank=True)
    barcode = models.CharField(max_length=PRODUCT_BARCODE_MAX_LENGTH, blank=True, default="")
    current_price = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_products")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_products")

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(current_price__gt=0), name="product_price_positive"),
            models.CheckConstraint(
                condition=Q(barcode="") | Q(barcode__regex=r"\A[A-Z0-9][A-Z0-9._-]{0,63}\Z"),
                name="product_barcode_shape",
            ),
            models.UniqueConstraint(
                fields=["barcode"],
                condition=~Q(barcode=""),
                name="uniq_product_nonblank_barcode",
            ),
        ]
        indexes = [models.Index(fields=["category", "is_active", "name"])]


class Lead(TimeStampedModel):
    class Status(models.TextChoices):
        """The three states Client-1 tracks a campaign in.

        Previously free text, which meant every caller invented its own
        vocabulary and the list could not be filtered reliably. Existing rows
        keep whatever they held — the constraint below admits the legacy blank
        so no historical row has to be rewritten — but everything new is one of
        these three.
        """

        PENDING = "pending", "در انتظار تکمیل"
        COMPLETED = "completed", "تکمیل"
        CANCELLED = "cancelled", "کنسل شده"

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="leads")
    source = models.CharField(max_length=100, blank=True)
    campaign_or_batch = models.CharField(max_length=100, blank=True)
    interested_product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT, related_name="interested_leads")
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.PENDING, blank=True, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_leads")
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="lead_assignments_made")
    assigned_at = models.DateTimeField(null=True, blank=True)
    next_follow_up_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_leads")
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)
    source_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(assigned_to__isnull=True, assigned_by__isnull=True, assigned_at__isnull=True)
                    | Q(assigned_to__isnull=False, assigned_by__isnull=False, assigned_at__isnull=False)
                ),
                name="lead_assignment_fields_consistent",
            )
        ]
        indexes = [
            models.Index(fields=["assigned_to", "status", "next_follow_up_at"]),
            models.Index(fields=["customer", "-created_at"]),
        ]


class TargetAudienceMember(TimeStampedModel):
    """One identity in a campaign's target audience ("جامعه هدف").

    A campaign is worked from a list of people who are not customers yet. That
    list has to survive between sessions, be scoped like everything else, and
    carry its own progression — so it is a table, not a JSON blob on the lead.

    `status` is partly derived: it moves to ENGAGED once the call centre records
    an interaction with this identity, and to CUSTOMER once the identity exists
    in the customer book. CUSTOMER wins over ENGAGED, because being a customer
    is the further state. `services.refresh_target_member_status` is the single
    place that applies both rules.
    """

    class Status(models.TextChoices):
        LEAD = "lead", "سرنخ"
        ENGAGED = "engaged", "در تعامل"
        CUSTOMER = "customer", "مشتری"
        FAILED = "failed", "ناموفق"

    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="target_audience")
    full_name = models.CharField(max_length=255, db_index=True)
    raw_phone = models.CharField(max_length=40)
    normalized_phone = models.CharField(max_length=20, db_index=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.LEAD, db_index=True)
    #: Set when this identity is matched to a real customer record. It is what
    #: makes the CUSTOMER status auditable rather than a guess.
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="target_audience_entries"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_target_members")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_target_members")
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["full_name", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(full_name__regex=r"\S"), name="target_member_name_nonblank"),
            models.CheckConstraint(
                condition=Q(normalized_phone__regex=r"\A\+98[1-9][0-9]{9}\Z"),
                name="target_member_phone_shape",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["lead", "engaged", "customer", "failed"]),
                name="target_member_status_valid",
            ),
            # One person appears once per campaign. Across campaigns the same
            # number may legitimately appear again.
            models.UniqueConstraint(fields=["lead", "normalized_phone"], name="uniq_target_member_per_lead"),
        ]
        indexes = [
            models.Index(fields=["lead", "status", "full_name"]),
            models.Index(fields=["normalized_phone", "status"]),
        ]


class LeadAssignmentHistory(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="assignment_history")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assignments_lost")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments_received")
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignment_changes")
    reason = models.CharField(max_length=500, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]
        indexes = [
            models.Index(fields=["lead", "-changed_at"]),
            models.Index(fields=["to_user", "-changed_at"]),
        ]


class Interaction(TimeStampedModel):
    class Direction(models.TextChoices):
        INBOUND = "inbound", "Inbound"
        OUTBOUND = "outbound", "Outbound"

    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="interactions")
    # A call is logged against whoever was actually called. Early in a campaign
    # that is a target-audience identity with no customer record yet, so
    # `customer` is nullable and the constraint below requires at least one of
    # the two. Every historical row has a customer, so nothing is rewritten.
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="interactions"
    )
    target_member = models.ForeignKey(
        TargetAudienceMember, null=True, blank=True, on_delete=models.PROTECT, related_name="interactions"
    )
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="interactions")
    phone = models.CharField(max_length=40)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    outcome = models.CharField(max_length=INTERACTION_OUTCOME_MAX_LENGTH, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)
    next_follow_up_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(direction__in=["inbound", "outbound"]),
                name="interaction_direction_valid",
            ),
            models.CheckConstraint(
                condition=Q(outcome__regex=r"\S"),
                name="interaction_outcome_nonblank",
            ),
            models.CheckConstraint(
                condition=Q(customer__isnull=False) | Q(target_member__isnull=False),
                name="interaction_names_someone",
            ),
        ]
        indexes = [models.Index(fields=["agent", "-occurred_at"]), models.Index(fields=["lead", "-occurred_at"])]


class Sale(TimeStampedModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"

    lead = models.ForeignKey(Lead, on_delete=models.PROTECT, related_name="sales")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT, related_name="sales")
    quantity = models.PositiveIntegerField(default=1)
    unit_price_snapshot = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    sold_at = models.DateTimeField(db_index=True)
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["-sold_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_quantity_positive"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="sale_total_non_negative"),
            models.CheckConstraint(
                condition=Q(unit_price_snapshot__isnull=True) | Q(unit_price_snapshot__gte=0),
                name="sale_unit_price_non_negative",
            ),
            models.CheckConstraint(condition=Q(status__in=["confirmed", "cancelled"]), name="sale_status_valid"),
            models.CheckConstraint(
                condition=(
                    Q(product__isnull=True, unit_price_snapshot__isnull=True)
                    | Q(product__isnull=False, unit_price_snapshot__isnull=False)
                ),
                name="sale_product_snapshot_pair",
            ),
            models.CheckConstraint(
                condition=Q(product__isnull=True) | Q(total_amount=models.F("unit_price_snapshot") * models.F("quantity")),
                name="sale_product_total_matches_snapshot",
            ),
        ]
        indexes = [
            models.Index(fields=["sold_by", "status", "-sold_at"]),
            models.Index(fields=["product", "-sold_at"]),
        ]


class SalesDocument(TimeStampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales_documents")
    sale = models.ForeignKey(Sale, null=True, blank=True, on_delete=models.PROTECT, related_name="sales_documents")
    document_number = models.CharField(max_length=SALES_DOCUMENT_NUMBER_MAX_LENGTH, unique=True)
    province_snapshot = models.CharField(max_length=100, blank=True)
    city_snapshot = models.CharField(max_length=100, blank=True)
    postal_code_snapshot = models.CharField(max_length=CUSTOMER_POSTAL_CODE_MAX_LENGTH, blank=True)
    address_snapshot = models.CharField(max_length=CUSTOMER_ADDRESS_MAX_LENGTH, blank=True)
    postal_status = models.CharField(max_length=POSTAL_STATUS_MAX_LENGTH, db_index=True)
    registered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    registered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="registered_sales_documents")
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)

    class Meta:
        ordering = ["-registered_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(document_number__regex=r"\S"), name="sales_document_number_nonblank"),
            models.CheckConstraint(condition=Q(postal_status__regex=r"\S"), name="sales_document_postal_status_nonblank"),
        ]
        indexes = [
            models.Index(fields=["customer", "-registered_at"]),
            models.Index(fields=["province_snapshot", "city_snapshot", "-registered_at"]),
        ]


class PostalStatusHistory(models.Model):
    document = models.ForeignKey(SalesDocument, on_delete=models.PROTECT, related_name="postal_history")
    from_status = models.CharField(max_length=POSTAL_STATUS_MAX_LENGTH, blank=True)
    to_status = models.CharField(max_length=POSTAL_STATUS_MAX_LENGTH)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="postal_status_changes")
    reason = models.CharField(max_length=500, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(to_status__regex=r"\S"), name="postal_history_to_status_nonblank"),
        ]
        indexes = [models.Index(fields=["document", "-changed_at"])]
