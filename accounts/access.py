from django.db.models import Exists, OuterRef

from accounts.models import User


CRM_ROLES = {value for value, _ in User.Role.choices}

# User administration is reserved for `platform_admin` alone. This is the secure
# default of the shared codebase, not a Client-1 special case: `sales_manager`,
# `company_it`, and `sales_agent` hold no `users.manage_*` capability, so
# `IsUserReader`, the maintained UI navigation, and the user pages all deny them
# without any per-role check elsewhere.
#
# A future deployment may reintroduce a narrower capability through the approved
# signed deployment manifest (PROFILE-001, Option C). Until that mechanism
# exists, nothing may re-grant these capabilities.
ROLE_CAPABILITIES = {
    User.Role.SALES_AGENT: frozenset({
        "dashboard.agent",
        "customers.scoped",
        "customers.manage",
        "leads.scoped",
        "leads.manage",
        "interactions.scoped",
        "interactions.manage",
        "sales.own",
        "sales.manage",
        "sales_documents.scoped",
        "products.read",
        "product_categories.read",
        # An agent may read stock to answer "can we sell this", and may never
        # change a level: every movement is a manager operation.
        "inventory.read",
        # An agent prepares commercial documents for their own customers. They
        # may not issue an invoice or take money — those are `*.company`
        # capabilities held only by elevated roles.
        "quotations.scoped",
        "quotations.manage",
        "orders.scoped",
        "orders.manage",
        "invoices.scoped",
        "invoices.manage",
        "reports.own",
        # بند ۶.۳ — «آیا بازاریاب باید مانده مشتریان خودش را ببیند؟» «بله».
        #
        # Deliberately **not** `ledger.company`. Permission and object scope are
        # separate controls here: this says a marketer may read a ledger at all,
        # and `ledger_entries_for` decides whose. Widening `ledger.company` to
        # this role would have granted the company-wide view and then relied on
        # a queryset to take most of it back, which is the shape that turns one
        # missed filter into every customer's balance.
        "ledger.own",
    }),
    User.Role.SALES_MANAGER: frozenset({
        "dashboard.store",
        "customers.company",
        "customers.manage",
        "leads.company",
        "leads.manage",
        "interactions.company",
        "interactions.manage",
        "sales.company",
        "sales.manage",
        "sales_documents.company",
        "sales_documents.manage",
        "after_sales.company",
        "after_sales.manage",
        "products.manage",
        "product_categories.read",
        "product_categories.manage",
        "inventory.read",
        "inventory.manage",
        "quotations.company",
        "quotations.manage",
        "orders.company",
        "orders.manage",
        "invoices.company",
        "invoices.manage",
        "payments.company",
        "payments.manage",
        "ledger.company",
        "reports.company",
        "sms.company",
    }),
    User.Role.COMPANY_IT: frozenset({
        "dashboard.technical",
        "customers.company",
        "customers.manage",
        "leads.company",
        "leads.manage",
        "interactions.company",
        "interactions.manage",
        "sales.company",
        "sales.manage",
        "sales_documents.company",
        "sales_documents.manage",
        "after_sales.company",
        "after_sales.manage",
        "products.manage",
        "product_categories.read",
        "product_categories.manage",
        "inventory.read",
        "inventory.manage",
        "quotations.company",
        "quotations.manage",
        "orders.company",
        "orders.manage",
        "invoices.company",
        "invoices.manage",
        "payments.company",
        "payments.manage",
        "ledger.company",
        "reports.company",
        "sms.company",
        "audit.non_platform",
    }),
    User.Role.PLATFORM_ADMIN: frozenset({
        "dashboard.platform",
        "customers.company",
        "customers.manage",
        "leads.company",
        "leads.manage",
        "interactions.company",
        "interactions.manage",
        "sales.company",
        "sales.manage",
        "sales_documents.company",
        "sales_documents.manage",
        "after_sales.company",
        "after_sales.manage",
        "products.manage",
        "product_categories.read",
        "product_categories.manage",
        "inventory.read",
        "inventory.manage",
        "quotations.company",
        "quotations.manage",
        "orders.company",
        "orders.manage",
        "invoices.company",
        "invoices.manage",
        "payments.company",
        "payments.manage",
        "ledger.company",
        "reports.company",
        "sms.company",
        "users.manage_all",
        "audit.all",
    }),
}

AFTER_SALES_AGENT_CAPABILITIES = frozenset({
    "dashboard.after_sales",
    "after_sales.assigned",
    "after_sales.work",
})


def crm_identities(queryset=None):
    queryset = queryset if queryset is not None else User.objects.all()
    group_memberships = User.groups.through.objects.filter(user_id=OuterRef("pk"))
    direct_permissions = User.user_permissions.through.objects.filter(user_id=OuterRef("pk"))
    return (
        queryset.filter(
            role__in=CRM_ROLES,
            is_staff=False,
            is_superuser=False,
        )
        .alias(
            _has_server_group=Exists(group_memberships),
            _has_direct_permission=Exists(direct_permissions),
        )
        .filter(
            _has_server_group=False,
            _has_direct_permission=False,
        )
    )


def is_crm_account(user):
    if not user or user.role not in CRM_ROLES or user.is_staff or user.is_superuser or user.pk is None:
        return False
    return not user.groups.exists() and not user.user_permissions.exists()


def is_crm_identity(user):
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and is_crm_account(user)
    )


#: Capabilities a per-user override may never touch, regardless of who is
#: signed in as Platform Admin at the time. User administration and the audit
#: trail are the codebase's own hard security defaults (see the comment on
#: `ROLE_CAPABILITIES` above) — a per-user permission matrix is a convenience
#: for the ordinary business modules, not a back door around that boundary.
#: Enforced twice on purpose: `set_user_permission_overrides` refuses to save
#: a row naming one of these, and this function refuses to honour one even if
#: a row existed anyway (a manual DB edit, a future bug elsewhere).
PROTECTED_CAPABILITY_PREFIXES = ("users.", "audit.")


def _is_protected_capability(capability):
    return capability.startswith(PROTECTED_CAPABILITY_PREFIXES)


def role_default_capabilities(user):
    """What `user` holds from their role alone, before any personal override.

    This is the function the rest of the codebase called `capabilities_for`
    before per-user overrides existed, kept under its own name so the override
    layer below has something stable to diff against — the permissions screen
    shows an admin exactly which rows on a user's matrix differ from this.
    """
    if not is_crm_identity(user):
        return frozenset()
    if user.role == User.Role.SALES_AGENT and user.workstream == User.Workstream.AFTER_SALES:
        return AFTER_SALES_AGENT_CAPABILITIES
    return ROLE_CAPABILITIES.get(user.role, frozenset())


def capabilities_for(user):
    base = role_default_capabilities(user)
    if not is_crm_identity(user):
        return base
    overrides = getattr(user, "_capability_overrides_cache", None)
    if overrides is None:
        from accounts.models import UserCapabilityOverride

        overrides = list(
            UserCapabilityOverride.objects.filter(user_id=user.pk).values_list("capability", "granted")
        )
    if not overrides:
        return base
    result = set(base)
    for capability, granted in overrides:
        if _is_protected_capability(capability):
            continue
        if granted:
            result.add(capability)
        else:
            result.discard(capability)
    return frozenset(result)


def has_any_capability(user, *capabilities):
    return bool(capabilities_for(user).intersection(capabilities))


#: Persian labels for the roles a user may be moved to. Kept beside the rule
#: that decides which of them are offered, so the two cannot drift.
ROLE_LABELS = {
    User.Role.SALES_AGENT: "بازاریاب (کال سنتر)",
    User.Role.SALES_MANAGER: "مدیر فروشگاه",
    User.Role.COMPANY_IT: "مدیر فنی مشتری",
    User.Role.PLATFORM_ADMIN: "مدیر پلتفرم",
}


def assignable_roles(actor):
    """The roles `actor` may move somebody to, or create a new account as, in
    display order.

    Platform Admin is never in this list, for anyone, including an acting
    Platform Admin: the product keeps exactly one Platform Admin account at a
    time, provisioned only out-of-band by `bootstrap_platform_admin` (which
    itself refuses to run a second time), never through the CRM's own create-
    user or change-role paths — see `_protect_last_active_platform_admin` for
    the matching floor (never drop below one) that this function is the
    ceiling for (never rise above one). `actor` is still a parameter, kept for
    a future per-actor gate and so callers need not change, even though no
    current rule depends on it beyond the deployment-wide feature flag below.

    The template renders this list rather than hardcoding options, so the page
    and `change_user_role`/`create_crm_user` can never disagree about what is
    allowed.
    """
    from common.deployment.profile import feature_enabled

    order = (
        User.Role.SALES_AGENT,
        User.Role.SALES_MANAGER,
        User.Role.COMPANY_IT,
    )
    allowed = []
    for role in order:
        if role == User.Role.COMPANY_IT and not feature_enabled("internal_it_role"):
            continue
        allowed.append((role.value, ROLE_LABELS[role]))
    return allowed
