"""The orders Kanban board: `/orders/board/`, its `order_kanban` feature
gate, and the drag-to-move wiring in `setupOrderBoard()` (`dolphin-app.js`).

Product-owner request (2026-09-07, first of the report's prioritised
recommendations): a board view for orders, grouped by status, mirroring the
existing lead board (`test_lead_board.py`) exactly. The four columns are
exactly `billing.models.Order.Status` — nothing invented — and the drag-to-move
action is deliberately *not* a new mutation path: it POSTs the same
`/api/v1/orders/<id>/transition/` the order detail page's own status
`<select>` already uses, so it inherits `transition_order`'s existing
scope/permission/stock-side-effect checks rather than duplicating them
(`billing/tests/test_workflows.py` and the order detail page tests already
cover that path; this file does not re-test it).

What is worth proving here, specifically, on top of everything the lead
board's own test file already establishes for the shared plumbing:

* the three separate controls (CLAUDE.md §5.1) hold for the new page —
  feature availability (`order_kanban`, on top of `orders`), and that the
  reused API endpoint is what actually enforces role/scope, not this page;
* the drag handler calls the *existing* transition endpoint with *only*
  `to_status` in the body — no parallel status-transition logic, no new
  endpoint;
* each column's `dragTo` option is drawn from `ORDER_TRANSITIONS`, so an
  invalid move is refused by jKanban itself before any request is sent —
  and that this is display-only, never the actual authority;
* RTL column order and the capability gate on dragging itself (shared CSS
  with the lead board — jkanban image-content coverage is not re-tested
  here, `DockerImageContentTests` in `test_lead_board.py` already covers the
  one bundle both boards load).
"""

import pathlib

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES, DEFAULT_OFF_FEATURES, FEATURE_DEPENDENCIES

PASSWORD = "Strong-pass-604!"

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
).read_text(encoding="utf-8")
CSS = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
).read_text(encoding="utf-8")


def _function_body(name, end_marker):
    start = SCRIPT.index(f"function {name}(")
    end = SCRIPT.index(end_marker, start)
    return SCRIPT[start:end]


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class RegistryTests(SimpleTestCase):
    def test_order_kanban_is_a_registered_feature_depending_only_on_orders(self):
        self.assertEqual(FEATURE_DEPENDENCIES["order_kanban"], frozenset({"orders"}))

    def test_order_kanban_defaults_off(self):
        """A separate frontend dependency and a drag interaction, like
        `lead_kanban` — not a read-only convenience like `reminders`."""
        self.assertIn("order_kanban", DEFAULT_OFF_FEATURES)


class FeatureGateTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="order.board.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.login(username="order.board.manager", password=PASSWORD)

    def test_the_page_is_404_when_order_kanban_is_off(self):
        with override_active_profile(profile_without("order_kanban")):
            self.assertEqual(self.client.get("/orders/board/").status_code, 404)

    def test_the_page_is_404_when_orders_itself_is_off(self):
        with override_active_profile(profile_without("orders", "order_kanban")):
            self.assertEqual(self.client.get("/orders/board/").status_code, 404)

    def test_the_page_renders_when_both_features_are_on(self):
        self.assertEqual(self.client.get("/orders/board/").status_code, 200)

    def test_the_nav_link_only_appears_with_the_feature_on(self):
        with_feature = self.client.get("/orders/").content.decode("utf-8")
        self.assertIn("تابلوی سفارش‌ها", with_feature)
        with override_active_profile(profile_without("order_kanban")):
            without_feature = self.client.get("/orders/").content.decode("utf-8")
        self.assertNotIn("تابلوی سفارش‌ها", without_feature)


class TemplateContentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="order.board.tpl.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="order.board.tpl.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def page(self, username):
        client = Client()
        client.login(username=username, password=PASSWORD)
        return client.get("/orders/board/").content.decode("utf-8")

    def test_the_jkanban_bundle_is_loaded(self):
        page = self.page("order.board.tpl.manager")
        self.assertIn("plugins/custom/jkanban/jkanban.bundle.js", page)
        self.assertIn("plugins/custom/jkanban/jkanban.bundle.rtl.css", page)

    def test_a_manager_is_marked_able_to_manage_orders(self):
        page = self.page("order.board.tpl.manager")
        self.assertIn('data-can-manage-orders="true"', page)

    def test_an_agent_is_also_marked_able_to_manage_their_own_scope(self):
        """`orders.manage` is held by every operational role — object scope,
        not this capability, is what actually confines an agent to their own
        assigned orders (enforced by `DOCUMENT_WRITERS`/`transition_order`,
        not this page)."""
        page = self.page("order.board.tpl.agent")
        self.assertIn('data-can-manage-orders="true"', page)

    def test_the_page_links_back_to_the_ordinary_list(self):
        page = self.page("order.board.tpl.manager")
        self.assertIn("فهرست سفارش‌ها", page)


class ScriptTests(SimpleTestCase):
    body = _function_body("setupOrderBoard", "\n    async function setupAfterSalesCalendar")

    def test_the_four_columns_are_the_real_model_labels_not_invented_ones(self):
        """No parallel status vocabulary — reuses ORDER_TRANSITIONS' own keys,
        which mirror billing.models.Order.TRANSITIONS."""
        self.assertIn("Object.keys(ORDER_TRANSITIONS)", self.body)

    def test_dragging_reuses_the_existing_order_transition_endpoint(self):
        self.assertIn("/api/v1/orders/${orderId}/transition/", self.body)
        self.assertIn('method: "POST"', self.body)
        self.assertIn("body: {to_status: toStatus}", self.body)

    def test_no_second_endpoint_or_status_vocabulary_is_introduced(self):
        self.assertNotIn("/api/v1/order-board", self.body)
        self.assertNotIn("kanban-status", self.body)

    def test_columns_are_fixed_not_reorderable(self):
        self.assertIn("dragBoards: false", self.body)

    def test_dragging_items_is_gated_by_the_manage_capability(self):
        self.assertIn("dragItems: canManage", self.body)
        self.assertIn('canManageOrders === "true"', self.body)

    def test_invalid_moves_are_restricted_via_jkanbans_own_dragto_option(self):
        """Display-only: `transition_order` re-validates independently, so a
        drift in ORDER_TRANSITIONS could only narrow this menu, never widen
        access — the same guarantee the comment beside CHEQUE_TRANSITIONS
        already documents for that table."""
        self.assertIn("dragTo: ORDER_TRANSITIONS[status]", self.body)

    def test_a_failed_move_is_reverted_the_same_way_the_lead_board_reverts(self):
        self.assertIn("source.append(el)", self.body)
        self.assertIn("showError(error)", self.body)

    def test_a_stock_shortage_redirect_is_reflected_not_assumed_away(self):
        """transition_order can silently redirect a shortage-hit confirm to
        cancelled — the board must show whatever status actually came back,
        not the column the card was dropped into."""
        self.assertIn("landedStatus", self.body)
        self.assertIn("موجودی کافی نبود", self.body)

    def test_card_content_is_built_via_textcontent_not_a_raw_template_literal(self):
        """The same escape-then-serialise pattern the lead board's own
        `cardContent` uses: every value assigned through `textContent`,
        `innerHTML` read only once, at the end, to satisfy jKanban's own
        string-based item API."""
        self.assertIn("title.textContent =", self.body)
        self.assertIn("return wrap.innerHTML;", self.body)
        self.assertNotIn("innerHTML = `", self.body)

    def test_card_content_reuses_the_same_fields_the_orders_table_shows(self):
        """No parallel data shape — the same fields `setupOrders()`'s own
        `columns` config already reads off each order."""
        self.assertIn("order.customer_name", self.body)
        self.assertIn("order.total_amount", self.body)
        self.assertIn("order.expected_delivery_at", self.body)
        self.assertIn("order.created_by_display", self.body)

    def test_pagination_is_bounded_not_a_full_table_load(self):
        """One page per column per request, not `loadAllPages` — a column
        with many orders must not load an unbounded result set."""
        self.assertIn("page=1", self.body)
        self.assertNotIn("loadAllPages", self.body)

    def test_a_column_with_more_pages_offers_a_load_more_control(self):
        self.assertIn("renderLoadMore", self.body)
        self.assertIn("not-draggable", self.body)

    def test_empty_columns_are_handled(self):
        self.assertIn("renderEmptyState", self.body)
        self.assertIn("سفارشی در این وضعیت نیست", self.body)


class StylingTests(SimpleTestCase):
    def test_order_board_shares_the_lead_boards_rtl_and_theme_rules(self):
        """One generalised CSS section (dolphin.css §7), not a duplicated
        block — `#order-board` rides the same selectors `#lead-board` does."""
        self.assertIn("#lead-board .kanban-container,\n#order-board .kanban-container {", CSS)
        self.assertIn("#lead-board .kanban-board,\n#order-board .kanban-board {", CSS)
        rule = CSS.split("#order-board .kanban-container {")[1].split("}")[0]
        self.assertIn("flex-direction: row", rule)
        self.assertNotIn("row-reverse", rule)
