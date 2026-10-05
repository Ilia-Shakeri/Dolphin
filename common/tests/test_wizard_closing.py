"""How a wizard may be closed: one set of rules for all of them.

Behaviour in a real browser is verified by hand and by the page-load test; these
pin the wiring that makes it system-wide, so a new wizard cannot quietly opt out.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase

from common.tests.panel_js import module_source

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "common"
PROFILE_TEMPLATES = Path(__file__).resolve().parents[2] / "profiles" / "templates"


def wizard_dialogs():
    for path in list(TEMPLATES.rglob("*.html")) + list(TEMPLATES.rglob("*.inc")):
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"<dialog\b.*?</dialog>", text, re.S):
            if "data-dolphin-stepper-element" in block:
                yield path.name, block


class WizardClosingTests(SimpleTestCase):
    def test_no_wizard_has_a_second_cancel_button_at_the_bottom(self):
        found = list(wizard_dialogs())
        self.assertGreaterEqual(len(found), 14)  # «ثبت فروش» removed in 2.39.20
        for name, block in found:
            with self.subTest(template=name):
                self.assertNotIn("data-close-dialog>انصراف", block)
                self.assertIn('aria-label="بستن"', block)

    def test_the_backdrop_never_closes_a_wizard(self):
        source = module_source("ui/dialogs.js")
        self.assertIn('dialog.querySelector(".stepper")', source)

    def test_every_wizard_gets_the_closing_rules_from_setup_wizard(self):
        """Since 2.40.10 the rules live in `ui/dialogs.js` (`guardDirtyDialog`)
        and every form dialog uses them; a wizard is one of those."""
        wizard = module_source("ui/wizard.js")
        self.assertIn("guardWizardClosing(dialog, form);", wizard)
        self.assertIn("guardDirtyDialog(dialog, form);", wizard)
        source = module_source("ui/dialogs.js")
        self.assertIn("تغییرات ذخیره نشده‌اند. آیا مطمئن هستید که می‌خواهید خارج شوید؟", source)
        self.assertIn('dialog.addEventListener("cancel"', source)
        self.assertIn('"beforeunload"', source)


def form_dialogs():
    """Every dialog that holds a form and is not a wizard."""
    for path in list(TEMPLATES.rglob("*.html")) + list(TEMPLATES.rglob("*.inc")) + list(PROFILE_TEMPLATES.rglob("*.inc")):
        text = path.read_text(encoding="utf-8")
        for block in re.findall(r"<dialog\b.*?</dialog>", text, re.S):
            if "data-dolphin-stepper-element" not in block and "<form" in block:
                yield path.name, block


class FormDialogClosingTests(SimpleTestCase):
    """2.40.10: the dialogs that are not wizards close by the same rules."""

    def test_no_form_dialog_has_a_second_cancel_beside_its_close(self):
        found = list(form_dialogs())
        self.assertGreaterEqual(len(found), 15)
        for name, block in found:
            with self.subTest(template=name):
                self.assertNotIn("data-close-dialog>انصراف<", block)

    def test_every_form_dialog_is_guarded_and_the_backdrop_asks_when_dirty(self):
        source = module_source("ui/dialogs.js")
        self.assertIn("if (form) guardDirtyDialog(dialog, form);", source)
        self.assertIn("if (dirtyDialogs.has(dialog)) {\n            closeIfConfirmed(dialog);", source)
        # Press and release both on the backdrop, never a drag out of a field.
        self.assertIn("if (pressStartedOn !== dialog) return;", source)
