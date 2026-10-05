"""Settings → «نمایش پنل» (2.40.6): bold headings, a large currency toggle.

The currency choice moved from two small radios to the shared segmented
toggle; the field name, what the save sends and the rial note are unchanged.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from accounts.models import User

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "common" / "templates" / "common" / "settings" / "settings.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "common" / "static" / "common" / "js" / "features" / "settings" / "settings-page.js").read_text(encoding="utf-8")
HEADING = "form-label fw-bold fs-6 d-block mb-3"


def _display_tab():
    start = TEMPLATE.index("<h2>نمایش پنل</h2>")
    return TEMPLATE[start:TEMPLATE.index('id="preferences-saved"', start)]


class HeadingTests(SimpleTestCase):
    def test_every_option_heading_is_bold_and_the_same_size(self):
        tab = _display_tab()
        for title in ("قلم پنل", "اندازهٔ قلم", "واحد پول", "حالت رنگی"):
            with self.subTest(title=title):
                self.assertRegex(tab, rf'class="{HEADING}"[^>]*>{title}<')
        self.assertNotIn("form-label fw-semibold d-block", tab)


class CurrencyToggleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="display.reader", password="Strong-pass-661!", role=User.Role.SALES_AGENT)
        self.client.force_login(self.user)

    def test_the_toggle_writes_the_same_field(self):
        page = self.client.get("/settings/").content.decode("utf-8")
        self.assertRegex(page, r'<input type="hidden" id="preference-currency-unit" name="currency_unit" value="(rial|toman)">')
        self.assertIn('class="dolphin-segmented dolphin-segmented-lg" role="radiogroup" aria-labelledby="preference-currency-label" data-segmented-for="preference-currency-unit"', page)
        self.assertEqual(len(re.findall(r'role="radio" class="dolphin-segmented-option[^"]*"', page)), 2)
        self.assertEqual(page.count('aria-checked="true" data-value="'), 1)

    def test_the_save_still_sends_currency_unit(self):
        self.assertIn('currency_unit: data.get("currency_unit"),', SCRIPT)

    def test_the_rial_note_stays(self):
        self.assertIn("همهٔ مبلغ‌ها در پایگاه داده به ریال ذخیره می‌شوند", _display_tab())
