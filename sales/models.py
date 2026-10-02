from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from common.models import TimeStampedModel


CUSTOMER_ADDRESS_MAX_LENGTH = 2000
CUSTOMER_CATEGORY_MAX_LENGTH = 100
CAMPAIGN_NAME_MAX_LENGTH = 120
CUSTOMER_POSTAL_CODE_MAX_LENGTH = 32
FREE_TEXT_MAX_LENGTH = 4000
INTERACTION_OUTCOME_MAX_LENGTH = 80
SALES_DOCUMENT_NUMBER_MAX_LENGTH = 64
POSTAL_STATUS_MAX_LENGTH = 80
PRODUCT_CATEGORY_DESCRIPTION_MAX_LENGTH = 2000
PRODUCT_CATEGORY_NAME_MAX_LENGTH = 120
PRODUCT_BRAND_MAX_LENGTH = 120
PRODUCT_BARCODE_MAX_LENGTH = 64


class CustomerCategory(TimeStampedModel):
    """A customer category chosen from a managed list (2.35.0).

    Replaces the free-text `Customer.category` as the thing people pick from;
    the text column stays, mirrored from the chosen category's name, so every
    existing filter, export and report keeps reading what it always read.
    """

    name = models.CharField(max_length=CUSTOMER_CATEGORY_MAX_LENGTH)
    normalized_name = models.CharField(max_length=CUSTOMER_CATEGORY_MAX_LENGTH, unique=True, editable=False)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_customer_categories")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_customer_categories")

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="customer_category_name_nonblank"),
            models.CheckConstraint(condition=Q(normalized_name__regex=r"\S"), name="customer_category_normalized_nonblank"),
        ]


class Customer(TimeStampedModel):
    class Kind(models.TextChoices):
        """Whether this customer is a person or an organisation.

        Client-1 keeps two customer books and works them separately, so the kind
        decides which list a customer appears in, not merely how they are
        labelled.

        The default is deliberate and is not a "not recorded yet" blank the way
        `Product.unit` is. Every customer that existed before this field is a
        natural person as far as the panel is concerned, and a blank kind would
        put them in *neither* list — they would silently vanish from the book
        the marketer works out of. A default nobody has to backfill is the only
        version of this migration that cannot lose sight of a customer.
        """

        INDIVIDUAL = "individual", "حقیقی"
        LEGAL = "legal", "حقوقی"

    full_name = models.CharField(max_length=255, db_index=True)
    kind = models.CharField(
        max_length=16, choices=Kind.choices, default=Kind.INDIVIDUAL, db_index=True
    )
    national_id = models.CharField(max_length=32, blank=True, db_index=True)
    #: Iran issues two different identifiers, and an official invoice needs the
    #: right one for the buyer it names. A natural person has a ten-digit
    #: کد ملی, which `national_id` above already holds. An organisation has an
    #: eleven-digit شناسه ملی *and* a separate شماره اقتصادی, which is this
    #: field. They are distinct numbers and one cannot be derived from the
    #: other, so they get distinct columns.
    #:
    #: Blank is the normal state: it is only required when an invoice is marked
    #: official, and it is required there by the invoice, not by this model. A
    #: customer entered for day-to-day work is not obliged to carry one.
    economic_code = models.CharField(max_length=32, blank=True, db_index=True)
    #: The person's position at their own company (2.19.0) — the customer
    #: profile's «سمت». Optional; the profile falls back to the customer kind.
    job_title = models.CharField(max_length=120, blank=True, default="")
    email = models.EmailField(blank=True)
    province = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=CUSTOMER_POSTAL_CODE_MAX_LENGTH, blank=True)
    category = models.CharField(max_length=CUSTOMER_CATEGORY_MAX_LENGTH, blank=True)
    address = models.CharField(max_length=CUSTOMER_ADDRESS_MAX_LENGTH, blank=True)
    notes = models.CharField(max_length=FREE_TEXT_MAX_LENGTH, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_customers")
    #: Who works this customer (2.35.0). Nullable only so the column can be
    #: added to a populated table; every customer is given one by the backfill
    #: and by every create path. A marketer's scope follows this, not
    #: `created_by`, so a manager can hand a customer to someone.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="owned_customers")
    #: The managed category; `category` above mirrors its name for old readers.
    category_ref = models.ForeignKey(CustomerCategory, on_delete=models.PROTECT, null=True, blank=True, related_name="customers")
    is_active = models.BooleanField(default=True, db_index=True)

    def save(self, *args, **kwargs):
        # No customer is ever left without someone who works it: a path that
        # does not name an owner gives the customer to whoever created it.
        if self.owner_id is None and self.created_by_id:
            self.owner_id = self.created_by_id
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = {*kwargs["update_fields"], "owner"}
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_by", "is_active", "-created_at"]),
            models.Index(fields=["owner", "is_active", "-created_at"], name="customer_owner_active_idx"),
            # The customers page filters by province since 2.6.0, and province
            # is matched exactly (the form offers the thirty-one canonical
            # names, so there is nothing to match loosely). An exact-match
            # filter on an unindexed column is a sequential scan of the whole
            # book on every page load once the book is large; one index makes
            # it a lookup. `city` and `category` are deliberately left alone:
            # both are matched with `icontains`, which a plain B-tree index
            # cannot serve anyway.
            models.Index(fields=["province"], name="customer_province_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["individual", "legal"]),
                name="customer_kind_valid",
            ),
        ]


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
    class Unit(models.TextChoices):
        """How a product is counted when it is sold.

        A fixed list, not free text: the unit appears on order and invoice
        lines, and two spellings of the same unit would make those documents
        disagree with each other. Existing products predate the field and carry
        a blank value, which the constraint below admits — a blank unit is "not
        recorded yet", never a silent default that would put a wrong word on a
        customer's invoice.
        """

        BOX = "box", "جعبه"
        PIECE = "piece", "عدد"
        CARTON = "carton", "کارتن"
        KILOGRAM = "kilogram", "کیلوگرم"
        GRAM = "gram", "گرم"

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
    unit = models.CharField(max_length=20, choices=Unit.choices, blank=True, default="")
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
            models.CheckConstraint(
                condition=Q(unit__in=["", "box", "piece", "carton", "kilogram", "gram"]),
                name="product_unit_valid",
            ),
        ]
        indexes = [models.Index(fields=["category", "is_active", "name"])]


class Campaign(TimeStampedModel):
    """A marketing campaign: the unit people are worked and measured by (2.36.0).

    Until now a campaign was only free text (`Lead.campaign_or_batch`), so two
    spellings were two campaigns and nothing could be measured. This is the
    real entity. Its people are `TargetAudienceMember` rows (one per person per
    campaign); its results are the valid invoices attributed to it
    (`CampaignAttribution`).

    `Lead` stays what it was — a work container other modules point at — and
    each campaign owns one hidden container so those modules keep working.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        ACTIVE = "active", "فعال"
        PAUSED = "paused", "متوقف"
        FINISHED = "finished", "تمام‌شده"
        ARCHIVED = "archived", "بایگانی"

    class Channel(models.TextChoices):
        PHONE = "phone", "تماس تلفنی"
        SMS = "sms", "پیامک"
        SOCIAL = "social", "شبکه‌های اجتماعی"
        EXHIBITION = "exhibition", "نمایشگاه"
        REFERRAL = "referral", "معرفی"
        WEBSITE = "website", "وب‌سایت"
        OTHER = "other", "سایر"

    name = models.CharField(max_length=CAMPAIGN_NAME_MAX_LENGTH)
    normalized_name = models.CharField(max_length=CAMPAIGN_NAME_MAX_LENGTH, unique=True, editable=False)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.PHONE)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    target_count = models.PositiveIntegerField(null=True, blank=True)
    budget = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    responsibles = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="responsible_campaigns")
    #: Set for the three campaigns every deployment has (`direct`, `referral`,
    #: `legacy`); they cannot be deleted or renamed away from their meaning.
    system_key = models.CharField(max_length=16, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_campaigns")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_campaigns")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(name__regex=r"\S"), name="campaign_name_nonblank"),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "active", "paused", "finished", "archived"]),
                name="campaign_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(starts_on__isnull=True) | Q(ends_on__isnull=True) | Q(ends_on__gte=models.F("starts_on")),
                name="campaign_dates_ordered",
            ),
            models.UniqueConstraint(fields=["system_key"], condition=~Q(system_key=""), name="uniq_campaign_system_key"),
        ]
        indexes = [models.Index(fields=["status", "-created_at"])]


class CampaignAttribution(TimeStampedModel):
    """Which campaign a valid invoice counts for (2.36.0).

    One row per invoice. Automatic attribution follows the last touch — the
    campaign whose person this customer was, most recently contacted, inside
    the window (`CAMPAIGN_ATTRIBUTION_WINDOW_DAYS`); a manager may correct it
    by hand. Only the link to a campaign is ever changed; the invoice itself is
    never touched, which is why this lives beside it and not on it.
    """

    class Source(models.TextChoices):
        AUTO = "auto", "خودکار"
        MANUAL = "manual", "دستی"

    invoice = models.OneToOneField("billing.Invoice", on_delete=models.PROTECT, related_name="campaign_attribution")
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT, related_name="attributions")
    member = models.ForeignKey(
        "sales.TargetAudienceMember", null=True, blank=True, on_delete=models.SET_NULL, related_name="attributions"
    )
    source = models.CharField(max_length=8, choices=Source.choices, default=Source.AUTO)
    attributed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="campaign_attributions_made"
    )
    reason = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [models.Index(fields=["campaign", "-created_at"])]


class CampaignAttributionLog(models.Model):
    """Append-only history of every attribution and correction."""

    invoice = models.ForeignKey("billing.Invoice", on_delete=models.PROTECT, related_name="campaign_attribution_log")
    from_campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    source = models.CharField(max_length=8)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


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

    # A campaign is worked from its target audience, not from one customer, so a
    # lead may name no customer at all. Existing leads keep theirs; a campaign
    # created from now on simply does not need one.
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.PROTECT, related_name="leads"
    )
    source = models.CharField(max_length=100, blank=True)
    campaign_or_batch = models.CharField(max_length=100, blank=True)
    #: The real campaign this work container belongs to (2.36.0). Filled by
    #: `migrate_campaigns` for existing leads and by the campaign services for
    #: new ones; the free-text label above is kept as it was.
    campaign = models.ForeignKey("sales.Campaign", null=True, blank=True, on_delete=models.PROTECT, related_name="leads")
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

    `status` is **entirely derived** and never typed in: every identity enters as
    LEAD, moves to ENGAGED once the call centre records an interaction with it,
    and to CUSTOMER once the same number exists in the customer book. CUSTOMER
    wins over ENGAGED, because being a customer is the further state.
    `services.refresh_target_member_status` is the single place that applies the
    rules, so the list can never claim work that did not happen.
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

    class Stage(models.TextChoices):
        """Where a person stands in a campaign (2.36.0).

        Unlike `status` (derived, and inflated by anyone who happens to be a
        customer already), `converted` is reached only through a valid invoice
        attributed to this campaign — see `sales.campaign_attribution`.
        """

        NEW = "new", "جدید"
        CONTACTED = "contacted", "تماس گرفته‌شده"
        ENGAGED = "engaged", "در تعامل"
        CONVERTED = "converted", "تبدیل‌شده"
        LOST = "lost", "ازدست‌رفته"

    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.PROTECT, related_name="members")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_campaign_members"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.NEW, db_index=True)
    lost_reason = models.CharField(max_length=300, blank=True)
    next_follow_up_at = models.DateTimeField(null=True, blank=True, db_index=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    #: The person was already a customer when they entered this campaign. A
    #: flag, not a conversion: it is what stops the audience from "converting"
    #: people the campaign never won.
    was_customer_on_entry = models.BooleanField(default=False)

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
            # The phone number *is* the identity, so one person appears once in
            # the whole target audience — not once per campaign. Two campaigns
            # chasing the same number would otherwise each draw their own
            # conclusions about the same human being.
            #
            # 2.36.0: this rule moved to *per campaign* (below). The global
            # constraint was dropped by migration 0029 — relaxing a unique
            # constraint is safe for the previous release, which only ever
            # inserts what it already checked.
            models.UniqueConstraint(
                fields=["campaign", "normalized_phone"], name="uniq_member_campaign_phone"
            ),
            models.CheckConstraint(
                condition=Q(stage__in=["new", "contacted", "engaged", "converted", "lost"]),
                name="target_member_stage_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "stage"], name="member_campaign_stage_idx"),
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
    #: `phone` in E.164, or blank when it is not an Iranian number (2.21.0).
    #: Kept by `save()`; indexed because contact matching falls back to the
    #: numbers people have already been called on.
    normalized_phone = models.CharField(max_length=20, blank=True, default="", db_index=True, editable=False)
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

    def save(self, *args, **kwargs):
        from common.phones import normalized_or_blank

        self.normalized_phone = normalized_or_blank(self.phone)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "phone" in update_fields and "normalized_phone" not in update_fields:
            kwargs["update_fields"] = [*update_fields, "normalized_phone"]
        super().save(*args, **kwargs)


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


class PostProviderSettings(TimeStampedModel):
    """One deployment's own post-carrier API connection — the settings a
    real `PostalCarrier` (`sales/postal.py`) would need once one exists.

    Same singleton shape as `communications.models.SmsProviderSettings`,
    and for the same reason: `sales/postal.py`'s own docstring already says
    "a future provider adds a subclass and a row in `CARRIERS`" — this is
    that provider's *connection settings*, ready before its subclass is
    written, not a business-logic change to how a parcel's status is set
    today. `ManualCarrier` stays the active carrier regardless of whether
    this row is filled in: nothing here maps a provider's own status
    vocabulary onto `sales/postal.py`'s four states, because no specific
    provider is integrated yet (CLAUDE.md §30 — "do not invent integration
    semantics when provider/business requirements are unknown"). What this
    row gives an operator today is a real, saved, testable connection an
    integration can be wired to later with no settings-page change.

    Deliberately simpler than `SmsProviderSettings`: one auth shape (a
    static header value — the common case for a tracking/status API,
    mirroring `SmsProviderSettings.AuthMode.API_KEY`) rather than two, and
    no body-template substitution, since nothing here sends a templated
    request yet — only the "تست اتصال" GET a real integration would also
    use to check its own credentials.

    `api_key` is stored as plain text, the same acknowledged gap
    `SmsProviderSettings.token_password` documents in full — no field-level
    encryption-at-rest mechanism exists anywhere in this codebase yet, and
    this row is protected the same way that one already is: never returned
    by the read API, never logged, and restricted at the database role
    level (`scripts/bootstrap-postgres.sh`).
    """

    SINGLETON = 1

    singleton = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON)
    #: Off by default — the same reasoning `SmsProviderSettings.is_enabled`
    #: documents: a control that cannot act must never be offered as if it
    #: could, and filling in every other field is not the same as confirming
    #: them.
    is_enabled = models.BooleanField(default=False)
    #: The admin's own label for whichever carrier this is — free text,
    #: shown back to them on the settings page only. Never sent in any
    #: request.
    label = models.CharField(max_length=120, blank=True)
    #: Where a real integration would reach this carrier's API — informational
    #: today, read by nothing but this settings page, until a `PostalCarrier`
    #: subclass exists to use it.
    base_url = models.CharField(max_length=500, blank=True)
    #: The header a static key is sent in — most tracking APIs use one of a
    #: small handful of names; free text rather than a fixed choice, since
    #: not knowing the eventual provider means not knowing which.
    api_key_header = models.CharField(max_length=80, blank=True, default="X-API-Key")
    api_key = models.CharField(max_length=255, blank=True)
    #: A business/sender/account code some carriers require alongside a key —
    #: never sent anywhere until a real integration exists to send it.
    sender_account_code = models.CharField(max_length=120, blank=True)
    timeout_seconds = models.PositiveSmallIntegerField(default=10)
    #: A GET endpoint the settings page's own "تست اتصال" button calls with
    #: the header above, so an operator can see a real response without
    #: waiting for an integration to exist to prove the credentials work.
    test_url = models.CharField(max_length=500, blank=True)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        verbose_name = "post provider settings"
        verbose_name_plural = "post provider settings"


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


class EbazarProductLink(TimeStampedModel):
    """A product's id at Iran Post's Ebazar service.

    Ebazar's `AddParcel` names its goods by the `EbazaarProductID` the service
    itself returned from `Product/Add`, so a product is registered there once,
    on its first shipment, and the id is kept here. Nothing about the product
    is copied back: Dolphin's own record stays the truth.
    """

    product = models.OneToOneField(Product, on_delete=models.PROTECT, related_name="ebazar_link")
    ebazar_product_id = models.CharField(max_length=40)
    unit_weight_grams = models.PositiveIntegerField()


class PostalShipment(TimeStampedModel):
    """One parcel registered with a carrier for a sales document.

    Carries only what the carrier issued or reported — the barcode, the cost,
    its own status words. The row's own `id` is the `ClientOrderId` the carrier
    knows it by. Where the parcel is, in Dolphin's four states, is
    still `SalesDocument.postal_status`, moved only through
    `sales.services.transition_postal_status`.
    """

    document = models.ForeignKey(SalesDocument, on_delete=models.PROTECT, related_name="shipments")
    carrier = models.CharField(max_length=30, default="ebazar")
    parcel_code = models.CharField(max_length=40, blank=True, db_index=True)
    shenase = models.CharField(max_length=40, blank=True)
    service_type = models.PositiveSmallIntegerField()
    pay_type = models.PositiveSmallIntegerField()
    city_id = models.PositiveIntegerField()
    weight_grams = models.PositiveIntegerField()
    goods_price_rial = models.BigIntegerField()
    shipping_cost_rial = models.BigIntegerField(null=True, blank=True)
    shipping_tax_rial = models.BigIntegerField(null=True, blank=True)
    carrier_status_code = models.SmallIntegerField(null=True, blank=True)
    carrier_status_text = models.CharField(max_length=200, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    is_cancelled = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="postal_shipments")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["document", "-created_at"])]
