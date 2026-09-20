"""The lead and order Kanban boards, after the 2026-09-20 pass.

Four requests, all about how much a column can show and how little it should
say to show it:

1. cards lost their «مشاهدهٔ جزئیات» footer line for a quiet three-dot control
   in the corner that names itself on hover;
2. a column's search stopped opening a second row above the cards and became
   the magnifier itself, widening in place, closed by a click anywhere;
3. a column shows four whole cards **and a slice of the fifth**, because a list
   cut cleanly after the fourth reads as a list that ends there;
4. the gaps between columns became equal.

The fourth is the one worth explaining. `jkanban.bundle.js` sets a per-board
inline `margin-left`/`margin-right` at `init()` from its own `gutter` option
and splits it between the two sides — so the space *between* two columns came
out as the sum of two margins while the space at each end came out as one.
Three columns, four different gaps. The gutter is now the flex row's own `gap`
and the inline margins are zeroed, which is why both halves of that are pinned
here: zeroing without a `gap` would jam the columns together, and a `gap`
without zeroing would add to the margins rather than replace them.

Read out of the shipped source, so none of it needs a browser. The rendered
result was measured in one at the time: equal 16px gaps on both boards, four
cards fully visible with 19px of the fifth showing, and the search container
going 24px → 137px with its column's cards not moving a pixel.
"""

import pathlib
import re

from django.test import SimpleTestCase


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")


def _function_body(name):
    start = SCRIPT.index(f"function {name}(")
    following = SCRIPT.find("\n    function ", start + 1)
    return SCRIPT[start:following if following != -1 else len(SCRIPT)]


def _rule(selector):
    """The declarations of the rule introduced by `selector`."""
    return CSS.split(selector)[1].split("}")[0]


def _declarations(selector):
    """`_rule`, with the explanatory comments taken out.

    Needed wherever a test asserts that a property is *absent*: this sheet
    explains its reversals where they happened, so the comment saying why
    `opacity` is gone contains the word `opacity`."""
    return re.sub(r"/\*.*?\*/", "", _rule(selector), flags=re.S)


class CardDetailControlTests(SimpleTestCase):
    def test_no_card_carries_a_details_link_any_more(self):
        """The whole card has always been clickable — jKanban's own `click`
        option navigates — so the footer link was a text label repeating what
        the card already did, on every card, in a 300px column."""
        for name in ("setupLeadBoard", "setupOrderBoard"):
            with self.subTest(board=name):
                body = _function_body(name)
                self.assertNotIn('textContent = "مشاهدهٔ جزئیات"', body)
                self.assertNotIn('link.className = "fs-8 fw-semibold mt-1 d-inline-block"', body)

    def test_both_boards_build_their_card_header_from_one_helper(self):
        self.assertEqual(SCRIPT.count("wrap.append(boardCardHeader("), 2)

    def test_the_control_is_a_real_link_not_a_decorative_span(self):
        """It keeps the card reachable by keyboard and openable in a new tab,
        neither of which the div-with-a-click-handler underneath offers."""
        body = _function_body("boardCardHeader")
        self.assertIn('document.createElement("a")', body)
        self.assertIn("more.href = href", body)

    def test_it_names_itself_on_hover_and_to_a_screen_reader(self):
        body = _function_body("boardCardHeader")
        self.assertIn('more.title = "مشاهدهٔ جزئیات"', body)
        self.assertIn('more.setAttribute("aria-label", "مشاهدهٔ جزئیات")', body)

    def test_it_is_three_dots(self):
        body = _function_body("boardCardHeader")
        self.assertIn("ki-dots-vertical", body)

    def test_it_sits_in_the_corner_and_is_drawn_rather_than_ghosted(self):
        """Restated 2026-09-20. It used to be pinned at `opacity: 0.55`
        until the card was hovered, which was right while jKanban's own
        `click` option made the whole card navigate and this was a shortcut
        to the same place. That handler is gone (product owner: «کلیک روی
        بدنهٔ کارت نباید صفحهٔ جزئیات را باز کند»), so this control is now
        the only door into the detail page — and a door drawn at half
        strength does not read as one.

        The rule is inverted, not dropped: quiet-until-hovered became
        always-visible, and the hover and focus states it already had still
        have to distinguish it, which is what the last two lines pin."""
        rule = _declarations("#order-board .kanban-card-more {")
        self.assertNotIn("opacity", rule)
        self.assertIn("#order-board .kanban-item:hover .kanban-card-more", CSS)
        # Reachable by keyboard, not only by pointer.
        self.assertIn("#order-board .kanban-card-more:focus-visible", CSS)


class ColumnSearchTests(SimpleTestCase):
    def test_the_field_lives_in_the_header_not_in_a_new_row(self):
        """It used to be inserted above the card list, which pushed every card
        in that column down by the height of an input."""
        body = _function_body("setupBoardColumnSearch")
        self.assertIn("title.append(search)", body)
        self.assertNotIn("board.insertBefore(wrap, drag)", body)

    def test_the_icon_and_the_field_are_one_box(self):
        body = _function_body("setupBoardColumnSearch")
        self.assertIn("search.append(toggle, input)", body)

    def test_the_container_animates_its_width(self):
        """Width on the container, not on the field: the field's own box is
        sized by a container that is itself sized by its contents, so sizing
        the field is circular. See the rule's own comment."""
        rule = _rule("#order-board .board-search {")
        self.assertIn("transition:", rule)
        self.assertIn("min-width", rule)
        open_rule = _rule("#order-board .board-search-open {")
        self.assertIn("min-width: 10.5rem", open_rule)

    def test_a_click_anywhere_closes_it(self):
        body = _function_body("setupBoardColumnSearch")
        self.assertIn('document.addEventListener("click"', body)
        self.assertIn("if (!search.contains(event.target)) close()", body)

    def test_opening_it_does_not_also_close_it(self):
        """The toggle sits inside the search, so its own click would reach the
        document listener above and close what it just opened."""
        body = _function_body("setupBoardColumnSearch")
        self.assertIn("event.stopPropagation()", body)

    def test_escape_closes_it_too(self):
        body = _function_body("setupBoardColumnSearch")
        self.assertIn('event.key === "Escape"', body)

    def test_closing_clears_the_filter(self):
        """A column left silently filtered by a term nobody can see any more is
        the one way this control could lie about what the board contains."""
        body = _function_body("setupBoardColumnSearch")
        self.assertIn('onSearch("")', body)

    def test_the_closed_field_is_not_a_keyboard_trap(self):
        body = _function_body("setupBoardColumnSearch")
        self.assertIn("input.tabIndex = -1", body)
        self.assertIn("input.tabIndex = 0", body)

    def test_someone_who_asked_for_no_motion_still_gets_the_control(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)


class ColumnHeightTests(SimpleTestCase):
    def test_a_column_shows_four_cards_and_part_of_the_next(self):
        """The slice is the point: a column cut cleanly after the fourth card
        looks like a column that holds exactly four, and nobody scrolls a list
        that appears to have ended."""
        rule = _rule("#order-board .kanban-drag {")
        self.assertIn("--dolphin-board-card:", rule)
        self.assertRegex(rule, r"max-height:\s*calc\(var\(--dolphin-board-card\) \* 4\.\d+\)")

    def test_the_multiplier_leaves_a_real_slice_showing(self):
        rule = _rule("#order-board .kanban-drag {")
        multiplier = float(re.search(r"\* (\d+\.\d+)\)", rule).group(1))
        self.assertGreater(multiplier, 4.0, "four cards would be cut flush, with no slice")
        self.assertLess(multiplier, 5.0, "a whole fifth card is not a slice")

    def test_the_column_scrolls_rather_than_the_page(self):
        """Restated 2026-09-20 for two changes that leave the rule itself
        intact.

        The class is now `dolphin-hover-scroll` rather than the theme's
        `hover-scroll-overlay-y`: the product owner asked for the bar on the
        *right* of an RTL column («اسکرول‌بار باید سمت راست باشد»), which no
        CSS property can express — the container has to be flipped to
        `direction: ltr` and its children flipped back. That flip is also
        why the gap clearing the bar is a physical `padding-right` here;
        `padding-inline-end` would follow the flip to the far side."""
        rule = _rule("#order-board .kanban-drag {")
        self.assertIn("padding-right", rule)
        self.assertIn('boardElement(status)?.classList.add("dolphin-hover-scroll")', SCRIPT)


class ColumnGutterTests(SimpleTestCase):
    def test_the_row_owns_one_gutter(self):
        rule = _rule("#order-board .kanban-container {")
        self.assertIn("gap:", rule)

    def test_the_bundles_own_split_margins_are_overridden(self):
        """Without this the `gap` above would be added to jKanban's margins
        rather than replacing them, and the gaps would still differ."""
        rule = _rule("#lead-board .kanban-board,\n#order-board .kanban-board {")
        self.assertIn("margin-inline: 0 !important", rule)
