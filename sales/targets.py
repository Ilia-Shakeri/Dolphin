"""Setting marketers' monthly sales targets (2.40.41).

The figures a target is measured against are read in `reports.targets`; this
module only writes the targets themselves. Who may set them is the
`sales_targets.manage` capability (a Sales Manager and the Platform Admin by
default, grantable per user on the permission matrix).
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction

from accounts.access import has_any_capability
from auditlog.services import log_activity
from common import jalali
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from sales.models import SalesTarget

#: The largest target the field can hold (20 digits, 2 of them decimals).
MAX_TARGET = Decimal("999999999999999999.99")


def clean_month(year, month):
    """`(year, month)` as a real Jalali month, or a Persian field error."""
    try:
        year, month = int(year), int(month)
        jalali.from_jalali(year, month, 1)
    except (TypeError, ValueError) as exc:
        raise BusinessRuleError({"month": "ماه انتخاب‌شده معتبر نیست."}) from exc
    return year, month


def _amount(value):
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BusinessRuleError({"targets": "مبلغ هدف معتبر نیست."}) from exc
    if not amount.is_finite() or amount < 0 or amount > MAX_TARGET:
        raise BusinessRuleError({"targets": "مبلغ هدف معتبر نیست."})
    amount = amount.quantize(Decimal("0.01"))
    return amount if amount > 0 else None


@transaction.atomic
def set_monthly_targets(*, actor, year, month, targets, marketers):
    """Write one month's targets.

    `targets` is `[{user_id, amount}]`; an empty or zero amount clears that
    marketer's target. `marketers` is the queryset of users a target may be
    set for — anyone else is refused. Returns how many targets were set,
    changed or cleared.
    """
    if not has_any_capability(actor, "sales_targets.manage"):
        raise BusinessPermissionDenied("تعیین هدف فروش مجاز نیست.")
    year, month = clean_month(year, month)
    wanted = {}
    for entry in targets:
        user_id = entry.get("user_id")
        if user_id in wanted:
            raise BusinessRuleError({"targets": "هر بازاریاب فقط یک‌بار می‌تواند در فهرست باشد."})
        wanted[user_id] = _amount(entry.get("amount"))
    allowed = set(marketers.filter(pk__in=list(wanted)).values_list("pk", flat=True))
    if set(wanted) - allowed:
        raise BusinessRuleError({"targets": "هدف فقط برای بازاریاب‌های فعال تعیین می‌شود."})
    existing = {
        target.user_id: target
        for target in SalesTarget.objects.select_for_update().filter(year=year, month=month, user_id__in=list(wanted))
    }
    changed = 0
    for user_id, amount in wanted.items():
        current = existing.get(user_id)
        if amount is None:
            if current is not None:
                log_activity(actor=actor, operation="sales_target.cleared", instance=current,
                             changes={"fields": ["amount"], "to_user": user_id})
                current.delete()
                changed += 1
            continue
        if current is None:
            current = SalesTarget.objects.create(user_id=user_id, year=year, month=month, amount=amount, set_by=actor)
        elif current.amount != amount:
            current.amount = amount
            current.set_by = actor
            current.save(update_fields=["amount", "set_by", "updated_at"])
        else:
            continue
        log_activity(actor=actor, operation="sales_target.set", instance=current,
                     changes={"fields": ["amount"], "to_user": user_id})
        changed += 1
    return changed
