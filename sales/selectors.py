from django.db.models import Case, IntegerField, Q, Value, When

from accounts.models import User
from sales.models import (
    Customer,
    CustomerPhone,
    Interaction,
    Lead,
    Product,
    ProductCategory,
    Sale,
    SalesDocument,
    TargetAudienceMember,
)


ELEVATED_OPERATIONAL = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def customers_for(user):
    """Which customers a role may see.

    A marketer sees the customers they entered themselves, and no others. They
    previously also saw every customer behind a lead assigned to them, which
    made the customer book grow silently as work was handed around; Client-1
    wants own-entry scope, so that is what this enforces.
    """
    queryset = Customer.objects.all()
    if user.role == User.Role.SALES_AGENT:
        if user.workstream == User.Workstream.AFTER_SALES:
            return queryset.none()
        return queryset.filter(created_by=user)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def phones_for(user):
    return CustomerPhone.objects.filter(customer__in=customers_for(user))


def leads_for(user):
    queryset = Lead.objects.all()
    if user.role == User.Role.SALES_AGENT:
        if user.workstream == User.Workstream.AFTER_SALES:
            return queryset.none()
        return queryset.filter(Q(assigned_to=user) | Q(created_by=user, assigned_to__isnull=True)).distinct()
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def lead_work_queue_for(user):
    if user.role != User.Role.SALES_AGENT:
        return Lead.objects.none()
    return (
        leads_for(user)
        .filter(assigned_to=user)
        .annotate(
            _follow_up_missing=Case(
                When(next_follow_up_at__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("_follow_up_missing", "next_follow_up_at", "-assigned_at", "-id")
    )


def interactions_for(user):
    queryset = Interaction.objects.all()
    if user.role == User.Role.SALES_AGENT:
        if user.workstream == User.Workstream.AFTER_SALES:
            return queryset.none()
        return queryset.filter(lead__assigned_to=user)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def products_for(user):
    queryset = Product.objects.all()
    if user.role == User.Role.SALES_AGENT:
        if user.workstream == User.Workstream.AFTER_SALES:
            return queryset.none()
        return queryset.filter(is_active=True)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def product_categories_for(user):
    queryset = ProductCategory.objects.all()
    if user.role == User.Role.SALES_AGENT:
        if user.workstream == User.Workstream.AFTER_SALES:
            return queryset.none()
        return queryset.filter(is_active=True)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def sales_for(user):
    queryset = Sale.objects.all()
    if user.role == User.Role.SALES_AGENT:
        if user.workstream == User.Workstream.AFTER_SALES:
            return queryset.none()
        return queryset.filter(sold_by=user)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def sales_documents_for(user):
    queryset = SalesDocument.objects.all()
    if user.role == User.Role.SALES_AGENT:
        if user.workstream == User.Workstream.AFTER_SALES:
            return queryset.none()
        return queryset.filter(
            Q(customer__in=customers_for(user)) | Q(sale__in=sales_for(user))
        ).distinct()
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def target_audience_for(user):
    """The campaign identities a role may see.

    Scoped through the lead that owns them, so a marketer sees the target
    audience of the campaigns assigned to them and nothing else. Read access
    only is a separate question from write access, which lives in the service.
    """
    return TargetAudienceMember.objects.filter(lead__in=leads_for(user))
