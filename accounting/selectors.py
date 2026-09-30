"""Read-only queries — see DOLPHIN_ACCOUNTING_PLAN.md §4.3.

Trial balance only, in phase 1: it needs no accounting-policy decision at
all, since it is nothing but summing what post_manual_entry already
enforced is balanced. Balance Sheet and Profit & Loss are phase 4, gated
on the fiscal-period and event-mapping decisions in the plan's §6.
"""

from decimal import Decimal

from django.db.models import DecimalField, Sum
from django.db.models.functions import Coalesce

from accounting.models import Account

ZERO = Decimal("0.00")


def trial_balance():
    """One row per account: total debit, total credit, net balance.

    Every account is listed, even one with no lines yet (LEFT JOIN via
    `lines`), so a fresh chart of accounts is visibly complete rather than
    silently empty.
    """
    rows = Account.objects.order_by("code").annotate(
        total_debit=Coalesce(
            Sum("lines__debit"), ZERO, output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
        total_credit=Coalesce(
            Sum("lines__credit"), ZERO, output_field=DecimalField(max_digits=20, decimal_places=2)
        ),
    )
    return [
        {
            "account": account,
            "total_debit": account.total_debit,
            "total_credit": account.total_credit,
            "balance": account.total_debit - account.total_credit,
        }
        for account in rows
    ]
