"""Every served control resolves to something real.

This is the machine-checked half of the "no demo, placeholder, or dead control"
requirement. Rather than trusting a manual sweep, it extracts the URLs the
maintained UI actually references — form actions, navigation links, and every
`/api/v1/...` path in the script — and resolves each against the URLconf.

It deliberately does not test behaviour; the module test suites do that. What it
proves is narrower and easy to regress: nothing rendered points at a route that
does not exist.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.urls import Resolver404, resolve

from accounts.models import User

from common.deployment.registry import ALL_FEATURES, FEATURE_DEPENDENCIES, missing_dependencies


ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "common" / "templates" / "common"
SCRIPT = ROOT / "common" / "static" / "common" / "dolphin-app.js"

# A template action is a literal path; a script endpoint is a template literal
# whose interpolations stand in for ids and query strings.
ACTION_RE = re.compile(r'action="(/[^"]*)"')
SCRIPT_PATH_RE = re.compile(r'["`](/api/v1/[^"`\s]*)["`]')
INTERPOLATION_RE = re.compile(r"\$\{[^}]*\}")


def _concrete(path):
    """Turn a script template literal into a path the resolver can accept."""
    path = path.split("?", 1)[0]
    # `${key}` is the one interpolation that is not an id: `setupRowSelection`
    # (2026-09-02, the hard-delete feature) builds `/api/v1/${key}/bulk-
    # delete/` from `setupPagedList`'s own `key`, which is always a real REST
    # resource segment (`"customers"`, `"leads"`, …), never a row id. Resolved
    # against one real one — `customers` — rather than substituted with "1"
    # like every other interpolation below, which would look for a route at
    # `/api/v1/1/bulk-delete/` that was never meant to exist.
    path = path.replace("${key}", "customers")
    # Any other interpolated segment is an id in practice; 1 resolves
    # wherever an id is expected and leaves a trailing slash intact.
    path = INTERPOLATION_RE.sub("1", path)
    return re.sub(r"/{2,}", "/", path)


class TemplateActionTests(SimpleTestCase):
    def test_every_form_action_in_a_served_template_resolves(self):
        unresolved = []
        for template in sorted(TEMPLATES.rglob("*.html")) + sorted(TEMPLATES.rglob("*.inc")):
            text = template.read_text(encoding="utf-8")
            for action in ACTION_RE.findall(text):
                if "{" in action:
                    # `{% url %}` output; Django itself fails the render if the
                    # name is unknown, so the template test suite covers it.
                    continue
                try:
                    resolve(_concrete(action))
                except Resolver404:
                    unresolved.append(f"{template.relative_to(ROOT)}: {action}")
        self.assertEqual(unresolved, [])

    def test_no_served_template_carries_a_placeholder_control(self):
        offenders = []
        for template in sorted(TEMPLATES.rglob("*.html")) + sorted(TEMPLATES.rglob("*.inc")):
            text = template.read_text(encoding="utf-8")
            for pattern in ("javascript:void", 'action=""', "TODO", "FIXME", "lorem"):
                if pattern in text:
                    offenders.append(f"{template.relative_to(ROOT)}: {pattern}")
        self.assertEqual(offenders, [])

    def test_every_placeholder_href_is_really_assigned_by_the_script(self):
        """`href="#"` is allowed only where the script fills it in.

        A blanket ban would be the wrong rule: an anchor whose target depends on
        loaded data has to start somewhere. What matters is that something
        actually assigns it, which is what this checks — by element id, so
        deleting the assignment fails here rather than shipping a link that
        silently jumps to the top of the page.
        """
        script = SCRIPT.read_text(encoding="utf-8")
        offenders = []
        for template in sorted(TEMPLATES.rglob("*.html")) + sorted(TEMPLATES.rglob("*.inc")):
            text = template.read_text(encoding="utf-8")
            for element in re.findall(r"<a\b[^>]*\bhref=\"#\"[^>]*>", text):
                element_id = re.search(r'\bid="([^"]+)"', element)
                if element_id is None:
                    offenders.append(f"{template.relative_to(ROOT)}: anonymous href=\"#\"")
                    continue
                assignment = f'getElementById("{element_id.group(1)}").href'
                if assignment not in script:
                    offenders.append(f"{template.relative_to(ROOT)}: {element_id.group(1)} is never assigned")
        self.assertEqual(offenders, [])

    def test_every_served_template_is_tag_balanced(self):
        """An unclosed container silently swallows the rest of the page.

        This is not hypothetical: a bulk class rewrite once injected an opening
        `<div>` with no closing tag, and every element after it ended up outside
        its section. The page still returned 200 and still contained the right
        text, so only a browser measuring the element's height caught it —
        `display: block` with `offsetHeight: 0`. Counting tags is cheap and
        catches the whole class.
        """
        offenders = []
        for template in sorted(TEMPLATES.rglob("*.html")) + sorted(TEMPLATES.rglob("*.inc")):
            text = template.read_text(encoding="utf-8")
            markup = re.sub(r"{%.*?%}|{{.*?}}", "", text, flags=re.DOTALL)
            for tag in ("div", "section", "form", "dialog", "table", "nav"):
                # The word boundary matters: without it `<div` also counts every
                # `<dialog`, and the two miscounts cancel out.
                opens = len(re.findall(rf"<{tag}\b", markup))
                closes = len(re.findall(rf"</{tag}>", markup))
                if opens != closes:
                    offenders.append(
                        f"{template.relative_to(ROOT)}: <{tag}> {opens} open / {closes} close"
                    )
        self.assertEqual(offenders, [])

    def test_no_template_comment_leaks_into_the_served_page(self):
        """Django's `{# #}` comment cannot span lines.

        A multi-line one is not a comment at all: the `{#` is literal text and
        the whole thing renders to the reader. This shipped English developer
        prose onto every page extending `base.html` and onto the top of every
        printed invoice, and no existing test noticed because each one asserted
        what *should* be present. Multi-line commentary must use
        `{% comment %}`.
        """
        offenders = []
        for template in sorted(TEMPLATES.rglob("*.html")) + sorted(TEMPLATES.rglob("*.inc")):
            text = template.read_text(encoding="utf-8")
            for match in re.finditer(r"\{#(.*?)#\}", text, flags=re.DOTALL):
                if "\n" in match.group(1):
                    offenders.append(f"{template.relative_to(ROOT)}: {match.group(1).strip()[:50]}")
        self.assertEqual(offenders, [])

    def test_no_served_template_reaches_a_third_party_host(self):
        """No external fetch, and no vendor name in anything that renders.

        `{% comment %}` blocks are stripped server-side, so naming the design
        system in one is not customer-visible and is worth keeping: it tells the
        next reader where the markup came from. The rendered-output check in
        `RenderedPageCleanlinessTests` is what actually guards the reader.
        """
        offenders = []
        for template in sorted(TEMPLATES.rglob("*.html")) + sorted(TEMPLATES.rglob("*.inc")):
            text = template.read_text(encoding="utf-8")
            visible = re.sub(r"{% comment %}.*?{% endcomment %}", "", text, flags=re.DOTALL)
            for pattern in ('href="http', 'src="http', "cdn.", "googleapis", "Metronic", "KeenThemes"):
                if pattern in visible:
                    offenders.append(f"{template.relative_to(ROOT)}: {pattern}")
        self.assertEqual(offenders, [])


class ScriptEndpointTests(SimpleTestCase):
    def test_every_api_path_the_script_calls_resolves(self):
        text = SCRIPT.read_text(encoding="utf-8")
        unresolved = []
        for raw in sorted(set(SCRIPT_PATH_RE.findall(text))):
            path = _concrete(raw)
            if not path.endswith("/") and not path.endswith(".xlsx"):
                # Every first-party route ends in a slash or is a named export
                # file; anything else is a typo rather than a route.
                unresolved.append(f"{raw} (unexpected shape)")
                continue
            try:
                resolve(path)
            except Resolver404:
                unresolved.append(raw)
        self.assertEqual(unresolved, [])

    def test_the_script_declares_a_handler_for_every_served_page_id(self):
        text = SCRIPT.read_text(encoding="utf-8")
        page_ids = set()
        for template in sorted(TEMPLATES.rglob("*.html")):
            match = re.search(r"{% block page_id %}([a-z0-9-]+){% endblock %}", template.read_text(encoding="utf-8"))
            if match:
                page_ids.add(match.group(1))
        # `shell` is the base default for a page that needs no handler at all.
        page_ids.discard("shell")
        missing = sorted(page for page in page_ids if f'page === "{page}"' not in text)
        self.assertEqual(missing, [])

    def test_the_script_carries_no_placeholder_or_third_party_reference(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for pattern in ("TODO", "FIXME", "http://", "https://", "cdn.", "Metronic", "KTUtil"):
            self.assertNotIn(pattern, text, pattern)

    def test_the_script_carries_no_url_shaped_string_at_all(self):
        """Not one exemption, not a doorway: none.

        Until 1.3.12 this allowed exactly one string — the XML namespace
        `createElementNS` needs to build an SVG node, which is an identifier
        rather than an address. The charts were hand-drawn SVG then. They are
        ApexCharts now, the drawing is the library's, and the last
        `createElementNS` in this script went with it, so the exemption has
        nothing left to cover. Restoring it needs a reason of its own.
        """
        text = SCRIPT.read_text(encoding="utf-8")
        urls = set(re.findall(r"https?://[^\s\"'`)]+", text))
        self.assertEqual(urls, set())


class ClientOneDayOneProfileTests(SimpleTestCase):
    """The feature set the first operational deployment is meant to carry.

    The signed manifest is the source of truth and lives outside this
    repository, so what is checked here is that the intended set is internally
    consistent — every dependency satisfied, every name registered — and that
    the one withheld module is a real choice rather than an oversight.
    Documented in the "Deployment profile — implemented design" section of `BACKEND_SPEC.md`.
    """

    day_one = frozenset({
        "customers", "products", "leads", "sales", "sales_documents", "after_sales",
        "inventory", "quotations", "orders", "invoices", "payments", "customer_ledger",
        "reports", "audit_log",
    })

    def test_the_day_one_set_names_only_registered_features(self):
        self.assertEqual(self.day_one - frozenset(ALL_FEATURES), frozenset())

    def test_the_day_one_set_satisfies_every_dependency(self):
        self.assertEqual(missing_dependencies(self.day_one), {})

    def test_the_withheld_features_are_exactly_the_five_intended_ones(self):
        withheld = frozenset(ALL_FEATURES) - self.day_one
        # `inbound_sms` and `outbound_sms` are both built and provider-neutral,
        # but no real gateway contract, credential, or owner has arrived for
        # Client-1 yet; enabling either would show a report or a send button
        # with nothing real behind it (`KARIZ_SMS_PROVIDER` unset). `internal_
        # it_role` is withheld by Client-1 policy: only a Platform Admin
        # administers users there. `attachments` is withheld because TIARA
        # (Client-1) is frozen as of 2026-09-03 pending a new-feature contract
        # — see DOLPHIN_FEATURE_MAP_AND_ROADMAP.md §8 — not because anything
        # about it is unfinished; a later Client-1 manifest can enable it with
        # no code change. `custom_branding` (2026-09-03) is withheld for the
        # same reason `DEFAULT_OFF_FEATURES` withholds it everywhere: Client-1
        # never asked to replace Dolphin's own name/logo with its own, and the
        # safe default is the platform's brand, not a customer's — a later
        # Client-1 manifest can turn it on with no code change either.
        self.assertEqual(
            withheld,
            frozenset({"inbound_sms", "outbound_sms", "internal_it_role", "attachments", "custom_branding"}),
        )

    def test_nothing_depends_on_a_withheld_feature(self):
        for feature, requires in FEATURE_DEPENDENCIES.items():
            for withheld in ("inbound_sms", "outbound_sms", "internal_it_role", "attachments", "custom_branding"):
                self.assertNotIn(withheld, requires, f"{feature} requires {withheld}")


class RenderedPageCleanlinessTests(TestCase):
    """What actually reaches the reader carries no template syntax or dev prose.

    The static check above catches the known cause; this one checks the effect
    on real rendered pages, so a different cause producing the same symptom is
    caught too.
    """

    def setUp(self):
        self.manager = User.objects.create_user(
            username="render.manager", password="Strong-pass-937!", role=User.Role.SALES_MANAGER
        )
        self.client.force_login(self.manager)

    def test_no_served_page_renders_template_syntax_or_developer_prose(self):
        offenders = []
        for path in ("/", "/customers/", "/leads/", "/products/",
                     "/orders/", "/invoices/", "/payments/", "/stock/", "/warehouses/",
                     "/reports/receivables/", "/reports/profit/", "/login/"):
            body = self.client.get(path).content.decode("utf-8")
            for token in ("{#", "#}", "{%", "%}", "{{", "}}"):
                if token in body:
                    offenders.append(f"{path}: {token}")
            # The vendor's name must never reach the reader, in any page.
            for vendor in ("Metronic", "KeenThemes", "keenthemes"):
                if vendor in body:
                    offenders.append(f"{path}: vendor name {vendor}")
        self.assertEqual(offenders, [])
