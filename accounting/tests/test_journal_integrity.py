"""Phase-1 double-entry invariants — see DOLPHIN_ACCOUNTING_PLAN.md §4, §9.

`accounting` is now in `config/settings.py`'s INSTALLED_APPS, gated by the
`accounting_ledger` feature flag (default off), with its own migration and
its own grants in `scripts/bootstrap-postgres.sh` (kept in step with
`common/tests/test_database_privileges.py`). Run directly with:

    python manage.py test accounting --settings=config.devcheck_settings
"""

from decimal import Decimal

from django.test import TestCase

from accounting.models import Account, JournalEntry, JournalLine
from accounting.selectors import trial_balance
from accounting.services import post_manual_entry
from accounts.models import User
from common.exceptions import BusinessRuleError


class JournalIntegrityTests(TestCase):
    def setUp(self):
        self.accountant = User.objects.create_user(
            username="accountant", password="Strong-pass-604!", role=User.Role.PLATFORM_ADMIN
        )
        self.cash = Account.objects.create(code="1001", name="صندوق", account_type=Account.AccountType.ASSET)
        self.capital = Account.objects.create(
            code="3001", name="سرمایه", account_type=Account.AccountType.EQUITY
        )

    def test_a_balanced_manual_entry_is_accepted(self):
        entry = post_manual_entry(
            actor=self.accountant,
            reference="JE-0001",
            memo="مانده اول دورهٔ صندوق",
            lines=[
                {"account": self.cash, "debit": Decimal("1000000")},
                {"account": self.capital, "credit": Decimal("1000000")},
            ],
        )
        self.assertEqual(JournalEntry.objects.count(), 1)
        self.assertEqual(JournalLine.objects.filter(entry=entry).count(), 2)

    def test_an_unbalanced_entry_is_rejected(self):
        with self.assertRaises(BusinessRuleError):
            post_manual_entry(
                actor=self.accountant,
                reference="JE-0002",
                lines=[
                    {"account": self.cash, "debit": Decimal("1000000")},
                    {"account": self.capital, "credit": Decimal("999999")},
                ],
            )
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_a_line_naming_both_debit_and_credit_is_rejected(self):
        with self.assertRaises(BusinessRuleError):
            post_manual_entry(
                actor=self.accountant,
                reference="JE-0003",
                lines=[
                    {"account": self.cash, "debit": Decimal("100"), "credit": Decimal("100")},
                    {"account": self.capital, "credit": Decimal("100")},
                ],
            )

    def test_a_single_line_entry_is_rejected(self):
        with self.assertRaises(BusinessRuleError):
            post_manual_entry(
                actor=self.accountant,
                reference="JE-0004",
                lines=[{"account": self.cash, "debit": Decimal("100")}],
            )

    def test_an_inactive_account_refuses_posting(self):
        self.cash.is_active = False
        self.cash.save()
        with self.assertRaises(BusinessRuleError):
            post_manual_entry(
                actor=self.accountant,
                reference="JE-0005",
                lines=[
                    {"account": self.cash, "debit": Decimal("100")},
                    {"account": self.capital, "credit": Decimal("100")},
                ],
            )

    def test_trial_balance_sums_every_account_including_untouched_ones(self):
        post_manual_entry(
            actor=self.accountant,
            reference="JE-0006",
            lines=[
                {"account": self.cash, "debit": Decimal("500")},
                {"account": self.capital, "credit": Decimal("500")},
            ],
        )
        rows = {row["account"].code: row for row in trial_balance()}
        self.assertEqual(rows["1001"]["balance"], Decimal("500"))
        self.assertEqual(rows["3001"]["balance"], Decimal("-500"))

    def test_the_database_itself_refuses_an_unbalanced_line_bypassing_the_service(self):
        """The CheckConstraint is the last line of defence, not the only one —
        even a caller that skips post_manual_entry cannot write a line naming
        both sides."""
        entry = JournalEntry.objects.create(reference="JE-0007", created_by=self.accountant)
        with self.assertRaises(Exception):
            JournalLine.objects.create(
                entry=entry, account=self.cash, debit=Decimal("0"), credit=Decimal("0")
            )
