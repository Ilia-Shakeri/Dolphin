"""Append-only customer ledger.

`append_ledger_entry` is the only writer. It locks the customer row first, so
two concurrent postings serialise and the `balance_after` chain stays a true
running balance rather than two entries computed from the same stale total.

`balance_after` records the balance in *posting* order. An entry may carry an
earlier `occurred_at` than the one before it — a payment received last week, an
opening balance from last year — so `current_balance` sums the entries instead
of reading the newest row's snapshot.

Nothing here ever updates or deletes an entry. Reversing an invoice or a payment
appends the opposite entry; the original stays visible forever.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce

from auditlog.services import log_activity
from billing.models import CustomerLedgerEntry
from billing.money import MAX_MONEY, quantize_money
from common.exceptions import BusinessRuleError
from sales.models import Customer


def current_balance(customer):
    """The balance the customer owes: positive is a receivable, negative a credit.

    Summed from every entry rather than read from the newest row's
    `balance_after`. `occurred_at` is a business date the caller supplies — a
    payment received last week, an opening balance carried in from last year —
    so the newest entry by that date is not necessarily the last one posted.
    Reading its `balance_after` silently dropped every back-dated entry from the
    balance: post an invoice today, then register a payment dated yesterday, and
    the customer still appeared to owe the full amount.

    Summing is order-independent and therefore correct whatever order entries
    arrive in. Nothing here writes: the ledger stays append-only.
    """
    totals = CustomerLedgerEntry.objects.filter(customer=customer).aggregate(
        debit=Coalesce(Sum("debit"), Decimal("0.00"), output_field=DecimalField(max_digits=38, decimal_places=2)),
        credit=Coalesce(Sum("credit"), Decimal("0.00"), output_field=DecimalField(max_digits=38, decimal_places=2)),
    )
    return quantize_money(totals["debit"] - totals["credit"])


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
        raise BusinessRuleError({"entry_type": "نوع سند دفتر نامعتبر است."})
    debit = quantize_money(debit or 0)
    credit = quantize_money(credit or 0)
    if (debit > 0) == (credit > 0):
        raise BusinessRuleError({"amount": "هر سند دفتر باید دقیقاً یکی از بدهکار یا بستانکار را داشته باشد."})
    if debit < 0 or credit < 0:
        raise BusinessRuleError({"amount": "مبلغ دفتر نمی‌تواند منفی باشد."})

    # Locking the customer serialises every posting for this account, which is
    # what makes the running balance correct under concurrency. `balance_after`
    # is therefore the account balance at the moment this entry was posted, in
    # posting order — not in `occurred_at` order, which a back-dated entry may
    # contradict. `current_balance` sums instead of reading this column, so the
    # account total never depends on that distinction.
    locked_customer = Customer.objects.select_for_update().get(pk=customer.pk)
    balance = current_balance(locked_customer) + debit - credit
    balance = quantize_money(balance)
    if abs(balance) > MAX_MONEY:
        raise BusinessRuleError({"amount": "مانده حاصل مشتری خارج از محدوده مجاز است."})

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
