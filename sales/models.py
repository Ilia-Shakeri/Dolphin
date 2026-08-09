from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


CUSTOMER_ADDRESS_MAX_LENGTH = 2000
FREE_TEXT_MAX_LENGTH = 4000
INTERACTION_OUTCOME_MAX_LENGTH = 80


class Customer(TimeStampedModel):
    full_name = models.CharField(max_length=255, db_index=True)
    national_id = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    province = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
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


class Product(TimeStampedModel):
    sku = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255, db_index=True)
    current_price = models.DecimalField(max_digits=18, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    description = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_products")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_products")

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.CheckConstraint(condition=Q(current_price__gt=0), name="product_price_positive")]


class Lead(TimeStampedModel):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="leads")
    source = models.CharField(max_length=100, blank=True)
    campaign_or_batch = models.CharField(max_length=100, blank=True)
    interested_product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT, related_name="interested_leads")
    status = models.CharField(max_length=40, blank=True, db_index=True)
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
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="interactions")
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
