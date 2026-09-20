"""Batch C of the 2026-09-20 UI pass: the invoice wizard, settings, popovers.

Three product-owner items, and again the through-line is that each replaced
several near-copies with one thing.

**Item 6 — «اقلام و تخفیف».** The step showed a product picker, a quantity
box and a delete button, and no money at all until the review two steps
later. It now shows the unit price and the line total per row, right-aligned
and tabular so the columns are comparable, with a live summary underneath
that computes the document exactly the way `billing/money.py` does — line
discount first, then the sum, then tax on what is left. The header row and
the line rows share one grid declaration, so a column and its label cannot
drift apart, and on a phone each row becomes its own labelled card.

The step's own container was the real defect behind «فاصله‌گذاری حرفه‌ای»:
the theme lays a stepper's current content out as a flex *row*, so at 375px
the heading measured 34px, the intro 45px and the line container 23px —
eight children sharing one row. One `flex-direction: column` is the fix.

**Item 7 — settings and the sidebar.** «تنظیمات» is a page with four
sections; it belongs in the navigation, not in the account dropdown beside a
sign-out button. «برند و لوگوی پنل» left the administration accordion and is
reached from that page as «شخصی‌سازی پنل», behind the same capability.

**Item 8 — the header popovers.** Four copies of one open/close behaviour,
none of which knew about the others, so the reminder panel stayed open
underneath the search panel. One registry now, two document listeners in
total, and opening any popover closes the rest by construction.

Read out of the shipped source. What a browser was used for at the time:
the invoice wizard's header and row cells matched right edge for right edge
(1108/800/679/590/462) with identical resolved tracks; a 3 × ۱۷٬۸۰۰٬۰۰۰ line
at 10% discount and 9% tax previewed ۵۲٬۳۸۵٬۴۰۰ ریال and the invoice the
server then stored held `total_amount` 52385400.00; the duplicate-product
refusal blocked the step with its own sentence; at 375px the step's children
were all 309px with no horizontal scroll on the page or the dialog; the
sidebar's last entry was «تنظیمات» and the user menu no longer had one; and
opening the bell then the search then the user menu left exactly one open
each time.
"""

import pathlib
import re

from django.test import SimpleTestCase


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
TEMPLATES = ROOT / "common" / "templates" / "common"
BASE = (TEMPLATES / "base.html").read_text(encoding="utf-8")
INVOICES = (TEMPLATES / "invoices" / "list.html").read_text(encoding="utf-8")
ORDERS = (TEMPLATES / "orders" / "list.html").read_text(encoding="utf-8")
SETTINGS = (TEMPLATES / "settings" / "settings.html").read_text(encoding="utf-8")
BRANDING = (TEMPLATES / "branding" / "settings.html").read_text(encoding="utf-8")

CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
#: Template markup with its `{% comment %}` prose removed, for the assertions
#: that something is *absent*: these templates explain their removals in
#: place, and the explanation names the thing that went.
def markup(text):
    return re.sub(r"\{% comment %\}.*?\{% endcomment %\}", "", text, flags=re.S)


def function_body(name):
    start = SCRIPT.index(f"function {name}(")
    following = SCRIPT.find("\n    function ", start + 1)
    return SCRIPT[start:following if following != -1 else len(SCRIPT)]


def rule(selector, source=CODE):
    for block in source.split("}"):
        if "{" not in block:
            continue
        head, body = block.split("{", 1)
        if selector in head:
            return body
    return ""


# ===========================================================================
# Item 6 — the invoice wizard's lines step
# ===========================================================================


class LineStepLayoutTests(SimpleTestCase):
    def test_the_step_lays_its_children_out_in_a_column(self):
        """The defect behind the whole item. The theme makes a stepper's
        current content `display: flex` with the default row direction, which
        is right for a step holding one `.row` and wrong for a step holding
        eight blocks — measured at 375px, the heading came out 34px wide and
        the line container 23px."""
        self.assertIn("flex-direction: column", rule(".wizard-lines-step"))

    def test_the_header_and_the_rows_share_one_grid_declaration(self):
        """Not two that happen to match: a column and the label above it can
        then never drift apart, which is exactly what the wrapping flex row
        this replaced could not promise."""
        self.assertIn(
            ".wizard-lines-step .wizard-lines-head,\n.wizard-line-row {",
            CODE,
        )
        shared = rule(".wizard-lines-step .wizard-lines-head,\n.wizard-line-row")
        self.assertIn("display: grid", shared)
        self.assertIn("grid-template-columns:", shared)

    def test_the_last_track_is_the_delete_buttons_measured_size(self):
        """`btn-sm btn-icon` computes to 34.8px at this theme's 13px root.
        At the 2.25rem the track was first written as, the button overflowed
        it by five pixels and the header spacer named a narrower column than
        the one beneath it."""
        shared = rule(".wizard-lines-step .wizard-lines-head,\n.wizard-line-row")
        self.assertIn("2.675rem", shared)
        # And the spacer fills that track rather than collapsing to zero.
        self.assertIn("width: 100%", rule(".wizard-lines-step .wizard-lines-head-spacer"))

    def test_the_money_columns_are_right_aligned_and_tabular(self):
        """«ترازبندی اعداد». Proportional figures never line their last
        digits up, which is the only thing that makes a column of amounts
        comparable at a glance."""
        declarations = rule(".wizard-line-price,\n.wizard-line-total")
        self.assertIn("text-align: end", declarations)
        self.assertIn("font-variant-numeric: tabular-nums", declarations)

    def test_a_wizard_with_a_line_step_gets_a_wider_dialog(self):
        self.assertIn("dialog:has(.wizard-lines-step) {", CODE)
        self.assertIn("58rem", rule("dialog:has(.wizard-lines-step)"))

    def test_a_phone_gets_one_labelled_card_per_row(self):
        phone = CODE.split("@media (max-width: 767.98px)")[-1]
        self.assertIn(".wizard-lines-head", phone)
        self.assertIn("display: none !important", phone)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", phone)
        # The header is gone, so each cell names itself.
        self.assertIn("content: attr(data-label)", phone)

    def test_the_row_builder_supplies_those_labels(self):
        body = function_body("createLineItemRows")
        self.assertIn('price.dataset.label = "قیمت واحد"', body)
        self.assertIn('total.dataset.label = "جمع ردیف"', body)


class LineRowTests(SimpleTestCase):
    def test_a_row_shows_the_price_and_the_line_total(self):
        body = function_body("createLineItemRows")
        self.assertIn("price.dataset.linePrice", body)
        self.assertIn("total.dataset.lineTotal", body)
        self.assertIn("money(unit * count)", body)

    def test_the_price_is_shown_and_not_edited(self):
        """The API accepts a per-line `unit_price`, but this wizard has never
        sent one and the server uses the product's own current price. An
        editable box would offer an override the form does not make."""
        body = function_body("createLineItemRows")
        self.assertIn('price.className = "wizard-line-price"', body)
        self.assertNotIn('price.type = "number"', body)

    def test_both_controls_carry_the_constraints_the_server_enforces(self):
        body = function_body("createLineItemRows")
        self.assertIn("select.required = true;", body)
        self.assertIn("quantity.required = true;", body)
        self.assertIn('quantity.min = "1";', body)
        # `clean_quantity`'s own ceiling.
        self.assertIn('quantity.max = "1000000";', body)

    def test_both_wizards_use_the_same_row_builder(self):
        self.assertEqual(SCRIPT.count("function createLineItemRows("), 1)
        self.assertEqual(SCRIPT.count("createLineItemRows(lineHost, products"), 2)


class DocumentTotalsTests(SimpleTestCase):
    def test_the_order_of_operations_is_the_servers(self):
        """The discount rides on each *line* (`createFields` sends it as each
        item's `discount_percent`), so it comes off each line before they are
        summed and the tax is charged on what is left. Summing first and
        discounting after gives a different number on any document whose
        lines round differently — and the reader would see one figure in the
        form and another on the saved invoice."""
        body = function_body("documentTotals")
        self.assertIn("const discount = roundMoney((line * percent) / 100);", body)
        self.assertIn("subtotal = roundMoney(subtotal + roundMoney(line - discount));", body)
        self.assertIn("const tax = roundMoney((subtotal * rate) / 100);", body)

    def test_money_is_rounded_the_way_the_server_rounds_it(self):
        """`quantize_money` is half up to two places. A preview that rounded
        differently would differ from the stored figure by a rial and make
        the reader doubt both."""
        body = function_body("roundMoney")
        self.assertIn("Math.round((Number(value) + Number.EPSILON) * 100) / 100", body)

    def test_one_renderer_draws_both_wizards_summaries(self):
        self.assertEqual(SCRIPT.count("function renderDocumentTotals("), 1)
        self.assertIn('renderDocumentTotals("create-invoice", lines)', SCRIPT)
        self.assertIn('renderDocumentTotals("create-order", lines)', SCRIPT)

    def test_the_summary_is_redrawn_when_either_percentage_changes(self):
        body = function_body("setupInvoices")
        self.assertIn('["create-invoice-discount", "create-invoice-tax"].forEach', body)

    def test_the_review_step_names_the_final_amount(self):
        body = function_body("setupInvoices")
        self.assertIn('["مبلغ نهایی", money(totals.total)]', body)


class LineStepValidationTests(SimpleTestCase):
    def test_the_wizard_can_refuse_a_step_for_a_reason_markup_cannot_express(self):
        body = function_body("setupWizard")
        self.assertIn("const complaint = validateStep?.(current, contentOf(current));", body)
        self.assertIn("[data-step-error]", body)

    def test_the_two_rules_it_adds_are_both_real(self):
        """A product chosen twice becomes two line items for one thing; a
        document past the server's ceiling is refused after the reader has
        filled it in. Everything else on this step — an empty product, a
        quantity below one — is a `required` attribute the browser already
        enforces and words for itself."""
        body = function_body("validateLinesStep")
        self.assertIn("lines.duplicateProduct()", body)
        self.assertIn("MAX_DOCUMENT_LINES", body)

    def test_it_only_speaks_for_a_lines_step(self):
        body = function_body("validateLinesStep")
        self.assertIn('content.classList.contains("wizard-lines-step")', body)

    def test_both_wizards_pass_it(self):
        self.assertEqual(SCRIPT.count("validateStep: (index, content) => validateLinesStep(content, lines)"), 2)

    def test_both_steps_have_somewhere_to_print_the_refusal(self):
        for name, text in (("invoices", INVOICES), ("orders", ORDERS)):
            with self.subTest(page=name):
                self.assertIn("data-step-error", markup(text))

    def test_the_stub_before_the_catalogue_loads_answers_every_question(self):
        """A half-built stub is how `lines.grossTotals` became a TypeError on
        a slow catalogue; the frozen object answers all six."""
        block = SCRIPT.split("const EMPTY_LINE_ROWS = Object.freeze({")[1].split("});")[0]
        for name in ("addLine", "reset", "collect", "grossTotals", "duplicateProduct", "count"):
            with self.subTest(method=name):
                self.assertIn(name, block)


class InvoiceStepMarkupTests(SimpleTestCase):
    def test_the_two_percentages_sit_in_the_summary_beside_what_they_change(self):
        step = INVOICES.split('class="wizard-lines-step"')[1].split("data-kt-stepper-element")[0]
        self.assertIn('id="create-invoice-totals"', step)
        summary = step.split('id="create-invoice-totals"')[1]
        self.assertIn('id="create-invoice-discount"', summary)
        self.assertIn('id="create-invoice-tax"', summary)

    def test_the_summary_names_all_four_figures(self):
        for name in ("gross", "discount", "tax", "total"):
            with self.subTest(figure=name):
                self.assertIn(f'data-total="{name}"', INVOICES)

    def test_the_order_wizard_claims_no_final_amount(self):
        """That form deliberately asks for no tax rate and its `createFields`
        sends none, so «مبلغ نهایی» there would be a number this form does
        not determine."""
        self.assertIn('data-total="gross"', ORDERS)
        self.assertNotIn('data-total="total"', ORDERS)
        self.assertNotIn('id="create-order-tax"', ORDERS)

    def test_the_header_names_the_five_columns(self):
        head = INVOICES.split('class="wizard-lines-head"')[1].split("</div>")[0]
        for label in ("کالا", "قیمت واحد", "تعداد", "جمع ردیف"):
            with self.subTest(column=label):
                self.assertIn(label, head)


# ===========================================================================
# Item 7 — settings out of the modal, branding into settings
# ===========================================================================


class SettingsPlacementTests(SimpleTestCase):
    def test_the_settings_link_is_the_last_entry_in_the_sidebar(self):
        sidebar = markup(BASE).split('id="app-sidebar"')[1]
        self.assertIn('id="open-settings"', sidebar)
        # Nothing but this link's own markup between it and the end of the
        # navigation — it really is the last entry, not merely present.
        after = sidebar.split('id="open-settings"')[1].split("</a>", 1)[1].split("</nav>")[0]
        self.assertNotIn("menu-link", after)

    def test_it_is_gone_from_the_user_menu(self):
        menu = markup(BASE).split('id="user-menu"')[1].split("</div>\n                        </div>")[0]
        self.assertNotIn('id="open-settings"', menu)

    def test_it_carries_no_role_gate(self):
        """Every reader has display preferences of their own; the
        deployment-wide sections inside the page keep their own gates."""
        sidebar = markup(BASE).split('id="app-sidebar"')[1]
        entry = sidebar.split('<div class="menu-item">\n                                    <a id="open-settings"')[0]
        self.assertFalse(entry.rstrip().endswith("{% if can_view_audit %}"))


class BrandingPlacementTests(SimpleTestCase):
    def test_the_branding_page_is_gone_from_the_sidebar(self):
        self.assertNotIn('data-module="branding-settings"', markup(BASE))

    def test_it_is_reached_from_the_settings_page_by_its_new_name(self):
        self.assertIn("شخصی‌سازی پنل", SETTINGS)
        self.assertIn('id="open-panel-appearance"', SETTINGS)
        self.assertIn("common_ui:branding-settings", SETTINGS)

    def test_the_page_itself_is_renamed(self):
        self.assertIn("{% block page_title %}شخصی‌سازی پنل{% endblock %}", BRANDING)
        self.assertNotIn("برند و لوگوی پنل", BRANDING)

    def test_the_capability_still_gates_it(self):
        """Renaming a page is not a permission change. `can_manage_branding`
        guards the card exactly as it guarded the sidebar entry, and the view
        and API gates are untouched."""
        card = SETTINGS.split('id="open-panel-appearance"')[0]
        self.assertTrue(card.rstrip().endswith("{% if can_manage_branding %}")
                        or "{% if can_manage_branding %}" in card.rsplit("{% endif %}", 1)[-1])

    def test_the_administration_gate_dropped_a_capability_that_opens_nothing(self):
        """A reader holding only `can_manage_branding` would otherwise get an
        empty «مدیریت» heading over an accordion with nothing in it."""
        self.assertNotIn(
            "can_view_audit or can_manage_users or can_manage_branding or can_manage_sms_provider",
            BASE,
        )
        self.assertIn("can_view_audit or can_manage_users or can_manage_sms_provider", BASE)


# ===========================================================================
# Item 8 — one popover behaviour
# ===========================================================================


class PopoverRegistryTests(SimpleTestCase):
    def test_there_is_one_open_close_implementation(self):
        self.assertEqual(SCRIPT.count("function registerPopover("), 1)

    def test_every_panel_in_the_shell_goes_through_it(self):
        """Five: the user menu, global search, the reminder bell, and each
        list card's filter panel — the fifth being the one that used the
        `hidden` attribute rather than `.show`."""
        # Calls, not the definition: the function's own signature destructures
        # its argument and so matches the same text.
        calls = SCRIPT.count("registerPopover({") - SCRIPT.count("function registerPopover({")
        self.assertEqual(calls, 5)

    def test_opening_one_closes_the_others(self):
        """The product owner's own case: «وقتی منوی یادآورها باز است و روی
        جست‌وجو کلیک می‌کنیم، منوی جدید نباید زیر منوی قبلی باز شود»."""
        body = function_body("registerPopover")
        self.assertIn("if (open) closeOtherPopovers(entry);", body)
        self.assertEqual(SCRIPT.count("function closeOtherPopovers("), 1)

    def test_the_two_page_rules_are_bound_once_for_all_of_them(self):
        """Not once per popover. Before this there were four document-level
        click listeners and four keydown listeners for the same two rules."""
        body = function_body("setupPopoverDismissal")
        self.assertEqual(body.count('document.addEventListener("click"'), 1)
        self.assertEqual(body.count('document.addEventListener("keydown"'), 1)
        self.assertIn("setupPopoverDismissal();", SCRIPT)

    def test_a_click_on_the_icon_inside_a_toggle_counts_as_inside(self):
        """The bug the four copies disagreed about: three compared
        `event.target !== toggle`, which is false for the `<i>` inside the
        button, so clicking the glyph closed the menu the same click had just
        opened."""
        body = function_body("setupPopoverDismissal")
        self.assertIn("if (entry.toggle.contains(event.target)) return;", body)

    def test_escape_closes_and_returns_focus_to_the_button(self):
        body = function_body("setupPopoverDismissal")
        self.assertIn('if (event.key !== "Escape") return;', body)
        self.assertIn("entry.close(); entry.toggle.focus();", body)

    def test_it_knows_the_one_panel_that_is_not_a_show_dropdown(self):
        """A list card's filter panel is plain markup toggled with `hidden`.
        Converting it to a `.show` dropdown is a visual change this item did
        not ask for, so the component knows both mechanisms rather than the
        page keeping its own copy of the behaviour."""
        body = function_body("registerPopover")
        self.assertIn("useHidden", body)
        self.assertIn("if (useHidden) panel.hidden = !open;", body)
        self.assertIn("useHidden: true,", function_body("setupListFilter"))

    def test_no_panel_keeps_its_own_copy_of_the_behaviour(self):
        """`setOpen` survives only inside `registerPopover` itself."""
        for name in ("setupUserMenu", "setupGlobalSearch", "setupReminderBell", "setupListFilter"):
            with self.subTest(panel=name):
                self.assertNotIn("function setOpen(", function_body(name))
                self.assertNotIn("const setOpen = ", function_body(name))

    def test_the_search_shortcut_still_works_through_the_registry(self):
        body = function_body("setupGlobalSearch")
        self.assertIn('event.key.toLowerCase() === "k"', body)
        self.assertIn("popover.open();", body)
