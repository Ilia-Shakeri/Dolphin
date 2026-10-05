"""No number field is `type="number"` (2.40.14).

Every quantity, percentage, count, weight and order field is a text input with
the numeric keypad and `core/decimal.js` (`data-decimal-input`): Persian and
Arabic digits and «٫» are accepted, a whole number has no fraction, and the
range is checked with a Persian sentence (`data-decimal-min`/`-max`).
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest import skipUnless

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
JS_ROOT = ROOT / "common" / "static" / "common" / "js"
NODE = shutil.which("node")


def _templates():
    for root in (ROOT / "common" / "templates", ROOT / "profiles" / "templates"):
        for path in list(root.rglob("*.html")) + list(root.rglob("*.inc")):
            yield path, path.read_text(encoding="utf-8")


class NoNumberInputTests(SimpleTestCase):
    def test_no_template_has_a_number_input(self):
        for path, text in _templates():
            self.assertNotRegex(text, r'<input\b[^>]*type="number"', path.name)

    def test_no_script_builds_one(self):
        for path in JS_ROOT.rglob("*.js"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn('.type = "number"', text, path.name)
            self.assertNotIn('int: "number"', text, path.name)

    def test_every_decimal_field_says_how_many_places(self):
        for path, text in _templates():
            for tag in re.findall(r"<input\b[^>]*data-decimal-input[^>]*>", text):
                with self.subTest(template=path.name, tag=tag[:60]):
                    self.assertIn("data-decimal-places=", tag)
                    self.assertIn('inputmode="', tag)


@skipUnless(NODE, "node is not installed")
class NormaliseTests(SimpleTestCase):
    def test_persian_digits_and_separator_and_whole_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for relative in ("core/digits.js", "core/decimal.js"):
                target = tmp / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((JS_ROOT / relative).read_text(encoding="utf-8").replace('"dolphin/', f'"{tmp.as_uri()}/'), encoding="utf-8")
            probe = tmp / "probe.mjs"
            probe.write_text(
                f'import {{normalizeDecimal}} from "{(tmp / "core/decimal.js").as_uri()}";\n'
                'console.log(JSON.stringify([normalizeDecimal("۱۲٫۵"), normalizeDecimal("۱۲٫۵", 0), normalizeDecimal("1e3"), normalizeDecimal("٣٠")]));\n',
                encoding="utf-8",
            )
            out = subprocess.run([NODE, str(probe)], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), ["12.5", "12", "13", "30"])
