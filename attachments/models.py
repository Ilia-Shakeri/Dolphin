"""File attachments on Customer, Lead, Invoice, SalesDocument and
AfterSalesRequest.

**Storage is a BinaryField, not disk.** The `web` container's filesystem is
read-only end to end (see `test_web_filesystem_is_read_only_and_source_is_
root_owned` in `common/tests/test_database_privileges.py` — read_only,
cap_drop ALL, only a 64 MB `/tmp` tmpfs) and this codebase has never had a
`MEDIA_ROOT`. Adding one would mean a new persistent Docker volume, updated
backup tooling, and nginx changes to a deployment already running in
production — real infrastructure risk for a feature capped at 10 MB per
file. Storing the bytes in PostgreSQL instead needs none of that: the data
rides along with the volume and backup mechanism that already exist, and at
this size (small, and bounded by `ATTACHMENT_MAX_BYTES`) a `bytea` column is
a legitimate, unremarkable choice, not a workaround.

Product-owner decisions recorded 2026-09-03 (see `DOLPHIN_PROJECT_HANDOFF.md`
and `CHANGELOG.md`'s `[1.7.11]` entry for the full record):

* record types: Customer, Lead, Invoice, SalesDocument, AfterSalesRequest;
* allowed types: image (jpeg/png/webp) and PDF only, 10 MB per file;
* retention: kept forever — no automatic deletion; only an elevated role
  (sales_manager, company_it, platform_admin) may delete one by hand.

Malware scanning and a deployment-wide storage budget were **not** decided
and are not built: the first needs a real scanning engine — an external
integration this codebase has no contract for (`BACKEND_SPEC.md` gate P11) —
and the second has no approved number. Both stay open; see the CHANGELOG
entry.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.models import TimeStampedModel


#: content_type -> the file extensions accepted for it, for display only; the
#: content_type itself is what every check (constraint, service, serializer)
#: actually validates against — an extension is operator-facing labelling,
#: never trusted on its own to say what a file is.
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
    "application/pdf": (".pdf",),
}

#: Product-owner decision, 2026-09-03: 10 MB per file. A real setting
#: (`ATTACHMENT_MAX_BYTES`, `DOLPHIN_ATTACHMENT_MAX_BYTES`) rather than only
#: this constant — `attachments/services.py` reads the setting; this name
#: stays as the constraint's own fallback and the value the setting defaults
#: to, so the two can never quietly disagree.
DEFAULT_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class Attachment(TimeStampedModel):
    """One uploaded file, attached to exactly one parent record.

    Five nullable foreign keys rather than a `GenericForeignKey`: every other
    cross-cutting reference in this codebase (`InboundSMS`/`OutboundSMS` to
    Customer and Lead, for one) is an explicit typed FK with a
    `CheckConstraint` shaping which combinations are valid — never a generic
    relation, which the rest of the codebase does not use anywhere and which
    would trade a real foreign key (referential integrity, `on_delete=
    PROTECT`, an indexable column) for a `(content_type_id, object_id)` pair
    the database cannot enforce anything about.
    """

    customer = models.ForeignKey(
        "sales.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="attachments",
    )
    lead = models.ForeignKey(
        "sales.Lead", null=True, blank=True, on_delete=models.PROTECT, related_name="attachments",
    )
    invoice = models.ForeignKey(
        "billing.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="attachments",
    )
    sales_document = models.ForeignKey(
        "sales.SalesDocument", null=True, blank=True, on_delete=models.PROTECT, related_name="attachments",
    )
    after_sales_request = models.ForeignKey(
        "aftersales.AfterSalesRequest", null=True, blank=True, on_delete=models.PROTECT, related_name="attachments",
    )

    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    #: The file itself. Never included in a list/detail serializer — only
    #: `AttachmentDownloadView` ever reads this column, streamed once and
    #: never held on the response object longer than the one request.
    content = models.BinaryField()
    uploaded_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
    )
    uploaded_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        ordering = ["-uploaded_at", "-id"]
        constraints = [
            # Exactly one parent — never zero, never two. A file uploaded
            # "generally" with no record to attach to is not this feature;
            # a file that could belong to two different parents would make
            # "who may see this" ambiguous, which the object-scope selectors
            # this reuses (`attachments/selectors.py`) are not built for.
            models.CheckConstraint(
                condition=(
                    Q(customer__isnull=False, lead__isnull=True, invoice__isnull=True,
                      sales_document__isnull=True, after_sales_request__isnull=True)
                    | Q(customer__isnull=True, lead__isnull=False, invoice__isnull=True,
                        sales_document__isnull=True, after_sales_request__isnull=True)
                    | Q(customer__isnull=True, lead__isnull=True, invoice__isnull=False,
                        sales_document__isnull=True, after_sales_request__isnull=True)
                    | Q(customer__isnull=True, lead__isnull=True, invoice__isnull=True,
                        sales_document__isnull=False, after_sales_request__isnull=True)
                    | Q(customer__isnull=True, lead__isnull=True, invoice__isnull=True,
                        sales_document__isnull=True, after_sales_request__isnull=False)
                ),
                name="attachment_exactly_one_parent",
            ),
            models.CheckConstraint(
                condition=Q(content_type__in=list(ALLOWED_CONTENT_TYPES)),
                name="attachment_content_type_allowed",
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__gt=0) & Q(size_bytes__lte=DEFAULT_MAX_ATTACHMENT_BYTES),
                name="attachment_size_within_default_limit",
            ),
            models.CheckConstraint(
                condition=Q(original_filename__regex=r"\S"),
                name="attachment_filename_nonblank",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-uploaded_at"]),
            models.Index(fields=["lead", "-uploaded_at"]),
            models.Index(fields=["invoice", "-uploaded_at"]),
            models.Index(fields=["sales_document", "-uploaded_at"]),
            models.Index(fields=["after_sales_request", "-uploaded_at"]),
        ]
