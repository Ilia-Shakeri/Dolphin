from django.db import transaction
from django.utils import timezone

from accounts.access import crm_identities, is_crm_identity
from accounts.models import User
from aftersales.models import AfterSalesHistory, AfterSalesRequest
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.models import Customer, Sale, SalesDocument


ELEVATED = {User.Role.SALES_MANAGER, User.Role.COMPANY_IT, User.Role.PLATFORM_ADMIN}


def _clean(value, *, field, limit):
    value = value.strip() if isinstance(value, str) else ""
    if not value:
        raise BusinessRuleError({field: "This field is required."})
    if any(character in value for character in "\r\n\t") and field in {"subject", "status", "to_status"}:
        raise BusinessRuleError({field: "Use a single-line value."})
    if len(value) > limit:
        raise BusinessRuleError({field: f"Ensure this field has no more than {limit} characters."})
    return value


def _lock_actor(actor):
    actor = User.objects.select_for_update().filter(pk=getattr(actor, "pk", None), is_active=True).first()
    if actor is None or not is_crm_identity(actor):
        raise BusinessPermissionDenied("Active CRM user is required.")
    return actor


def _lock_eligible_operator(user):
    if user is None:
        return None
    operator = crm_identities(User.objects.select_for_update().filter(
        pk=user.pk, is_active=True, role=User.Role.SALES_AGENT,
        workstream=User.Workstream.AFTER_SALES,
    )).first()
    if operator is None:
        raise BusinessRuleError({"assigned_to": "Select an active after-sales operator."})
    return operator


@transaction.atomic
def create_after_sales_request(*, actor, customer, subject, description, status, sale=None, document=None, assigned_to=None):
    actor = _lock_actor(actor)
    if actor.role not in ELEVATED:
        raise BusinessPermissionDenied("After-sales request creation is not allowed.")
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    sale = Sale.objects.select_for_update().get(pk=sale.pk) if sale is not None else None
    document = SalesDocument.objects.select_for_update().get(pk=document.pk) if document is not None else None
    if sale is not None and sale.customer_id != customer.pk:
        raise BusinessRuleError({"sale": "Sale must belong to the selected customer."})
    if document is not None and document.customer_id != customer.pk:
        raise BusinessRuleError({"document": "Document must belong to the selected customer."})
    assigned_to = _lock_eligible_operator(assigned_to)
    item = AfterSalesRequest.objects.create(
        customer=customer, sale=sale, document=document,
        subject=_clean(subject, field="subject", limit=200),
        description=_clean(description, field="description", limit=4000),
        status=_clean(status, field="status", limit=80),
        assigned_to=assigned_to, created_by=actor,
    )
    AfterSalesHistory.objects.create(request=item, event=AfterSalesHistory.Event.CREATED, actor=actor, to_status=item.status, to_user=assigned_to)
    log_activity(actor=actor, operation="after_sales.created", instance=item, changes={"fields": ["customer", "sale", "document", "status", "assigned_to"]})
    return item


@transaction.atomic
def assign_after_sales_request(*, actor, request, to_user, reason=""):
    actor = _lock_actor(actor)
    if actor.role not in ELEVATED:
        raise BusinessPermissionDenied("After-sales assignment is not allowed.")
    item = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if item.closed_at is not None:
        raise BusinessConflictError({"closed_at": "Closed request cannot be reassigned."})
    to_user = _lock_eligible_operator(to_user)
    if item.assigned_to_id == to_user.pk:
        raise BusinessConflictError({"to_user": "Request is already assigned to this operator."})
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) > 500:
        raise BusinessRuleError({"reason": "Ensure this field has no more than 500 characters."})
    previous = item.assigned_to
    item.assigned_to = to_user
    item.save(update_fields=["assigned_to", "updated_at"])
    AfterSalesHistory.objects.create(request=item, event=AfterSalesHistory.Event.ASSIGNED, actor=actor, from_user=previous, to_user=to_user, reason=reason)
    log_activity(actor=actor, operation="after_sales.assigned", instance=item, changes={"from_user": getattr(previous, "pk", None), "to_user": to_user.pk, "reason_provided": bool(reason)})
    return item


@transaction.atomic
def transition_after_sales_status(*, actor, request, to_status, reason=""):
    actor = _lock_actor(actor)
    item = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if actor.role not in ELEVATED and not (
        actor.role == User.Role.SALES_AGENT and actor.workstream == User.Workstream.AFTER_SALES and item.assigned_to_id == actor.pk
    ):
        raise BusinessPermissionDenied("After-sales status transition is not allowed.")
    if item.closed_at is not None:
        raise BusinessConflictError({"closed_at": "Closed request cannot change status."})
    to_status = _clean(to_status, field="to_status", limit=80)
    if item.status == to_status:
        raise BusinessConflictError({"to_status": "Status is already set to this value."})
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) > 500:
        raise BusinessRuleError({"reason": "Ensure this field has no more than 500 characters."})
    previous = item.status
    item.status = to_status
    item.save(update_fields=["status", "updated_at"])
    AfterSalesHistory.objects.create(request=item, event=AfterSalesHistory.Event.STATUS_CHANGED, actor=actor, from_status=previous, to_status=to_status, reason=reason)
    log_activity(actor=actor, operation="after_sales.status_changed", instance=item, changes={"case_from": previous, "case_to": to_status, "reason_provided": bool(reason)})
    return item


@transaction.atomic
def close_after_sales_request(*, actor, request, reason=""):
    actor = _lock_actor(actor)
    if actor.role not in ELEVATED:
        raise BusinessPermissionDenied("After-sales close is not allowed.")
    item = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if item.closed_at is not None:
        raise BusinessConflictError({"closed_at": "Request is already closed."})
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) > 500:
        raise BusinessRuleError({"reason": "Ensure this field has no more than 500 characters."})
    item.closed_at = timezone.now()
    item.save(update_fields=["closed_at", "updated_at"])
    AfterSalesHistory.objects.create(request=item, event=AfterSalesHistory.Event.CLOSED, actor=actor, from_status=item.status, to_status=item.status, reason=reason)
    log_activity(actor=actor, operation="after_sales.closed", instance=item, changes={"reason_provided": bool(reason)})
    return item
