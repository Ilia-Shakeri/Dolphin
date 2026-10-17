from django.db import transaction
from django.utils import timezone

from accounts.access import crm_identities, has_any_capability, is_crm_identity
from accounts.models import User
from aftersales.models import AfterSalesHistory, AfterSalesRequest
from auditlog.services import log_activity
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from sales.models import Customer, Sale, SalesDocument


def _clean(value, *, field, limit):
    value = value.strip() if isinstance(value, str) else ""
    if not value:
        raise BusinessRuleError({field: "این فیلد الزامی است."})
    if any(character in value for character in "\r\n\t") and field in {"subject", "status", "to_status"}:
        raise BusinessRuleError({field: "این مقدار باید تک‌خطی باشد."})
    if len(value) > limit:
        raise BusinessRuleError({field: f"این فیلد نباید بیش از {limit} نویسه داشته باشد."})
    return value


def _lock_actor(actor):
    actor = User.objects.select_for_update().filter(pk=getattr(actor, "pk", None), is_active=True).first()
    if actor is None or not is_crm_identity(actor):
        raise BusinessPermissionDenied("کاربر فعال سامانه لازم است.")
    return actor


def _lock_eligible_operator(user):
    if user is None:
        return None
    operator = crm_identities(User.objects.select_for_update().filter(
        pk=user.pk, is_active=True, role=User.Role.SALES_AGENT,
        workstream=User.Workstream.AFTER_SALES,
    )).first()
    if operator is None:
        raise BusinessRuleError({"assigned_to": "یک کارشناس فعال خدمات پس از فروش را انتخاب کنید."})
    return operator


@transaction.atomic
def create_after_sales_request(
    *, actor, customer, subject, description, status=None, sale=None, document=None, assigned_to=None,
    case_type=None, priority=None, stage=None,
):
    """Open a case (2.40.60, BIZ-008): a type, a priority (the type's own by
    default) and a starting stage (the list's first open one by default);
    the deadlines follow. `status` is the words a client sent before stages
    existed: used only to find the nearest stage when no stage is named."""
    from aftersales import workflow

    actor = _lock_actor(actor)
    if not has_any_capability(actor, "after_sales.manage"):
        raise BusinessPermissionDenied("ثبت درخواست خدمات پس از فروش مجاز نیست.")
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    sale = Sale.objects.select_for_update().get(pk=sale.pk) if sale is not None else None
    document = SalesDocument.objects.select_for_update().get(pk=document.pk) if document is not None else None
    if sale is not None and sale.customer_id != customer.pk:
        raise BusinessRuleError({"sale": "فروش باید متعلق به مشتری انتخاب‌شده باشد."})
    if document is not None and document.customer_id != customer.pk:
        raise BusinessRuleError({"document": "سند باید متعلق به مشتری انتخاب‌شده باشد."})
    assigned_to = _lock_eligible_operator(assigned_to)
    workflow.ensure_defaults()
    if case_type is not None and not case_type.is_active:
        raise BusinessRuleError({"case_type": "این نوع پرونده خاموش است."})
    priority = priority or (case_type.default_priority if case_type else "normal")
    if priority not in workflow.PRIORITY_LABELS:
        raise BusinessRuleError({"priority": "اولویت باید عادی، فوری یا بحرانی باشد."})
    if stage:
        start = workflow.resolve_stage(case_type, stage)
    elif status:
        words = _clean(status, field="status", limit=80)
        known = {item.key: item for item in workflow.stages_for(case_type)}
        start = next((item for item in known.values() if words in (item.key, item.label)), None)
        start = start or known.get(workflow.nearest_stage(words))
    else:
        start = workflow.first_open(case_type)
    if start is None or start.kind != "open" or not start.is_active:
        raise BusinessRuleError({"stage": "پرونده از یکی از مرحله‌های باز شروع می‌شود."})
    item = AfterSalesRequest.objects.create(
        customer=customer, sale=sale, document=document,
        subject=_clean(subject, field="subject", limit=200),
        description=_clean(description, field="description", limit=4000),
        status=start.label, stage=start.key, case_type=case_type, priority=priority,
        assigned_to=assigned_to, created_by=actor,
    )
    workflow.set_deadlines(item)
    item.save(update_fields=["response_due", "plan_due", "resolution_due"])
    AfterSalesHistory.objects.create(request=item, event=AfterSalesHistory.Event.CREATED, actor=actor, to_status=item.status, to_user=assigned_to)
    log_activity(actor=actor, operation="after_sales.created", instance=item, changes={"fields": ["customer", "sale", "document", "status", "assigned_to"]})
    return item


@transaction.atomic
def assign_after_sales_request(*, actor, request, to_user, reason=""):
    actor = _lock_actor(actor)
    if not has_any_capability(actor, "after_sales.manage"):
        raise BusinessPermissionDenied("واگذاری درخواست خدمات پس از فروش مجاز نیست.")
    item = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if item.closed_at is not None:
        raise BusinessConflictError({"closed_at": "درخواست بسته‌شده قابل واگذاری مجدد نیست."})
    to_user = _lock_eligible_operator(to_user)
    if item.assigned_to_id == to_user.pk:
        raise BusinessConflictError({"to_user": "این درخواست قبلاً به این کارشناس واگذار شده است."})
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) > 500:
        raise BusinessRuleError({"reason": "این فیلد نباید بیش از ۵۰۰ نویسه داشته باشد."})
    previous = item.assigned_to
    item.assigned_to = to_user
    item.save(update_fields=["assigned_to", "updated_at"])
    AfterSalesHistory.objects.create(request=item, event=AfterSalesHistory.Event.ASSIGNED, actor=actor, from_user=previous, to_user=to_user, reason=reason)
    log_activity(actor=actor, operation="after_sales.assigned", instance=item, changes={"from_user": getattr(previous, "pk", None), "to_user": to_user.pk, "reason_provided": bool(reason)})
    return item


def transition_after_sales_status(*, actor, request, to_status, reason=""):
    """Move a case to another stage of its list (2.40.60): `to_status` is the
    stage's key or name; the free words of before are no longer taken."""
    from aftersales import workflow

    return workflow.set_stage(actor=actor, request=request, to_stage=to_status, reason=reason)


@transaction.atomic
def schedule_after_sales_appointment(*, actor, request, appointment_at=None, reason=""):
    """Set or clear the case's next appointment — the after-sales side of
    the follow-up calendar (DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §7 phase E).

    Same permission shape as `transition_after_sales_status`: an elevated
    role, or the after-sales-workstream agent this specific case is assigned
    to — never any other agent, and never an unassigned case for an agent.
    `appointment_at=None` clears a previously scheduled appointment rather
    than being refused, since "no appointment" is this field's own null
    state, not an error.
    """
    actor = _lock_actor(actor)
    item = AfterSalesRequest.objects.select_for_update().get(pk=request.pk)
    if not has_any_capability(actor, "after_sales.manage") and not (
        actor.role == User.Role.SALES_AGENT and actor.workstream == User.Workstream.AFTER_SALES and item.assigned_to_id == actor.pk
    ):
        raise BusinessPermissionDenied("زمان‌بندی قرار خدمات پس از فروش مجاز نیست.")
    if item.closed_at is not None:
        raise BusinessConflictError({"closed_at": "درخواست بسته‌شده قابل زمان‌بندی نیست."})
    reason = reason.strip() if isinstance(reason, str) else ""
    if len(reason) > 500:
        raise BusinessRuleError({"reason": "این فیلد نباید بیش از ۵۰۰ نویسه داشته باشد."})
    if item.next_appointment_at == appointment_at:
        raise BusinessConflictError({"appointment_at": "زمان قرار هم‌اکنون همین مقدار است."})
    item.next_appointment_at = appointment_at
    fields = ["next_appointment_at", "updated_at"]
    if item.responded_at is None:
        # Booking a visit answers the customer (2.40.60): the first response.
        item.responded_at = timezone.now()
        fields.append("responded_at")
    item.save(update_fields=fields)
    AfterSalesHistory.objects.create(
        request=item, event=AfterSalesHistory.Event.APPOINTMENT_SCHEDULED, actor=actor,
        appointment_at=appointment_at, reason=reason,
    )
    log_activity(
        actor=actor, operation="after_sales.appointment_scheduled", instance=item,
        changes={"next_appointment_at": appointment_at.isoformat() if appointment_at else None, "reason_provided": bool(reason)},
    )
    return item


def close_after_sales_request(*, actor, request, reason="", final_result=""):
    """Close a case with its final result (2.40.60): «حل‌شده»، «حل‌نشده» or
    «مختومه با توافق مشتری» — required."""
    from aftersales import workflow

    return workflow.close(actor=actor, request=request, final_result=final_result, reason=reason)
