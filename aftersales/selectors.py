from accounts.models import User
from aftersales.models import AfterSalesRequest


ELEVATED = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def after_sales_requests_for(user):
    queryset = AfterSalesRequest.objects.all()
    if user.role in ELEVATED:
        return queryset
    if user.role == User.Role.SALES_AGENT and user.workstream == User.Workstream.AFTER_SALES:
        return queryset.filter(assigned_to=user)
    return queryset.none()
