"""Round 2 of the product owner's UI/UX follow-up (2026-09-21) — twelve fixes
and additions on top of the five batches already shipped as `2.14.0`.

One class per item, added as each item lands, in the same source-scanning
style as `test_ui_overhaul_*` (`ui_overhaul_helpers`): what a browser check
already confirmed once is pinned here against silent regressions, not
re-verified.
"""

from django.test import SimpleTestCase

from common.tests.ui_overhaul_helpers import (
    CODE,
    ROOT,
    SCRIPT,
    TEMPLATES,
    function_body,
    markup,
    python_function,
    rule,
)

PAYMENTS_LIST = (TEMPLATES / "payments" / "list.html").read_text(encoding="utf-8")
BASE = (TEMPLATES / "base.html").read_text(encoding="utf-8")
INTEGRATIONS_SOURCE = (ROOT / "common" / "integrations.py").read_text(encoding="utf-8")


def exact_rule(selector, source=CODE):
    """`rule()`'s declarations, but for the one block whose selector is
    exactly this — not merely contains it as a substring. `rule("
    .postal-mini-step")` also matches `.postal-mini-stepper` and
    `.postal-mini-step-current`; this pins the block by its own opening
    line (`<selector> {`, this file's one-selector-per-line convention)."""
    marker = f"\n{selector} {{"
    start = source.index(marker) + len(marker)
    end = source.index("}", start)
    return source[start:end]


class JalaliPickerTitleSpacingTests(SimpleTestCase):
    """Item 1 — the month/year title in the date picker read as one jumbled
    word: 2026-09-20 split it into two buttons (`monthBtn`/`yearBtn` in
    `openJalaliPicker`, dolphin-app.js) so each half opens its own grid, but
    both buttons carry the base `.btn` class the nav-arrow rule also
    selects — `.jalali-picker .jalali-picker-header .btn` forced them to a
    27px square meant for a lone icon, leaving ~0 content width once padding
    was accounted for. The text was clipped to an unreadable sliver.
    """

    def test_nav_arrow_rule_excludes_the_title_buttons(self):
        # The fixed-width icon-button rule must no longer also catch the
        # two title buttons — that was the whole bug.
        self.assertIn(
            ".jalali-picker .jalali-picker-header .btn:not(.jalali-picker-scope)",
            CODE,
        )

    def test_title_is_a_flex_row_with_a_real_gap(self):
        # `display:flex` + `gap` is what actually separates the two buttons;
        # without it they sat back to back with zero space between them
        # regardless of their own padding.
        body = rule(".jalali-picker-title")
        self.assertIn("display: flex", body)
        self.assertRegex(body, r"gap:\s*0\.3rem")

    def test_scope_padding_wins_over_the_vendor_button(self):
        # Metronic's own `.btn:not(...).btn-sm` (eight `:not()` clauses) has
        # higher specificity than any selector built from this component's
        # own classes, so the padding override needs `!important` to
        # actually apply — without it the buttons kept the vendor's roomy
        # text-button padding despite the width fix, which is what had
        # pushed a long month name out of the title's own space.
        body = rule(".jalali-picker .jalali-picker-scope")
        self.assertIn("!important", body)
        self.assertIn("overflow: hidden", body)


class LineChartAxisLabelTests(SimpleTestCase):
    """Item 2 — the bottom axis of every line/mixed chart (`renderAreaChart`,
    `renderMixedChart`) was truncating its own already-thinned date labels
    to unreadable garbage: measured live on the dashboard trend widget, a
    full `۱۴۰۵/۰۴/۱۵` came out `۱…`, and even the shortened `۰۴/۱۵` this fix
    introduces still came out `۰۴…` before `trim` was removed. The
    untruncated value only ever reached a hover `<title>` nobody finds.
    """

    def test_compact_axis_label_drops_the_year(self):
        body = function_body("compactAxisLabel", SCRIPT)
        self.assertIn('split("/")', body)
        self.assertIn("parts.length === 3", body)

    def test_thinning_formatter_shortens_surviving_labels(self):
        body = function_body("thinningFormatter", SCRIPT)
        self.assertIn("compactAxisLabel(value)", body)

    def test_neither_line_chart_lets_apex_trim_the_axis_text(self):
        # `trim: true` is what was chopping the already-short label down
        # further — removed from both chart functions, `hideOverlappingLabels`
        # stays as the real backstop against genuine overlap.
        for fn in ("renderAreaChart", "renderMixedChart"):
            body = function_body(fn, SCRIPT)
            self.assertNotIn("trim: true", body, f"{fn} still lets Apex trim its axis text")
            self.assertIn("hideOverlappingLabels: true", body)


class BoardCardDetailsLinkTests(SimpleTestCase):
    """Item 4 — the three-dot "view details" link on a board card
    (`boardCardHeader`) was a real `<a href>` that never navigated: jKanban's
    own vendor bundle attaches a click listener straight to every
    `.kanban-item` it builds and calls the event's `preventDefault()`
    unconditionally, which also cancels the anchor's own default action
    since a link's navigation resolves only after the click event finishes
    propagating. Confirmed live: dispatching a click on the link navigated
    to `/leads/<id>/` once the fix was in place.
    """

    def test_the_fix_runs_in_the_capture_phase(self):
        # Has to see the click before jKanban's own bubble-phase listener on
        # `.kanban-item` does, or the preventDefault already happened.
        body = function_body("letCardDetailsLinkThrough", SCRIPT)
        self.assertIn('.closest(".kanban-card-more")', body)
        self.assertIn("event.stopPropagation()", body)
        self.assertIn("}, true)", body)

    def test_both_boards_install_it(self):
        for fn in ("setupLeadBoard", "setupOrderBoard"):
            body = function_body(fn, SCRIPT)
            self.assertIn("letCardDetailsLinkThrough(container)", body, f"{fn} does not install the fix")


class PaymentWizardDocumentStepTests(SimpleTestCase):
    """Item 5 — the receipts/payments wizard's «اطلاعات سند» step shared the
    exact bug `.wizard-lines-step` was already written to fix: the theme
    lays every `[data-kt-stepper-element="content"]` out as `display:flex;
    flex-direction:row` by default, and this step has up to five top-level
    children once a fieldset is shown, so they fought each other for one
    shared row instead of stacking. Measured live with «چک» selected before
    the fix: the fields row came out 128px wide, the cheque fieldset 252px,
    the notes row 64px.
    """

    def test_the_step_carries_the_scoping_class(self):
        self.assertIn('class="wizard-document-step" data-kt-stepper-element="content"', markup(PAYMENTS_LIST))

    def test_the_step_is_a_column(self):
        body = rule(".wizard-document-step")
        self.assertIn("flex-direction: column", body)
        self.assertIn("align-items: stretch", body)

    def test_the_sections_get_more_air_than_a_lone_form_row_would(self):
        # The theme's own `.mt-2` utility is itself `!important`
        # (style.bundle.rtl.css), so beating it for just this step needs the
        # same — a single, targeted override, not a chain.
        body = rule(".wizard-document-step > .mt-2")
        self.assertIn("!important", body)


class PostalMiniStepperTests(SimpleTestCase):
    """Item 6 — «رهگیری پستی» (sales_documents/list.html) showed each
    document's postal status as plain text in a table cell; the full
    four-stop stepper only ever existed on one document's own detail page.
    Product owner, 2026-09-21: «وضعیت پستی باید ۴ تا ایکون پست سرهم به هم
    متصل باشد و در هر مرحله‌ای است باید این ایکون روشن باشد. کلا ۴ حالت باید
    وجود داشته باشد». The four states and their order were already decided
    (2026-09-20, `sales/postal.py`) and are read from
    `item.postal_stepper` — the exact field `SalesDocumentSerializer`
    already computed for the detail page — not redeclared here.
    """

    def test_the_row_reads_the_servers_own_stepper_not_a_redeclared_one(self):
        body = function_body("postalStatusCell", SCRIPT)
        self.assertIn("item.postal_stepper", body)
        self.assertIn("step.icon", body)
        self.assertIn("step.stage", body)

    def test_a_pre_vocabulary_free_text_status_falls_back_to_text(self):
        """`stepper_for` (sales/postal.py) returns `[]` for a status outside
        the four states, and four icons with none of them current would
        claim to know where such a parcel is when nobody does."""
        body = function_body("postalStatusCell", SCRIPT)
        self.assertIn("if (!steps || !steps.length)", body)
        self.assertIn("item.postal_status", body)

    def test_the_current_stage_is_named_for_a_screen_reader(self):
        body = function_body("postalStatusCell", SCRIPT)
        self.assertIn('setAttribute("aria-label"', body)
        self.assertIn("mark.title = step.label", body)

    def test_the_list_row_calls_it_instead_of_printing_raw_text(self):
        body = function_body("salesDocumentRow", SCRIPT)
        self.assertIn("postalStatusCell(row, item)", body)
        self.assertNotIn('appendCell(row, item.postal_status)', body)

    def test_four_icons_sit_flush_against_each_other(self):
        """"سرهم به هم متصل" — connected, not merely nearby: the rail is
        one continuous line and the marks carry no gap of their own.

        `rule()` matches by substring of the selector text, so a bare
        `.postal-mini-step` query also matches `.postal-mini-stepper` and
        `.postal-mini-step-current` — this pins the exact single-class rule
        by its own opening line instead."""
        self.assertIn("display: inline-flex", rule(".postal-mini-stepper"))
        mark = exact_rule(".postal-mini-step")
        self.assertNotIn("gap", mark)
        self.assertNotIn("margin", mark)

    def test_the_current_mark_is_visibly_lit(self):
        body = exact_rule(".postal-mini-step-current")
        self.assertIn("var(--bs-primary)", body)
        self.assertIn("box-shadow", body)


INBOUND_SMS_REPORT = (TEMPLATES / "reports" / "inbound_sms.html").read_text(encoding="utf-8")


class ReportWizardCenteringTests(SimpleTestCase):
    """Item 7 — both report wizards (sales-documents-and-post, inbound-sms)
    live directly in the page, not inside a `dialog` the way the
    create-document wizards do, so nothing capped their width. On a wide
    screen the stepper nav, a three-line step and a results table all
    stretched edge to edge of the content area (product owner, 2026-09-21:
    «ویزارد مرحله‌ای ... باید وسط‌چین باشد»)."""

    def test_the_wizard_card_is_capped_and_centred(self):
        body = exact_rule(".report-wizard-card")
        self.assertIn("max-width", body)
        self.assertIn("margin-inline: auto", body)

    def test_both_report_pages_use_the_capped_class(self):
        sales_documents_report = (TEMPLATES / "reports" / "sales_documents.html").read_text(encoding="utf-8")
        self.assertIn('class="card report-wizard-card"', markup(sales_documents_report))
        self.assertIn('class="card report-wizard-card"', markup(INBOUND_SMS_REPORT))


class ReportProvinceDropdownTests(SimpleTestCase):
    """Item 7's second half — the sales-documents-and-post report's province
    filter was a free-text `<input>`, and the report's own filter is an
    *exact* match (`reports/services.py`), so a typo already returned
    nothing; the fix is a dropdown of the same 31 canonical names the
    customer map and form already read from `iran-provinces.json`, not a
    second hand-typed list (product owner, 2026-09-21: «استان باید منو
    دراپ‌داون باشه»)."""

    def setUp(self):
        self.template = (TEMPLATES / "reports" / "sales_documents.html").read_text(encoding="utf-8")

    def test_the_field_is_a_select_not_a_text_input(self):
        markup_text = markup(self.template)
        self.assertIn('<select class="form-select form-select-solid" id="document-report-province">', markup_text)
        self.assertNotIn('id="document-report-province" maxlength', markup_text)

    def test_it_is_filled_from_the_same_canonical_list_the_map_uses(self):
        body = function_body("setupSalesDocumentReport", SCRIPT)
        self.assertIn("fillProvinceSelect(", body)
        self.assertIn('document-report-province', body)


class ExcelButtonIconTests(SimpleTestCase):
    """Item 8 — every Excel import/export button in the panel gets a small,
    theme-consistent icon (product owner, 2026-09-21: «یه ایکون کوچولو
    اکسل در دکمه باشه ... هماهنگ با تم اصلی»). `ki-file-sheet` — a real
    icon in the purchased, actually-bundled keenicons set
    (`plugins.bundle.rtl.css`), not an invented brand-coloured logo — so
    "coordinated with the theme" means using its own icon system, the same
    as every other icon in the panel."""

    TEMPLATE_PATHS = (
        "leads/detail.html",
        "products/list.html",
        "reports/inbound_sms.html",
        "reports/sales_documents.html",
        "reports/profit.html",
        "reports/receivables.html",
        "reports/stock_valuation.html",
        "includes/performance_panel.inc",
        "users/list.html",
        "customers/list.html",
    )

    def test_the_icon_is_a_real_bundled_keenicon(self):
        """`ki-file-sheet` must actually exist in the loaded icon font, not
        merely look plausible — the same 31-icon-vs-576-icon mistake this
        session already caught once for a different icon name."""
        bundle = (ROOT / "assets" / "plugins" / "global" / "plugins.bundle.rtl.css").read_text(encoding="utf-8")
        self.assertIn(".ki-file-sheet .path1", bundle)
        self.assertIn(".ki-file-sheet .path2", bundle)

    def test_every_excel_button_carries_it(self):
        for relative in self.TEMPLATE_PATHS:
            path = TEMPLATES / relative
            text = markup(path.read_text(encoding="utf-8"))
            self.assertIn(
                "ki-file-sheet", text,
                f"{relative} has an Excel import/export control with no icon",
            )

    def test_the_icon_has_its_two_paths(self):
        for relative in self.TEMPLATE_PATHS:
            path = TEMPLATES / relative
            text = markup(path.read_text(encoding="utf-8"))
            if "ki-file-sheet" not in text:
                continue
            self.assertIn('<span class="path1">', text)
            self.assertIn('<span class="path2">', text)


class DashboardWidgetDragTests(SimpleTestCase):
    """Item 10 — dashboard widget reordering used HTML5 drag-and-drop, which
    never fires on a touch screen at all and drew the drag with the
    browser's own uncontrollable ghost image. Rewritten on Pointer Events,
    which unify mouse/touch/pen, with the dragged widget positioned by a
    real CSS transform this code owns and every other widget the drag
    displaces animating (FLIP) from its old slot to its new one — product
    owner, 2026-09-21: «کار با ویجت‌ها ... مثل ویجت‌های apple و اندروید
    روان و پرکاربرد باشد».

    A real bug surfaced and was fixed while building this: without
    `lastSwapTarget`, every `pointermove` while the pointer sat anywhere
    within the same target widget re-ran the swap — and a swap is its own
    inverse, so hovering one widget for several consecutive move events (the
    common case; a widget is ~235px wide) toggled it back and forth and
    landed on either the original or swapped arrangement depending on
    parity, which looked like dragging did nothing about half the time.
    Verified live: dragging a widget across two others produced the correct
    three-way shift (A landed where C was, B and C both slid over) and
    persisted through a reload; before the fix, the same drag left the
    order completely unchanged.
    """

    def test_no_html5_drag_and_drop_remains(self):
        # Checked as the actual `addEventListener` calls, not the bare
        # words — this docstring explains the HTML5-to-Pointer-Events
        # switch by name, which a plain substring check would trip on.
        body = function_body("setupDashboardEditor", SCRIPT)
        for event_name in ("dragstart", "dragover", "drop", "dragend"):
            self.assertNotIn(f'addEventListener("{event_name}"', body, event_name)
        self.assertNotIn(".draggable = true", body)

    def test_pointer_events_drive_the_drag(self):
        body = function_body("setupDashboardEditor", SCRIPT)
        self.assertIn('"pointerdown"', body)
        self.assertIn('"pointermove"', body)
        self.assertIn('"pointerup"', body)

    def test_the_same_target_does_not_toggle_every_move_event(self):
        body = function_body("setupDashboardEditor", SCRIPT)
        self.assertIn("lastSwapTarget", body)
        self.assertIn("target !== lastSwapTarget", body)

    def test_displaced_widgets_animate_rather_than_snap(self):
        body = function_body("setupDashboardEditor", SCRIPT)
        self.assertIn("function swapWithAnimation", body)
        self.assertIn('transition = "transform 0.2s ease"', body)

    def test_touch_does_not_fight_the_page_for_a_scroll_gesture(self):
        self.assertIn("touch-action: none", exact_rule(".dashboard-widget.editing"))
        self.assertIn("touch-action: none", rule(".dashboard-widget-resize"))

    def test_the_dragged_widget_is_lifted_not_dimmed(self):
        """Restated 2026-09-21: `opacity: 0.45` read as "disabled", not
        "picked up"."""
        body = exact_rule(".dashboard-widget.dragging")
        self.assertNotIn("opacity", body)
        card_body = exact_rule(".dashboard-widget.dragging > .card")
        self.assertIn("scale(1.03)", card_body)
        self.assertIn("box-shadow", card_body)


class IntegrationsNavRenameTests(SimpleTestCase):
    """Item 11 — the sidebar's and the admin settings page's own entry into
    the connections hub used to be a standalone «تنظیمات سامانهٔ پیامک»
    link, pointing at the SMS settings page directly and gated on
    `can_manage_sms_provider` alone — a Sales Manager who may configure the
    post connection (item 9) but not SMS never saw *any* way into either.
    Product owner, 2026-09-21: «تنظیمات سامانهٔ پیامک باید به اتصال سامانه
    های تغییر اسم یابد و در ورودی سرویس های مختلف و فعال/غیرفعال بودن
    انها رو نشان بده و با کلیک بر روی آن بتوان وارد تنظیماتش [شد]» — which
    is exactly what the existing «اتصال سرویس‌ها» hub (`common/
    integrations.py`, since batch D) already does; the fix is pointing the
    two navigation entries at it instead of at SMS alone, and renaming it
    to match the product owner's own wording.

    The SMS-sending page's own contextual shortcut to SMS-specific settings
    (`sms/outbound.html`) is deliberately untouched — a reader already
    there wants SMS settings specifically, not the general hub.
    """

    def test_the_sidebar_no_longer_links_straight_to_sms_settings(self):
        markup_text = markup(BASE)
        self.assertNotIn('href="{% url \'common_ui:sms-provider-settings\' %}"', markup_text)
        self.assertIn(
            '<a data-module="integrations" class="menu-link" href="{% url \'common_ui:integrations\' %}">',
            markup_text,
        )
        self.assertIn("اتصال سامانه‌ها", markup_text)

    def test_the_sidebar_accordion_shows_for_anyone_who_can_configure_something(self):
        markup_text = markup(BASE)
        self.assertIn("can_manage_integrations", markup_text)
        self.assertNotIn("can_manage_sms_provider", markup_text)

    def test_the_sms_page_keeps_its_own_contextual_shortcut(self):
        outbound = (TEMPLATES / "sms" / "outbound.html").read_text(encoding="utf-8")
        self.assertIn("can_manage_sms_provider", outbound)
        self.assertIn("sms-provider-settings", outbound)

    def test_the_settings_page_dropped_the_redundant_sms_only_button(self):
        settings_page = markup((TEMPLATES / "settings" / "settings.html").read_text(encoding="utf-8"))
        self.assertNotIn("sms-provider-settings", settings_page)
        self.assertIn("can_manage_integrations", settings_page)
        self.assertIn("اتصال سامانه‌ها", settings_page)

    def test_the_hub_gate_is_cheap_no_status_query_per_page_load(self):
        """`can_manage_integrations` is computed on every page — it must not
        call the per-row status functions `visible_integrations` does
        (an OutboundSMS query, a PostProviderSettings read)."""
        body = python_function("any_integration_configurable", INTEGRATIONS_SOURCE)
        self.assertNotIn(".status(", body)
        self.assertIn("integration.feature", body)
        self.assertIn("integration.gate", body)

    def test_the_placeholder_row_cannot_make_the_gate_true(self):
        """`coming_soon` has neither a feature nor a gate and is always
        "visible" — counting it would make `can_manage_integrations` true
        for everyone, which defeats the whole point of the check."""
        body = python_function("any_integration_configurable", INTEGRATIONS_SOURCE)
        self.assertIn("integration.settings_url_name", body)
