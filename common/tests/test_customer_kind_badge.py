"""«حقیقی» / «حقوقی» always come with their icon, from one helper (2.40.8).

The words live in one label table per side — `sales.models.Customer.Kind`
(read by `{% customer_kind %}`) and `ui/customer-kind.js` — and every served
template and module shows a kind through them. Where an icon cannot go (a
native `<option>`) the template takes the word from the same table. Excel
exports keep plain words.
"""

import re
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
WORDS = ("حقیقی", "حقوقی")
#: Not a customer's kind: the official invoice's field names a party
#: «شخص حقیقی/حقوقی», and two sentences use «حقوقی» as "legal" (a legal
#: meaning, a legal buyer's economic code) rather than as a kind label.
ALLOWED = {
    "common/templates/common/invoices/print.html",
    "common/templates/common/reports/receivables.html",
    "common/static/common/js/features/billing/invoice-detail.js",
    "common/static/common/js/ui/customer-kind.js",
}


def _without_comments(text, suffix):
    if suffix == ".html" or suffix == ".inc":
        text = re.sub(r"{% comment %}.*?{% endcomment %}", "", text, flags=re.S)
        return re.sub(r"{#.*?#}", "", text, flags=re.S)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(^|[^:])//.*$", r"\1", text, flags=re.M)


class OneHelperTests(SimpleTestCase):
    def test_no_template_or_module_spells_the_kind_itself(self):
        offenders = []
        roots = [ROOT / "common" / "templates", ROOT / "profiles" / "templates", ROOT / "common" / "static" / "common" / "js"]
        for root in roots:
            for path in root.rglob("*"):
                if path.suffix not in {".html", ".inc", ".js"}:
                    continue
                relative = path.relative_to(ROOT).as_posix()
                if relative in ALLOWED:
                    continue
                text = _without_comments(path.read_text(encoding="utf-8"), path.suffix)
                if any(word in text for word in WORDS):
                    offenders.append(relative)
        self.assertEqual(offenders, [])

    def test_the_tag_draws_icon_and_word(self):
        html = Template('{% load customer_kind_tags %}{% customer_kind "legal" %}|{% customer_kind_label "individual" %}').render(Context())
        badge, label = html.split("|")
        self.assertIn('class="customer-kind"', badge)
        self.assertIn('class="di-duotone di-bank customer-kind-icon" aria-hidden="true"', badge)
        self.assertIn("<span>حقوقی</span>", badge)
        self.assertEqual(label, "حقیقی")
        self.assertEqual(Template('{% load customer_kind_tags %}{% customer_kind "nope" %}').render(Context()), "")

    def test_the_two_tables_agree(self):
        from common.templatetags.customer_kind_tags import ICONS
        from sales.models import Customer

        script = (ROOT / "common" / "static" / "common" / "js" / "ui" / "customer-kind.js").read_text(encoding="utf-8")
        for kind, label in Customer.Kind.choices:
            icon, paths = ICONS[kind]
            self.assertIn(f'{kind}: {{label: "{label}", icon: "{icon}", paths: {paths}}}', script)

    def test_the_icon_is_one_em_in_the_text_colour(self):
        rule = CSS.split(".customer-kind-icon {")[1].split("}")[0]
        for declaration in ("width: 1em", "height: 1em", "font-size: 1em", "vertical-align: -0.125em", "color: currentColor"):
            self.assertIn(declaration, rule)
