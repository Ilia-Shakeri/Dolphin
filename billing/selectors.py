"""Object scope for the commercial documents.

A Sales Agent sees a document they created, or one belonging to a customer
already inside their customer scope (created by them, or the customer of a lead
assigned to them). Everything else is invisible by row, not merely hidden in the
UI: a direct-ID read answers 404 exactly as it does for customers and leads.

Payments and the customer ledger are money records and stay company-only.
"""

from django.db.models import Q

from accounts.models import User
from billing.models import (
    Cheque,
    CustomerLedgerEntry,
    Installment,
    InstallmentPlan,
    Invoice,
    Order,
    Payment,
    Quotation,
)
from sales.selectors import customers_for


ELEVATED_OPERATIONAL = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def _sales_agent_in_scope(user):
    return user.role == User.Role.SALES_AGENT and user.workstream != User.Workstream.AFTER_SALES


def _document_scope(user, queryset):
    """Which commercial documents a role may see.

    A marketer sees the documents they raised themselves — nothing wider. They
    previously also saw every document belonging to a customer in their scope,
    which quietly widened as customers were reassigned; Client-1 wants own-work
    scope, and "own" means the person who created the document.
    """
    if _sales_agent_in_scope(user):
        return queryset.filter(created_by=user)
    if user.role in ELEVATED_OPERATIONAL:
        return queryset
    return queryset.none()


def quotations_for(user):
    return _document_scope(user, Quotation.objects.all())


def orders_for(user):
    return _document_scope(user, Order.objects.all())


def invoices_for(user):
    return _document_scope(user, Invoice.objects.all())


def payments_for(user):
    """Money received is company data; an agent never sees it."""
    if user.role in ELEVATED_OPERATIONAL:
        return Payment.objects.all()
    return Payment.objects.none()


def cheques_for(user):
    if user.role in ELEVATED_OPERATIONAL:
        return Cheque.objects.all()
    return Cheque.objects.none()


def installment_plans_for(user):
    if user.role in ELEVATED_OPERATIONAL:
        return InstallmentPlan.objects.all()
    return InstallmentPlan.objects.none()


def installments_for(user):
    if user.role in ELEVATED_OPERATIONAL:
        return Installment.objects.all()
    return Installment.objects.none()


def ledger_entries_for(user):
    """Which ledger rows a role may read.

    بند ۶.۳ — «آیا بازاریاب باید مانده مشتریان خودش را ببیند؟» «بله».

    So a marketer is no longer refused the ledger outright. They are confined to
    **their own customers**, and by reusing `customers_for` rather than writing
    a second rule: a marketer's scope is own-entry and individual-only, and if
    that definition ever changes, the ledger follows it instead of drifting into
    a quietly wider view of who owes what.

    The scope is applied here, in the selector every reader goes through, not in
    the view — the list, the customer page and the export all come through this
    one queryset.
    """
    if user.role in ELEVATED_OPERATIONAL:
        return CustomerLedgerEntry.objects.all()
    if user.role == User.Role.SALES_AGENT:
        return CustomerLedgerEntry.objects.filter(customer__in=customers_for(user))
    return CustomerLedgerEntry.objects.none()
