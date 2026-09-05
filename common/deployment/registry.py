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
    # communications.OutboundSMS — customer/lead are nullable (an ad-hoc
    # number is a valid recipient too), so no non-nullable FK forces a
    # dependency; the sending UI still points at a customer/lead in practice.
    "outbound_sms": frozenset(),
    # attachments.Attachment — every one of its five parent FKs is nullable
    # (a CheckConstraint requires exactly one, not any particular one), so no
    # single feature is a hard dependency by the "non-nullable FK" rule. In
    # practice an attachment is useless without at least customers enabled
    # (every one of the five parent types is itself customer-shaped or reachable
    # only through a customer), so customers is named explicitly here as a
    # practical dependency even though the schema alone would not force it.
    "attachments": frozenset({"customers"}),
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
    # common.BrandSettings — like internal_it_role, this gates a capability
    # rather than a data model: whether this deployment's own Platform Admin
    # may replace the Dolphin/دلفین name and logo shown across the panel with
    # their own (common/branding.py). No non-nullable FK forces a dependency
    # (BrandSettings stands alone), and turning it off does not delete a
    # customer's saved name/logo — it just stops being shown, exactly like any
    # other disabled feature; turning it back on shows the same row again.
    "custom_branding": frozenset(),
    # chat.ChatThread / ChatParticipant / ChatMessage — internal coordination
    # chat between colleagues of the same deployment. No non-nullable FK into
    # any other module forces a dependency; the three models stand alone.
    "internal_chat": frozenset(),
    # common/reminders.py — the topbar bell. Like `custom_branding` and
    # `internal_it_role` this gates a capability rather than a data model:
    # there is no reminder table, only a read across due dates other modules
    # already own (lead follow-ups, after-sales appointments, cheque and
    # instalment due dates). Deliberately no dependency: each of those four
    # sources is checked for its own feature at read time and simply omitted
    # when that module is off, so this stays useful on a deployment running
    # any one of them and shows nothing at all on a deployment running none.
    "reminders": frozenset(),
    # common/search.py — the header search box. Same shape as `reminders`
    # again: no table of its own, and no dependency, because each of its
    # eight sources is checked for its own feature at read time and simply
    # left out when that module is off. A deployment running only
    # `customers` gets a search box that finds customers.
    "global_search": frozenset(),
    # common/customer_timeline.py — the customer page's history strip. Needs
    # `customers` and nothing else: a timeline is *about* a customer, and
    # every other source it reads (calls, invoices, payments, after-sales,
    # attachments, SMS) is checked for its own feature at read time and left
    # out when that module is off.
    "customer_timeline": frozenset({"customers"}),
    # common/dashboard.py — the home page's KPI strip, sales trend and status
    # breakdown. No table, and no dependency: each of its sources (sales,
    # invoices, leads, after-sales) is checked for its own feature at read
    # time, so a deployment running any one of them gets the parts it can
    # fill and a deployment running none gets a page that looks exactly as
    # it did before this existed.
    "dashboard_insights": frozenset(),
    # The leads board (/leads/board/) — the same Lead rows the ordinary list
    # page shows, as a status-column view instead of a table. No table of its
    # own and no mutation path of its own: dragging a card between columns
    # goes through the existing `PATCH /api/v1/leads/<id>/` (LeadSerializer.
    # update -> sales.services.update_lead), the same endpoint the ordinary
    # list and the follow-up calendar already use, so it is scoped and
    # permission-checked exactly like they are. `leads` is a real hard
    # dependency, unlike the read-only additions above: a board with nothing
    # to group is not a smaller version of this feature, it is not this
    # feature.
    "lead_kanban": frozenset({"leads"}),
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
#:
#: `custom_branding` joins it for a different reason: the product-owner
#: decision behind it (2026-09-03) is that a deployment shows Dolphin/دلفین
#: branding *unless* someone deliberately turns white-labelling on for that
#: customer — the safe default is the platform's own brand, not a customer's.
#:
#: `internal_chat` (2026-09-04) joins it the same way `custom_branding` did:
#: a real, finished module nobody has asked for yet on any live deployment,
#: opt-in per customer through the same manifest, with nothing to rebuild
#: when one does.
#:
#: `reminders` (2026-09-04) is deliberately **not** here, unlike the three
#: above, and the difference is the point: it is not a module a customer
#: would buy separately and it holds no data of its own. It surfaces rows the
#: signed-in user can already open by hand, from modules that deployment has
#: already been given, on pages it already has — so a deployment that gets
#: `leads` and says nothing else should get the bell that makes those leads'
#: own follow-up dates visible. It stays a named feature (any deployment can
#: still turn it off through its manifest, like anything else here); it just
#: does not default to off. `global_search`, `customer_timeline` and
#: `dashboard_insights` (all 2026-09-04) are absent for exactly the same
#: reason and on the same reasoning.
#:
#: `lead_kanban` (2026-09-05) joins the default-off side instead, and for the
#: same reason `internal_chat` did rather than the reason `reminders` did not:
#: it is not a read-only convenience layered onto a page every deployment
#: already has, it is a second, separately meaningful *page* built around a
#: new frontend dependency (the theme's own `jkanban` bundle) and a drag
#: interaction some deployments may not want offered on their sales floor at
#: all. A deployment gets it by asking, the same way it gets chat.
DEFAULT_OFF_FEATURES = frozenset({"quotations", "custom_branding", "internal_chat", "lead_kanban"})

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
