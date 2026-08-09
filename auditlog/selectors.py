from django.db.models import Q

from accounts.access import is_crm_identity
from accounts.models import User
from auditlog.models import ActivityLog


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
        actor_is_visible = Q(actor__isnull=True, actor_role_snapshot="") | Q(
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
    return queryset.none()
