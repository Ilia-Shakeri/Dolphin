"""Every list page's filter row, collapsed behind a header button.

Product-owner request (2026-09-05): filters should look like the purchased
theme's own pattern — click a button, a popup opens, the filters live in it
— rather than sitting permanently inline across the card header.

Twenty-five templates carry `<form class="list-filters">`, each with its own
fields and its own submit wiring already attached directly to that form
element (`setupPagedList({form, ...})` or a page's own handler). Rather than
rebuild each one, `setupListFilterPopovers()` in `dolphin-app.js` finds every
`.list-filters` form generically and moves it — the same DOM node, never a
clone — into a dropdown panel opened by a new toggle button, the same
hand-rolled `.show`-class pattern the reminder bell, search box and user
menu already use (not `data-kt-menu-trigger`, since `KTMenu` needs Popper,
which is not loaded).

What is worth proving:

* the transformation is generic and reaches every one of the twenty-five
  forms, not a hand-picked few;
* moving the form preserves it — same id, same fields, same name attributes
  a page's own script already looks up;
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
    # `setupListFilterPopovers` is the last function defined before the
    # top-level dispatch calls, so its own end is marked by the first of
    # those rather than by another `function` declaration.
    end = SCRIPT.index("\n    setupSearchableSelects();", start)
    return SCRIPT[start:end]


class ReachTests(SimpleTestCase):
    def test_the_known_set_of_templates_still_carries_the_shared_class(self):
        """Guards the fixture above, not the feature: if a page's filter row
        stopped using `.list-filters`, the generic popover would silently
        skip it and this would be the only thing to notice."""
        self.assertGreaterEqual(len(FILTER_TEMPLATES), 20, FILTER_TEMPLATES)

    def test_the_transformation_is_generic_not_a_hand_picked_list(self):
        body = _function_body("setupListFilterPopovers")
        self.assertIn('document.querySelectorAll("form.list-filters")', body)
        # No page name appears in the function body — it cannot be, since it
        # was written before knowing which twenty-five templates exist.
        for name in ("customers", "leads", "invoices", "products"):
            with self.subTest(name=name):
                self.assertNotIn(f'"{name}', body)


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
