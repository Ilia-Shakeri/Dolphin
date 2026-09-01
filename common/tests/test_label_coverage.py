"""Every stored enum value must have a Persian name on screen.

The panel translates stored values with hand-written maps in
`dolphin-app.js`, and offers them as filter options in hand-written
`<option>` lists. Both are copies of an enum that lives in Python, and a copy
falls behind.

This has already cost this project twice at the database level, where a
hand-written list inside a `CheckConstraint` did not know about a newly added
enum member and the first row using it failed in production. The display copies
fail more quietly: `payment_made` was added to `CustomerLedgerEntry.EntryType`
in 1.2.1 and neither the label map nor the ledger filter learned about it, so a
real ledger row rendered the raw string `payment_made` in a Persian table and
could not be filtered for at all.

These tests read the source rather than the running page, so they need no
browser and no database, and they fail the moment an enum grows a member that
the panel cannot name.
"""

import pathlib
import re

from django.test import SimpleTestCase

from billing.models import (
    Cheque,
    CustomerLedgerEntry,
    Installment,
    Invoice,
    Order,
    Payment,
)
from inventory.models import StockMovement
from sales.models import Sale


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_JS = REPOSITORY_ROOT / "common" / "static" / "common" / "dolphin-app.js"
LEDGER_PAGE = (
    REPOSITORY_ROOT / "common" / "templates" / "common" / "reports" / "customer_ledger.html"
)
CHEQUE_PAGE = (
    REPOSITORY_ROOT / "common" / "templates" / "common" / "payments" / "cheques.html"
)


def js_map_keys(name):
    """The keys of a `const NAME = Object.freeze({...})` map in the panel script."""
    source = APP_JS.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = Object\.freeze\(\{{(.*?)\}}\);", source, re.S)
    assert match is not None, f"{name} not found in dolphin-app.js"
    return set(re.findall(r"^\s*([a-z_0-9]+)\s*:", match.group(1), re.M))


def option_values(path, select_id):
    """The `value=` of every option inside one `<select>` on a page."""
    source = path.read_text(encoding="utf-8")
    start = source.index(f'id="{select_id}"')
    end = source.index("</select>", start)
    return set(re.findall(r'<option value="([a-z_0-9]*)"', source[start:end]))


class LabelMapCoverageTests(SimpleTestCase):
    """Each map must name every value its enum can hold."""

    def assert_covers(self, map_name, values):
        missing = sorted(set(values) - js_map_keys(map_name))
        self.assertEqual(
            missing,
            [],
            f"{map_name} has no Persian name for {missing}, so the panel would "
            f"print the raw stored value in a Persian table.",
        )

    def test_ledger_entry_types(self):
        self.assert_covers("LEDGER_ENTRY_TEXT", CustomerLedgerEntry.EntryType.values)

    def test_cheque_statuses(self):
        self.assert_covers("CHEQUE_STATUS_TEXT", Cheque.Status.values)

    def test_payment_methods(self):
        self.assert_covers("PAYMENT_METHOD_TEXT", Payment.Method.values)

    def test_payment_statuses(self):
        self.assert_covers("PAYMENT_STATUS_TEXT", Payment.Status.values)

    def test_payment_directions(self):
        self.assert_covers("PAYMENT_DIRECTION_TEXT", Payment.Direction.values)

    def test_installment_statuses(self):
        self.assert_covers("INSTALLMENT_STATUS_TEXT", Installment.Status.values)

    def test_stock_movement_types(self):
        self.assert_covers("MOVEMENT_TEXT", StockMovement.MovementType.values)

    def test_settlement_statuses(self):
        self.assert_covers("SETTLEMENT_TEXT", Invoice.SettlementStatus.values)

    def test_document_statuses(self):
        """One map serves invoices, orders and campaign results."""
        self.assert_covers(
            "DOCUMENT_STATUS_TEXT",
            set(Invoice.Status.values)
            | set(Order.Status.values)
            | set(Sale.Status.values),
        )

    def test_every_label_is_actually_persian(self):
        """A key mapped to its own ASCII name would satisfy coverage and read wrong."""
        persian = re.compile(r"[؀-ۿ]")
        source = APP_JS.read_text(encoding="utf-8")
        for name in (
            "LEDGER_ENTRY_TEXT", "CHEQUE_STATUS_TEXT", "PAYMENT_METHOD_TEXT",
            "PAYMENT_STATUS_TEXT", "PAYMENT_DIRECTION_TEXT",
            "INSTALLMENT_STATUS_TEXT", "MOVEMENT_TEXT",
            "SETTLEMENT_TEXT", "DOCUMENT_STATUS_TEXT",
        ):
            match = re.search(rf"const {name} = Object\.freeze\(\{{(.*?)\}}\);", source, re.S)
            for key, label in re.findall(r'^\s*([a-z_0-9]+)\s*:\s*"([^"]*)"', match.group(1), re.M):
                with self.subTest(map=name, key=key):
                    self.assertTrue(persian.search(label), f"{name}.{key} = {label!r}")


class FilterOptionCoverageTests(SimpleTestCase):
    """A value a reader cannot filter for is a value they cannot find."""

    def test_the_ledger_offers_every_entry_type(self):
        offered = option_values(LEDGER_PAGE, "ledger-entry-type")
        missing = sorted(set(CustomerLedgerEntry.EntryType.values) - offered)
        self.assertEqual(missing, [], f"ledger filter cannot select {missing}")

    def test_the_cheque_page_offers_every_status(self):
        offered = option_values(CHEQUE_PAGE, "cheque-status-filter")
        missing = sorted(set(Cheque.Status.values) - offered)
        self.assertEqual(missing, [], f"cheque filter cannot select {missing}")

    def test_a_filter_offers_nothing_the_enum_cannot_hold(self):
        """A stale option returns an empty list and looks like missing data."""
        offered = option_values(LEDGER_PAGE, "ledger-entry-type") - {""}
        unknown = sorted(offered - set(CustomerLedgerEntry.EntryType.values))
        self.assertEqual(unknown, [], f"ledger filter offers unknown {unknown}")
