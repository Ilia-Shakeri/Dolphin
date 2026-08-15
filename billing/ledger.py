"""Append-only customer ledger.

`append_ledger_entry` is the only writer. It locks the customer row first, so
two concurrent postings serialise and the `balance_after` chain stays a true
running balance rather than two entries computed from the same stale total.

Nothing here ever updates or deletes an entry. Reversing an invoice or a payment
appends the opposite entry; the original stays visible forever.
"""

from decimal import Decimal

from django.db import transaction

from auditlog.services import log_activity
from billing.models import CustomerLedgerEntry
from billing.money import MAX_MONEY, quantize_money
from common.exceptions import BusinessRuleError
from sales.models import Customer


def current_balance(customer):
    """The balance the customer owes: positive is a receivable, negative a credit."""
    latest = (
        CustomerLedgerEntry.objects.filter(customer=customer)
        .order_by("-occurred_at", "-id")
        .values_list("balance_after", flat=True)
        .first()
    )
    return latest if latest is not None else Decimal("0.00")


@transaction.atomic
def append_ledger_entry(
    *,
    actor,
    customer,
    entry_type,
    debit=Decimal("0.00"),
    credit=Decimal("0.00"),
    occurred_at,
    reference_kind=CustomerLedgerEntry.ReferenceKind.NONE,
    reference_id=None,
    reference_number="",
    notes="",
):
    if entry_type not in CustomerLedgerEntry.EntryType.values:
        raise BusinessRuleError({"entry_type": "Unknown ledger entry type."})
    debit = quantize_money(debit or 0)
    credit = quantize_money(credit or 0)
    if (debit > 0) == (credit > 0):
        raise BusinessRuleError({"amount": "A ledger entry carries exactly one of debit or credit."})
    if debit < 0 or credit < 0:
        raise BusinessRuleError({"amount": "A ledger amount cannot be negative."})

    # Locking the customer serialises every posting for this account, which is
    # what makes the running balance correct under concurrency.
    locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
    balance = current_balance(locked_customer) + debit - credit
    balance = quantize_money(balance)
    if abs(balance) > MAX_MONEY:
        raise BusinessRuleError({"amount": "Resulting customer balance is out of range."})

    entry = CustomerLedgerEntry.objects.create(
        customer=locked_customer,
        entry_type=entry_type,
        debit=debit,
        credit=credit,
        balance_after=balance,
        reference_kind=reference_kind,
        reference_id=reference_id,
        reference_number=reference_number,
        occurred_at=occurred_at,
        created_by=actor,
        notes=notes,
    )
    log_activity(
        actor=actor,
        operation="customer_ledger.appended",
        instance=entry,
        changes={
            "customer": locked_customer.pk,
            "entry_type": entry_type,
            "amount": str(debit if debit > 0 else credit),
            "balance_after": str(balance),
        },
    )
    return entry
