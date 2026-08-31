"""The Read/Edit permission matrix an admin edits, translated to real capabilities.

`accounts.access.ROLE_CAPABILITIES` is the actual authority the rest of the
codebase checks — dozens of call sites already read it through
`has_any_capability`. This module does not replace that; it is a curated,
human-facing VIEW over it: one row per real page/feature of the panel, each
row showing whether the signed-in target user can read it and whether they
can also change it, with the specific capability strings that mean "yes" on
each side named right here so the mapping cannot drift out of sight.

Two things this matrix deliberately does NOT cover, because they are already
governed by a stricter, hard-coded rule elsewhere and a permission screen must
not appear to relax it: `users` (user administration) and `audit` (the
activity log). See the comment on `ROLE_CAPABILITIES` in `accounts/access.py`.

A module's "edit" column, where it exists, grants ordinary create/update
through that module's own list/detail screen — it does not reach into the
narrower business-rule gates a few advanced actions still carry on top (an
Invoice's Edit lets an operator work on a draft; issuing, cancelling, or
reissuing one stays Sales-Manager-and-above regardless, exactly as it always
has, because those are policy decisions about a document's lifecycle, not
data-entry rights). Modules with no write side at all — reports, ledger,
inbound SMS — carry no edit capability and no `write` key.

Known asymmetry, honestly noted rather than hidden: REVOKING edit for
`quotations`, `orders`, `invoices`, or `payments` fully blocks basic
create/update through this screen — the view-permission gate enforces it
before any service function runs. GRANTING edit on those four modules to a
role that never had it does not yet unlock the deeper service-layer gates
(`billing._lock_document_writer`, `billing.payments._lock_payment_manager`),
which are still plain role checks shared across several document types —
threading a per-module capability through them safely is follow-up work,
tracked in KARIZ_PROJECT_HANDOFF.md. Every other module's edit column (both
directions) is enforced end to end, including granting beyond a role's
default — see `accounts/tests/test_permission_overrides.py`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    key: str
    label: str
    #: Capabilities where holding *any one* means "can read this module".
    read: tuple
    #: Capabilities where holding *any one* means "can also write to it".
    #: Empty for a module with no write side of its own.
    write: tuple = ()


MODULES = (
    Module("customers", "مشتریان", ("customers.scoped", "customers.company"), ("customers.manage",)),
    Module("leads", "سرنخ‌ها", ("leads.scoped", "leads.company"), ("leads.manage",)),
    Module("interactions", "تعامل‌های مرکز تماس", ("interactions.scoped", "interactions.company"), ("interactions.manage",)),
    Module("sales", "نتایج کمپین فروش", ("sales.own", "sales.company"), ("sales.manage",)),
    Module("product_categories", "دسته‌بندی کالا", ("product_categories.read", "product_categories.manage"), ("product_categories.manage",)),
    Module("products", "کاتالوگ محصولات", ("products.read", "products.manage"), ("products.manage",)),
    Module("quotations", "پیش‌فاکتورها", ("quotations.scoped", "quotations.company"), ("quotations.manage",)),
    Module("orders", "سفارش‌ها", ("orders.scoped", "orders.company"), ("orders.manage",)),
    Module("invoices", "فاکتورها (اسناد مالی)", ("invoices.scoped", "invoices.company"), ("invoices.manage",)),
    Module("payments", "دریافت‌ها، پرداخت‌ها، چک و اقساط", ("payments.company",), ("payments.manage",)),
    Module("ledger", "دفتر حساب مشتری", ("ledger.own", "ledger.company")),
    Module("inventory", "انبار و موجودی", ("inventory.read", "inventory.manage"), ("inventory.manage",)),
    Module("sales_documents", "اسناد فروش داخلی (پستی)", ("sales_documents.scoped", "sales_documents.company"), ("sales_documents.manage",)),
    Module("after_sales", "خدمات پس از فروش", ("after_sales.company", "after_sales.assigned"), ("after_sales.manage",)),
    Module("reports", "گزارش‌ها", ("reports.own", "reports.company")),
    Module("communications", "گزارش پیامک ورودی", ("sms.company",)),
)

MODULES_BY_KEY = {module.key: module for module in MODULES}


def role_held_capabilities(role, workstream=None):
    """The raw capability set `accounts.access.ROLE_CAPABILITIES` gives this
    role, ignoring any per-user override — the "role alone" baseline every
    other function in this module diffs or reconciles against.
    """
    from accounts.access import AFTER_SALES_AGENT_CAPABILITIES, ROLE_CAPABILITIES
    from accounts.models import User

    if role == User.Role.SALES_AGENT and workstream == User.Workstream.AFTER_SALES:
        return AFTER_SALES_AGENT_CAPABILITIES
    return ROLE_CAPABILITIES.get(role, frozenset())


def default_matrix_for_role(role, workstream=None):
    """The Read/Edit matrix a fresh, unoverridden user of this role would see.

    Mirrors `accounts.access.role_default_capabilities` without needing a real
    `User` instance, so the Create User form can show what a role grants
    before the account exists yet.
    """
    held = role_held_capabilities(role, workstream)
    return {
        module.key: {
            "read": any(capability in held for capability in module.read),
            "write": any(capability in held for capability in module.write) if module.write else False,
        }
        for module in MODULES
    }


def effective_matrix_for_user(user):
    """The Read/Edit matrix `user` actually has right now, role plus overrides.

    Also reports, per module, whether the row is an override (differs from
    what the role alone would give) — the permissions screen uses that to mark
    a customised row without recomputing the diff itself.
    """
    from accounts.access import capabilities_for

    held = capabilities_for(user)
    defaults = default_matrix_for_role(user.role, user.workstream)
    matrix = {}
    for module in MODULES:
        read = any(capability in held for capability in module.read)
        write = any(capability in held for capability in module.write) if module.write else False
        default = defaults[module.key]
        matrix[module.key] = {
            "read": read,
            "write": write,
            "is_custom": read != default["read"] or write != default["write"],
        }
    return matrix


def validate_matrix(matrix):
    """Reject a client-supplied matrix that isn't shaped like this registry.

    Returns the matrix normalised to booleans, with edit-implies-read already
    applied (an edit with no read is promoted to read+edit rather than
    refused — the UI already prevents the invalid state, so a client that
    still sends it gets the same correction the checkbox would have made,
    not an error over something the UI itself makes impossible to construct).
    """
    if not isinstance(matrix, dict):
        raise ValueError("Permission matrix must be an object.")
    unknown = set(matrix) - set(MODULES_BY_KEY)
    if unknown:
        raise ValueError(f"Unknown module(s): {', '.join(sorted(unknown))}.")
    normalised = {}
    for key, module in MODULES_BY_KEY.items():
        entry = matrix.get(key, {})
        if not isinstance(entry, dict):
            raise ValueError(f"Module '{key}' must be an object with read/write flags.")
        read = bool(entry.get("read", False))
        write = bool(entry.get("write", False)) if module.write else False
        if write and not read:
            read = True
        normalised[key] = {"read": read, "write": write}
    return normalised


def capabilities_for_matrix(matrix, *, role, workstream=None):
    """Which capability, per module, encodes a row's read/write choice for
    a user of this role.

    A module's *read* side may name two capabilities — a `.scoped`/`.own` one
    and a `.company` one — because that axis also carries object scope, a
    second and separate control this matrix does not touch. Blindly granting
    both whenever "read" is turned on would hand a Sales Agent the
    company-wide capability alongside their own-scope one, which is a scope
    escalation this function refuses to cause: it always acts on the ONE
    capability this role already holds by default (its natural scope tier),
    falling back to the narrower, first-listed capability only for a role
    that starts with neither — an admin can only ever widen someone's *access
    to the feature*, never their *object scope*, through this screen.

    Returns `{capability: bool}` for exactly the capabilities this matrix
    governs for this role, meant to be reconciled against a user's current
    capabilities by `set_user_permission_overrides`.
    """
    role_held = role_held_capabilities(role, workstream)

    result = {}
    for key, module in MODULES_BY_KEY.items():
        entry = matrix[key]

        def _target_capability(candidates):
            for capability in candidates:
                if capability in role_held:
                    return capability
            return candidates[0]

        if module.read:
            capability = _target_capability(module.read)
            result[capability] = entry["read"]
            # Any *other* scope capability on this axis must stay exactly
            # where the role default left it — never forced on, and never
            # forced off underneath a role that genuinely holds it.
            for other in module.read:
                if other != capability:
                    result.setdefault(other, other in role_held)
        if module.write:
            capability = _target_capability(module.write)
            result[capability] = entry["write"]
            for other in module.write:
                if other != capability:
                    result.setdefault(other, other in role_held)
    return result


def governed_capabilities():
    """Every capability this matrix ever reads or writes, for a final
    defensive check before anything is persisted — none of these may start
    with `users.` or `audit.` by construction, since neither module is ever
    listed above, but a future edit to `MODULES` gets caught here instead of
    silently opening the one boundary that must not move.
    """
    result = set()
    for module in MODULES:
        result.update(module.read)
        result.update(module.write)
    return result


def overrides_needed_for_matrix(matrix, *, role, workstream=None):
    """Which `{capability: granted}` rows must exist for `matrix` to hold.

    Only a capability that actually *disagrees* with what the role would give
    for free needs a row — matching the default needs no override at all, so
    resaving a matrix nobody touched leaves the override table exactly as
    empty as it was. This is the one place that decides "is this an
    override", so `set_user_permission_overrides` never has to.
    """
    role_held = role_held_capabilities(role, workstream)
    desired = capabilities_for_matrix(matrix, role=role, workstream=workstream)
    return {
        capability: granted
        for capability, granted in desired.items()
        if granted != (capability in role_held)
    }
