"""Every list page's filter row, collapsed behind a header button.

Product-owner request (2026-09-05): filters should look like the purchased
theme's own pattern — click a button, a popup opens, the filters live in it
— rather than sitting permanently inline across the card header.

Twenty-five templates originally carried `<form class="list-filters">`, each
with its own fields and its own submit wiring already attached directly to
that form element (`setupPagedList({form, ...})` or a page's own handler).
`setupListFilterPopovers()` in `dolphin-app.js` finds every remaining
`.list-filters` form generically and moves it — the same DOM node, never a
clone — into a dropdown panel opened by a new toggle button, the same
hand-rolled `.show`-class pattern the reminder bell, search box and user
menu already use (not `data-kt-menu-trigger`, since `KTMenu` needs Popper,
which is not loaded). It is untouched and still exactly this generic.

**Update, 2026-09-09 (product-owner request):** the search box itself had to
come out of that popover — live, in `card-title`, not gated behind a click —
with the popover keeping only the *other* filters (status, ordering, date
windows…) behind a smaller "فیلتر" icon button. Doing that live-search split
generically, the same way the popover itself was done, would have meant
teaching one function every page's different notion of "which field is the
search box" — so the seventeen templates whose filter row is a real,
frequently-used list (`customers`, `leads`, `orders`, …) were converted by
hand instead, each to its own `card-title`/`card-toolbar` markup
(`.list-search` + `.list-filter`/`.list-filter-panel`, wired per page by
`setupListFilter(prefix)` — see that function and `bindLiveSearch` in
`dolphin-app.js`). The six report-style pages left below never had a live
search box to begin with (`reports/*.html` — a required date range submitted
once, not a filterable list), so `setupListFilterPopovers()` still owns them
unchanged, exactly as this file already tested.

What is worth proving:

* the six remaining `.list-filters` forms still transform generically, not
  through a hand-picked list;
* moving a form preserves it — same id, same fields, same name attributes a
  page's own script already looks up;
* the popover opens/closes the same way the other three header dropdowns do,
  and a native reset re-submits so "بازنشانی" actually clears the list;
* nothing here duplicates the reminder bell/search/user-menu positioning
  fix or reaches for `!important` on a narrow screen.
"""

import pathlib

from django.test import SimpleTestCase

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
).read_text(encoding="utf-8")
CSS = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
).read_text(encoding="utf-8")
TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "common" / "templates" / "common"

#: Every template known to carry the shared filter-row class, so the
#: transformation's reach can be checked directly rather than sampled.
FILTER_TEMPLATES = sorted(
    path.relative_to(TEMPLATES).as_posix()
    for path in TEMPLATES.rglob("*.html")
    if 'class="list-filters"' in path.read_text(encoding="utf-8")
)


def _function_body(name):
    start = SCRIPT.index(f"function {name}(")
    # Every top-level function in this file sits at the same four-space
    # indent, one per `function` declaration — so the next one at that same
    # indent, after this one's own, is this one's end. Generic on purpose:
    # this helper now reads more than one function's body. The one function
    # with no such next sibling is `setupListFilterPopovers` itself — the
    # last one defined before the top-level dispatch calls — whose end is
    # marked by the first of those instead.
    try:
        end = SCRIPT.index("\n    function ", start + 1)
    except ValueError:
        end = SCRIPT.index("\n    setupSearchableSelects();", start)
    return SCRIPT[start:end]


#: The six report-style pages `setupListFilterPopovers()` still owns —
#: see this module's own docstring, "Update, 2026-09-09" — kept explicit so a
#: page silently leaving this set (not just the count changing) is caught by
#: name, not just by a number moving.
REPORT_FILTER_TEMPLATES = frozenset({
    "reports/customer_ledger.html",
    "reports/inbound_sms.html",
    "reports/profit.html",
    "reports/receivables.html",
    "reports/sales_documents.html",
    "reports/stock_valuation.html",
})


class ReachTests(SimpleTestCase):
    def test_the_known_set_of_templates_still_carries_the_shared_class(self):
        """Guards the fixture above, not the feature: if one of the six
        report pages stopped using `.list-filters`, the generic popover
        would silently skip it and this would be the only thing to notice.
        The other seventeen list pages converted to their own explicit
        `.list-search`/`.list-filter` markup on purpose (2026-09-09) and are
        expected to be absent here — see this module's own docstring."""
        self.assertEqual(set(FILTER_TEMPLATES), REPORT_FILTER_TEMPLATES)

    def test_the_transformation_is_generic_not_a_hand_picked_list(self):
        body = _function_body("setupListFilterPopovers")
        self.assertIn('document.querySelectorAll("form.list-filters")', body)
        # No page name appears in the function body — it cannot be, since it
        # was written before knowing which twenty-five templates exist.
        for name in ("customers", "leads", "invoices", "products"):
            with self.subTest(name=name):
                self.assertNotIn(f'"{name}', body)


#: The seventeen list pages converted to live search + a small filter panel
#: (2026-09-09) — the counterpart fixture to `REPORT_FILTER_TEMPLATES` above,
#: same reasoning: named explicitly so a page silently losing the pattern is
#: caught by name.
LIVE_SEARCH_TEMPLATES = frozenset({
    "activity_logs/list.html",
    "after_sales/list.html",
    "customers/list.html",
    "interactions/list.html",
    "inventory/stock_levels.html",
    "inventory/stock_movements.html",
    "invoices/list.html",
    "leads/list.html",
    "orders/list.html",
    "payments/cheques.html",
    "payments/installments.html",
    "payments/list.html",
    "product_categories/list.html",
    "products/list.html",
    "sales/list.html",
    "sales_documents/list.html",
    "users/list.html",
    "warehouses/list.html",
})

#: `payments/installments.html` — the one page in the set with no search box
#: at all (nothing free-text to search; only a status/date/ordering filter),
#: so it carries `.list-filter` but never `.list-search`.
LIVE_SEARCH_TEMPLATES_WITHOUT_A_SEARCH_BOX = frozenset({"payments/installments.html"})

#: `users/list.html` — the one page in the set with nothing *but* a search
#: box (no status/date/ordering filter ever existed for it), so it carries
#: `.list-search` but never `.list-filter`.
LIVE_SEARCH_TEMPLATES_WITHOUT_A_FILTER_PANEL = frozenset({"users/list.html"})


class LiveSearchReachTests(SimpleTestCase):
    """The seventeen converted pages actually carry the new markup, and
    `dolphin-app.js` actually wires each one — not just the six report pages
    the class above already covers."""

    def test_every_converted_template_carries_the_new_markup(self):
        for relative_path in sorted(LIVE_SEARCH_TEMPLATES):
            content = (TEMPLATES / relative_path).read_text(encoding="utf-8")
            with self.subTest(template=relative_path):
                if relative_path not in LIVE_SEARCH_TEMPLATES_WITHOUT_A_FILTER_PANEL:
                    self.assertIn('class="list-filter"', content)
                    self.assertIn('class="list-filter-panel"', content)
                if relative_path not in LIVE_SEARCH_TEMPLATES_WITHOUT_A_SEARCH_BOX:
                    self.assertIn('class="list-search"', content)
                # The old generic popover must never also claim a page this
                # module now owns explicitly — the two mechanisms are meant
                # to partition the twenty-three templates, not overlap.
                self.assertNotIn('class="list-filters"', content)

    #: `orders/list.html` and `invoices/list.html` both go through the
    #: shared `setupDocumentList({prefix, ...})` helper (`common.dashboard`'s
    #: own counterpart for commercial documents), which calls
    #: `setupListFilter(prefix)` itself, once, generically — never a literal
    #: `setupListFilter("order")` string a page-by-page search would find.
    TEMPLATES_WIRED_THROUGH_SETUP_DOCUMENT_LIST = frozenset({"orders/list.html", "invoices/list.html"})

    def test_dolphin_app_js_calls_setup_list_filter_for_every_converted_page(self):
        self.assertIn("setupListFilter(prefix);", _function_body("setupDocumentList"))
        checked = LIVE_SEARCH_TEMPLATES - self.TEMPLATES_WIRED_THROUGH_SETUP_DOCUMENT_LIST
        checked -= LIVE_SEARCH_TEMPLATES_WITHOUT_A_FILTER_PANEL
        for relative_path in sorted(checked):
            # Every converted template's own toggle/panel ids are
            # `{prefix}-filter-toggle`/`{prefix}-filter-panel`, `prefix`
            # being that page's own established id stem (`customer`, not
            # `customers`) — read directly from the template rather than
            # guessed, since the stem is irregular (plural list pages, a
            # singular id prefix).
            content = (TEMPLATES / relative_path).read_text(encoding="utf-8")
            start = content.index('class="list-filter"')
            toggle_id = content[start:].split('id="', 1)[1].split('"')[0]
            expected_call = f'setupListFilter("{toggle_id.removesuffix("-filter-toggle")}")'
            with self.subTest(template=relative_path):
                self.assertTrue(toggle_id.endswith("-filter-toggle"), toggle_id)
                self.assertIn(expected_call, SCRIPT)


class PreservationTests(SimpleTestCase):
    """The form is moved, never cloned or rebuilt."""

    body = _function_body("setupListFilterPopovers")

    def test_the_existing_form_node_is_reparented_not_recreated(self):
        self.assertIn("body.appendChild(form);", self.body)
        self.assertNotIn("form.cloneNode", self.body)
        self.assertNotIn("innerHTML = form", self.body)

    def test_the_existing_submit_button_is_reused_not_rebuilt(self):
        self.assertIn(
            'form.querySelector(".list-filters-submit, button[type=\'submit\']")', self.body
        )
        self.assertIn("actions.append(reset, submit);", self.body)


class InteractionTests(SimpleTestCase):
    body = _function_body("setupListFilterPopovers")

    def test_it_opens_and_closes_like_the_other_header_dropdowns(self):
        """The same hand-rolled `.show` toggle as the bell/search/user menu —
        not `data-kt-menu-trigger`, which needs Popper (not loaded here)."""
        self.assertIn('panel.classList.toggle("show", open)', self.body)
        self.assertNotIn("data-kt-menu-trigger", self.body)

    def test_escape_closes_it_and_returns_focus(self):
        self.assertIn('event.key === "Escape"', self.body)
        self.assertIn("toggle.focus();", self.body)

    def test_a_successful_apply_closes_the_popover(self):
        self.assertIn('form.addEventListener("submit", () => setOpen(false));', self.body)

    def test_reset_reloads_the_list_after_the_browser_clears_the_fields(self):
        """Native `reset` only restores field values; nothing re-asks for the
        now-default list unless this resubmits after it."""
        self.assertIn('form.addEventListener("reset"', self.body)
        self.assertIn("form.requestSubmit()", self.body)

    def test_the_toggle_is_addressable_by_the_form_it_opens(self):
        """So a test — or a future script — can find "the filter button for
        the product list" without a second, hand-maintained id."""
        self.assertIn("toggle.dataset.filterToggleFor = form.id;", self.body)


class StylingTests(SimpleTestCase):
    def test_the_panel_is_anchored_the_same_way_the_other_dropdowns_are(self):
        self.assertIn(".list-filters-panel {", CSS)
        rule = CSS.split(".list-filters-panel {")[1].split("}")[0]
        self.assertIn("position: absolute", rule)

    def test_the_narrow_screen_rule_does_not_fight_the_themes_important_width(self):
        """The same lesson already learned once for the reminder bell and the
        search box: pinning both inline edges while `.w-300px !important` is
        also in force is over-constrained."""
        media = CSS.split("@media (max-width: 575.98px) {\n    /* The width stays")[1]
        rule = media.split(".list-filters-panel {")[1].split("}")[0]
        self.assertIn("inset-inline-start", rule)
        self.assertIn("inset-inline-end: auto", rule)
        self.assertNotIn("width:", rule)
        self.assertNotIn("!important", rule)
