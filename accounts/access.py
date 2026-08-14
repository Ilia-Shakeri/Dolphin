from django.db.models import Exists, OuterRef

from accounts.models import User


CRM_ROLES = {value for value, _ in User.Role.choices}

ROLE_CAPABILITIES = {
    User.Role.SALES_AGENT: frozenset({
        "dashboard.agent",
        "customers.scoped",
        "leads.scoped",
        "interactions.scoped",
        "sales.own",
        "sales_documents.scoped",
        "products.read",
        "reports.own",
    }),
    User.Role.SALES_MANAGER: frozenset({
        "dashboard.store",
        "customers.company",
        "leads.company",
        "interactions.company",
        "sales.company",
        "sales_documents.company",
        "sales_documents.manage",
        "after_sales.company",
        "after_sales.manage",
        "products.manage",
        "reports.company",
        "sms.company",
        "users.manage_agents",
    }),
    User.Role.COMPANY_IT: frozenset({
        "dashboard.technical",
        "customers.company",
        "leads.company",
        "interactions.company",
        "sales.company",
        "sales_documents.company",
        "sales_documents.manage",
        "after_sales.company",
        "after_sales.manage",
        "products.manage",
        "reports.company",
        "sms.company",
        "users.manage_non_platform",
        "audit.non_platform",
    }),
    User.Role.PLATFORM_ADMIN: frozenset({
        "dashboard.platform",
        "customers.company",
        "leads.company",
        "interactions.company",
        "sales.company",
        "sales_documents.company",
        "sales_documents.manage",
        "after_sales.company",
        "after_sales.manage",
        "products.manage",
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


def capabilities_for(user):
    if not is_crm_identity(user):
        return frozenset()
    if user.role == User.Role.SALES_AGENT and user.workstream == User.Workstream.AFTER_SALES:
        return AFTER_SALES_AGENT_CAPABILITIES
    return ROLE_CAPABILITIES.get(user.role, frozenset())


def has_any_capability(user, *capabilities):
    return bool(capabilities_for(user).intersection(capabilities))
