"""The features and deployment profiles this codebase knows about.

Three separate controls exist and must not be merged:

* **feature availability** — this module and the signed manifest: may this
  deployment run a module at all;
* **role permission** — `accounts/access.py`: may this role use it;
* **object scope** — each app's `selectors.py`: which rows may this user see.

Nothing here mentions a customer name, and no code branches on one. A
deployment is described entirely by a signed manifest naming a profile id and a
feature set.

Feature dependencies are read off the actual data model, not invented: a feature
depends on another only where a *non-nullable* foreign key makes its rows
impossible without the other module's rows.
"""


# feature name -> features it cannot function without
FEATURE_DEPENDENCIES = {
    # sales.Customer / sales.CustomerPhone
    "customers": frozenset(),
    # sales.ProductCategory / sales.Product
    "products": frozenset(),
    # sales.Lead, LeadAssignmentHistory, Interaction — Lead.customer is NOT NULL
    "leads": frozenset({"customers"}),
    # sales.Sale — lead and customer are NOT NULL; product is nullable
    "sales": frozenset({"customers", "leads"}),
    # sales.SalesDocument / PostalStatusHistory — customer NOT NULL, sale nullable
    "sales_documents": frozenset({"customers"}),
    # aftersales.AfterSalesRequest — customer NOT NULL, sale and document nullable
    "after_sales": frozenset({"customers"}),
    # communications.InboundSMS — provider-neutral internal storage and report
    "inbound_sms": frozenset(),
    # inventory.Warehouse / StockItem / StockMovement — StockItem.product is
    # NOT NULL, and the ledger's soft reference to a billing document is
    # deliberately not a foreign key so inventory stays usable on its own.
    "inventory": frozenset({"products"}),
    # billing.Quotation / QuotationItem — customer and item product NOT NULL
    "quotations": frozenset({"customers", "products"}),
    # billing.Order / OrderItem — same non-nullable pair
    "orders": frozenset({"customers", "products"}),
    # billing.Invoice / InvoiceItem — same non-nullable pair
    "invoices": frozenset({"customers", "products"}),
    # billing.Payment (customer NOT NULL) and PaymentAllocation (invoice NOT
    # NULL): allocating money needs an invoice to allocate it to.
    "payments": frozenset({"customers", "invoices"}),
    # billing.CustomerLedgerEntry — customer NOT NULL
    "customer_ledger": frozenset({"customers"}),
    # reports: user performance metrics count customers and sales
    "reports": frozenset({"customers", "sales"}),
    # auditlog.ActivityLog
    "audit_log": frozenset(),
    # The `company_it` CRM role itself. Unlike every other entry this gates a
    # *role* rather than a module, which is why it is named for the role and not
    # for an app: some deployments want an on-site technical account, and
    # Client-1 policy is that nobody but a Platform Admin administers users.
    # With this absent the role cannot be assigned, is not offered in the UI,
    # and the service refuses it — existing rows keep working and are never
    # deleted, exactly as with any other disabled feature.
    "internal_it_role": frozenset(),
}

#: Features this release ships but does not serve by default.
#:
#: Quotations (پیش‌فاکتور) is the whole of it today: Client-1 raises an invoice
#: first and never issues a pre-invoice, so the module has no place in the panel
#: and its sidebar entry, pages and API are all withheld. The models, services,
#: serializers and tests stay in the codebase and stay reusable — a deployment
#: whose signed manifest names `quotations` gets it back with nothing to
#: rebuild. This only decides what a deployment gets when nobody has said
#: otherwise.
DEFAULT_OFF_FEATURES = frozenset({"quotations"})

FEATURES = frozenset(FEATURE_DEPENDENCIES)

# Every feature the current code actually ships. A deployment may enable a
# subset; it may never enable something absent from this set.
ALL_FEATURES = FEATURES

#: What a deployment runs when no manifest narrows it: everything this release
#: ships, minus the modules that are off by default.
DEFAULT_FEATURES = ALL_FEATURES - DEFAULT_OFF_FEATURES

# Known deployment profile identifiers. An id absent from this table is refused
# even when its signature is valid, so a manifest issued for a deployment this
# release does not know about cannot start it.
PROFILES = {
    "client-1": "First operational customer deployment.",
    "demo": "Reduced demonstration deployment.",
    "development": "Local development and automated tests only.",
}


def unknown_features(names):
    """Return the requested feature names this release does not ship."""
    return frozenset(names) - FEATURES


def missing_dependencies(names):
    """Return {feature: missing required features} for an enabled feature set."""
    enabled = frozenset(names)
    missing = {}
    for feature in sorted(enabled & FEATURES):
        absent = FEATURE_DEPENDENCIES[feature] - enabled
        if absent:
            missing[feature] = frozenset(absent)
    return missing
