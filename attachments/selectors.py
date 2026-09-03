"""Object scope for attachments: reused, never reinvented.

An attachment is visible exactly when its parent record is. Each of the five
`*_for(user)` selectors imported below already answers "which rows of this
type may this user see" for its own app; this module adds no scoping logic of
its own; it only routes a request to the selector that matches whichever
parent field is set.
"""

from accounts.access import has_any_capability
from aftersales.selectors import after_sales_requests_for
from attachments.models import Attachment
from billing.selectors import invoices_for
from sales.selectors import customers_for, leads_for, sales_documents_for


#: parent field name -> (selector, capability required to write that parent —
#: the same capability each domain's own service layer already requires to
#: create or change that record). Upload reuses this; delete does not — see
#: attachments/services.py for why deletion is elevated-only regardless of
#: which parent type is involved.
PARENT_WRITE_CAPABILITY = {
    "customer": "customers.manage",
    "lead": "leads.manage",
    "invoice": "invoices.manage",
    "sales_document": "sales_documents.manage",
    # An after-sales-workstream agent works their assigned cases without
    # holding after_sales.manage; either capability is enough to attach a
    # file to a case they may already act on.
    "after_sales_request": ("after_sales.manage", "after_sales.work"),
}

PARENT_SELECTORS = {
    "customer": customers_for,
    "lead": leads_for,
    "invoice": invoices_for,
    "sales_document": sales_documents_for,
    "after_sales_request": after_sales_requests_for,
}

PARENT_FIELDS = tuple(PARENT_SELECTORS)


def parent_is_visible(user, field_name, parent_id):
    """Whether this user may see `field_name`'s parent row `parent_id` at all."""
    if field_name not in PARENT_FIELDS:
        return False
    return PARENT_SELECTORS[field_name](user).filter(pk=parent_id).exists()


def can_write_parent(user, field_name):
    required = PARENT_WRITE_CAPABILITY[field_name]
    capabilities = (required,) if isinstance(required, str) else required
    return has_any_capability(user, *capabilities)


def attachments_for(user, *, field_name, parent_id):
    """Attachments on one specific parent record, or none if it is out of scope."""
    if not parent_is_visible(user, field_name, parent_id):
        return Attachment.objects.none()
    return Attachment.objects.filter(**{field_name: parent_id})
