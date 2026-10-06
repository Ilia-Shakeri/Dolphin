"""Bulk selection stays true after a live refresh (2.40.11).

A live update redraws a list's rows in place and keeps the reader's choice;
a chosen row that disappeared in that redraw (deleted or moved by someone
else) must drop out of the choice, so the count and «حذف موارد انتخاب‌شده»
never name a row the reader cannot see. Every bulk delete button carries
the trash icon and still asks first.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
LISTS = (ROOT / "common" / "static" / "common" / "js" / "ui" / "lists.js").read_text(encoding="utf-8")
TEMPLATES = ROOT / "common" / "templates" / "common"


class LiveRefreshSelectionTests(SimpleTestCase):
    def test_a_quiet_redraw_drops_rows_that_are_gone(self):
        self.assertIn("if (quiet) selection.keepOnlyShown();", LISTS)
        body = LISTS.split("function keepOnlyShown() {")[1].split("\n    }\n")[0]
        self.assertIn("selected = new Set(Array.from(selected).filter((id) => shown.has(id)));", body)
        self.assertIn("updateToolbar();", body)

    def test_a_list_without_selection_still_answers(self):
        self.assertIn("resetSelection() {}, keepOnlyShown() {}", LISTS)

    def test_bulk_delete_still_asks_first(self):
        self.assertIn("if (!await confirmDialog(", LISTS)


class TrashIconTests(SimpleTestCase):
    def test_every_bulk_delete_button_has_the_trash_icon(self):
        buttons = []
        # Since 2.40.33 the icon alone, a red trash button, named for assistive
        # tech and as its tooltip (`btn-trash`); fifteen lists with the campaigns
        # and their members.
        for path in TEMPLATES.rglob("*.html"):
            buttons += re.findall(r'(<button[^>]*select="delete_selected"[^>]*>)(.*?)</button>', path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(buttons), 15)
        for tag, inner in buttons:
            self.assertIn("btn-trash", tag)
            self.assertIn('aria-label="حذف موارد انتخاب‌شده"', tag)
            self.assertIn('class="di-duotone di-trash fs-3" aria-hidden="true"', inner)
