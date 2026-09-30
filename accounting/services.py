"""Phase 1 posting service — see DOLPHIN_ACCOUNTING_PLAN.md §4.2.

Exactly one entry point in phase 1: a manual journal entry, for the case a
document this codebase already understands (an invoice, a payment, a
cheque) doesn't cover — an accountant recording an opening balance on a
bank account, for instance. Automatic posting from real billing events
(`post_invoice_issued` and its siblings) is phase 2, gated on the open
questions in the plan's §6 — writing them now would mean guessing which
account a real event debits or credits, exactly what CLAUDE.md §31 forbids.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounting.models import Account, JournalEntry, JournalLine
from common.exceptions import BusinessRuleError

ZERO = Decimal("0.00")


def _clean_lines(lines):
    """Validate a raw line list and return the values ready to save.

    Mirrors billing.services._build_lines' shape (validate the whole list
    up front, raise one BusinessRuleError naming the bad index) rather than
    inventing a new validation style for this app.
    """
    if not isinstance(lines, (list, tuple)) or len(lines) < 2:
        raise BusinessRuleError({"lines": "یک سند حسابداری حداقل دو ردیف نیاز دارد."})

    prepared = []
    total_debit = ZERO
    total_credit = ZERO
    for index, raw in enumerate(lines, start=1):
        if not isinstance(raw, dict):
            raise BusinessRuleError({"lines": f"ردیف {index}: باید یک شیء باشد."})
        account = raw.get("account")
        if not isinstance(account, Account):
            raise BusinessRuleError({"lines": f"ردیف {index}: انتخاب حساب الزامی است."})
        if not account.is_active:
            raise BusinessRuleError({"lines": f"ردیف {index}: حساب «{account.code}» غیرفعال است."})
        if not account.allow_manual_posting:
            raise BusinessRuleError({
                "lines": f"ردیف {index}: حساب «{account.code}» ثبت دستی را نمی‌پذیرد."
            })
        debit = Decimal(raw.get("debit") or 0)
        credit = Decimal(raw.get("credit") or 0)
        if (debit > 0) == (credit > 0):
            raise BusinessRuleError({
                "lines": f"ردیف {index}: دقیقاً یکی از دو مقدار بدهکار/بستانکار باید مثبت باشد."
            })
        total_debit += debit
        total_credit += credit
        prepared.append({
            "account": account,
            "debit": debit,
            "credit": credit,
            "description": str(raw.get("description") or ""),
        })

    if total_debit != total_credit:
        raise BusinessRuleError({
            "lines": f"سند متوازن نیست: جمع بدهکار {total_debit} با جمع بستانکار {total_credit} برابر نیست."
        })
    return prepared


@transaction.atomic
def post_manual_entry(*, actor, reference, entry_date=None, memo="", lines):
    """Record one balanced manual journal entry.

    The atomic block is the same discipline `billing.services._create_document`
    already follows: the header and every line are written together, or none
    of them are — a half-posted journal entry is a worse failure than a
    rejected one.
    """
    prepared = _clean_lines(lines)
    entry = JournalEntry.objects.create(
        reference=reference,
        entry_date=entry_date or timezone.now(),
        memo=memo,
        created_by=actor,
    )
    JournalLine.objects.bulk_create([
        JournalLine(entry=entry, **line) for line in prepared
    ])
    return entry
