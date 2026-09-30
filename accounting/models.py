"""Phase 1 of the general ledger — see DOLPHIN_ACCOUNTING_PLAN.md §4.1.

Deliberately minimal and policy-neutral: three models that encode the
mathematical rule of double-entry bookkeeping (a journal entry balances,
a line is a debit or a credit but never both) and nothing about what any
real Dolphin business event should post. No accounting, tax, or legal rule
from CLAUDE.md §31's forbidden list is invented here — see the plan
document for the open questions that gate phase 2 (automatic posting from
billing events).

Wired into INSTALLED_APPS behind the `accounting_ledger` feature flag
(default off — DOLPHIN_ACCOUNTING_PLAN.md §7), migrated
(`accounting/migrations/0001_initial.py`), and covered by
`accounting/tests/test_journal_integrity.py`.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from common.models import TimeStampedModel


class Account(TimeStampedModel):
    """One row of the chart of accounts (کدینگ حساب‌ها).

    The five-way split (asset/liability/equity/income/expense) is the one
    piece of structure every double-entry system needs regardless of which
    coding standard a deployment's accountant eventually picks for `code` —
    see DOLPHIN_ACCOUNTING_PLAN.md §6.1 for that still-open decision.
    """

    class AccountType(models.TextChoices):
        ASSET = "asset", "دارایی"
        LIABILITY = "liability", "بدهی"
        EQUITY = "equity", "حقوق صاحبان سهام"
        INCOME = "income", "درآمد"
        EXPENSE = "expense", "هزینه"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, db_index=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    is_active = models.BooleanField(default=True)
    #: Whether a human may post a manual JournalEntry line directly against
    #: this account. A control account meant to be touched only by an
    #: automatic posting service (phase 2, not built yet) would have this
    #: off — but nothing in this phase turns it off anywhere, since nothing
    #: posts automatically yet either.
    allow_manual_posting = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(condition=Q(code__regex=r"\S"), name="account_code_nonblank"),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class JournalEntry(TimeStampedModel):
    """One accounting document — always balanced, always append-only.

    Nothing here is ever updated after creation except by the ordinary
    TimeStampedModel `updated_at` bookkeeping; a correction is a new,
    reversing JournalEntry, the same append-only convention
    `billing.models.CustomerLedgerEntry` already uses.
    """

    reference = models.CharField(max_length=64, unique=True)
    entry_date = models.DateTimeField(db_index=True, default=timezone.now)
    memo = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="journal_entries"
    )
    # Phase 2 will add a link back to the billing document that caused this
    # entry (invoice/payment/cheque) once DOLPHIN_ACCOUNTING_PLAN.md §6's
    # event-to-account mapping is answered. Deliberately absent here: a
    # foreign key to a specific document type would commit to an answer for
    # §6.2 this phase has no business guessing.

    class Meta:
        ordering = ["-entry_date", "-id"]

    def __str__(self):
        return self.reference


class JournalLine(TimeStampedModel):
    """One debit or credit row inside a JournalEntry.

    The CheckConstraint below is the one rule that is *always* true for
    double-entry bookkeeping, independent of any business policy: a line
    moves money on exactly one side. It is not a substitute for the
    entry-level balance check (Σdebit == Σcredit across a whole
    JournalEntry), which is application logic in accounting/services.py,
    not something a single row's constraint can express.
    """

    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["entry_id", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(debit__gt=0) & Q(credit=0)) | (Q(credit__gt=0) & Q(debit=0)),
                name="journal_line_exactly_one_side",
            ),
        ]

    def __str__(self):
        side = "بدهکار" if self.debit else "بستانکار"
        amount = self.debit or self.credit
        return f"{self.account.code} {side} {amount}"
