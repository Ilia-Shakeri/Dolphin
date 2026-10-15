from django.db.models import Q

from accounts.access import capabilities_for, is_crm_identity
from accounts.models import User
from auditlog.models import ActivityLog

#: Any one of these lets someone open the activity log; `activity_logs_for`
#: decides which rows (2.40.48 added `audit.team`).
AUDIT_READ_CAPABILITIES = ("audit.non_platform", "audit.all", "audit.team")

#: What `audit.team` shows (owner decision 2026-10-14, BIZ-011): the sales
#: team's own work on business records. User administration, permissions,
#: settings of any kind, integrations, backups and the deployment are not in
#: it, and neither is anything the IT role or the Platform Admin did.
TEAM_AUDIT_ROLES = (User.Role.SALES_AGENT, User.Role.SALES_MANAGER)
TEAM_AUDIT_OBJECT_TYPES = frozenset({
    "sales.customer", "sales.customerphone", "sales.customercategory", "sales.lead", "sales.leadassignmenthistory",
    "sales.interaction", "sales.campaign", "sales.targetaudiencemember", "sales.campaignattribution", "sales.sale",
    "sales.salesdocument", "sales.postalshipment", "sales.postalstatushistory", "sales.product", "sales.productcategory",
    "sales.salestarget", "billing.quotation", "billing.order", "billing.invoice", "billing.payment",
    "billing.paymentallocation", "billing.cheque", "billing.installmentplan", "billing.installment",
    "billing.customerledgerentry", "inventory.warehouse", "inventory.stockitem", "inventory.stockmovement",
    "aftersales.aftersalesrequest", "aftersales.aftersaleshistory", "attachments.attachment", "tasks.task",
    "timeline.personnote", "communications.outboundsms", "communications.smscampaign", "communications.smstemplate",
    "telephony.call",
})


def activity_logs_for(user):
    queryset = ActivityLog.objects.all()
    if not is_crm_identity(user):
        return queryset.none()
    if user.role == User.Role.PLATFORM_ADMIN:
        return queryset
    if user.role == User.Role.COMPANY_IT:
        visible_roles = {
            User.Role.SALES_AGENT,
            User.Role.SALES_MANAGER,
            User.Role.COMPANY_IT,
        }
        actor_is_visible = Q(actor__isnull=True, actor_role_snapshot__in=("", "system")) | Q(
            actor__isnull=False,
            actor_role_snapshot__in=visible_roles,
        )
        object_is_visible = ~Q(object_type="accounts.user") | Q(
            object_type="accounts.user",
            object_role_snapshot__in=visible_roles,
        )
        protected_role_change = (
            Q(safe_changes__has_key="from") & Q(safe_changes__from=User.Role.PLATFORM_ADMIN)
        ) | (
            Q(safe_changes__has_key="to") & Q(safe_changes__to=User.Role.PLATFORM_ADMIN)
        )
        return queryset.filter(actor_is_visible, object_is_visible).exclude(protected_role_change)
    if "audit.team" in capabilities_for(user):
        return queryset.filter(actor_role_snapshot__in=TEAM_AUDIT_ROLES, object_type__in=TEAM_AUDIT_OBJECT_TYPES)
    return queryset.none()
