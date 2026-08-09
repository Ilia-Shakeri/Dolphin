from accounts.access import crm_identities
from accounts.models import User


REPORT_BROAD_ROLES = {
    User.Role.SALES_MANAGER,
    User.Role.COMPANY_IT,
    User.Role.PLATFORM_ADMIN,
}
REPORT_ROLES = REPORT_BROAD_ROLES | {User.Role.SALES_AGENT}


def users_for_performance_report(actor):
    valid_roles = [value for value, _ in User.Role.choices]
    queryset = crm_identities(User.objects.filter(role__in=valid_roles)).order_by("id")
    if actor.role == User.Role.SALES_AGENT:
        return queryset.filter(pk=actor.pk)
    if actor.role in REPORT_BROAD_ROLES:
        return queryset
    return queryset.none()
