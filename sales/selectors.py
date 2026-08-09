from django.db.models import Q

from accounts.models import User
from sales.models import Customer, CustomerPhone, Interaction, Lead, Product, Sale


ELEVATED_OPERATIONAL = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def customers_for(user):
    queryset = Customer.objects.all()
    if user.role == User.Role.SALES_AGENT:
        return queryset.filter(Q(created_by=user) | Q(leads__assigned_to=user)).distinct()
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def phones_for(user):
    return CustomerPhone.objects.filter(customer__in=customers_for(user))


def leads_for(user):
    queryset = Lead.objects.all()
    if user.role == User.Role.SALES_AGENT:
        return queryset.filter(assigned_to=user)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def interactions_for(user):
    queryset = Interaction.objects.all()
    if user.role == User.Role.SALES_AGENT:
        return queryset.filter(lead__assigned_to=user)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def products_for(user):
    queryset = Product.objects.all()
    if user.role == User.Role.SALES_AGENT:
        return queryset.filter(is_active=True)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def sales_for(user):
    queryset = Sale.objects.all()
    if user.role == User.Role.SALES_AGENT:
        return queryset.filter(sold_by=user)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()
