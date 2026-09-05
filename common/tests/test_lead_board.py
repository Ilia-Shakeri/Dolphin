"""The leads Kanban board: `/leads/board/`, its `lead_kanban` feature gate,
and the drag-to-move wiring in `setupLeadBoard()` (`dolphin-app.js`).

Product-owner request (2026-09-05, immediate priority (a) of three): a
board view for leads, grouped by pipeline stage, alongside the existing
list view. The three columns are exactly `sales.Lead.Status` — nothing
invented — and the drag-to-move action is deliberately *not* a new mutation
path: it PATCHes the same `/api/v1/leads/<id>/` the list page's status
dropdown and the follow-up calendar's own drag already use, so it inherits
`update_lead`'s existing scope/permission checks rather than duplicating
them (`sales/tests/test_workflows.py` and `test_lead_calendar.py` already
cover that path; this file does not re-test it).

What is worth proving here, specifically:

* the three separate controls (CLAUDE.md §5.1) hold for the new page —
  feature availability (`lead_kanban`, on top of `leads`), and that the
  reused API endpoint is what actually enforces role/scope, not this page;
* the drag handler calls the *existing* endpoint with *only* `status` in
  the body — no parallel status-transition logic, no new endpoint;
* the vendor `jkanban` bundle actually reaches a built image (the historical
  `fullcalendar` gap this repository already hit once, in `.dockerignore`
  and `scripts/validate_image_content.py`);
* RTL column order and the capability gate on dragging itself.
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
DOCKERIGNORE = (
    pathlib.Path(__file__).resolve().parents[2] / ".dockerignore"
).read_text(encoding="utf-8")
VALIDATOR = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "validate_image_content.py"
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
    def test_lead_kanban_is_a_registered_feature_depending_only_on_leads(self):
        self.assertEqual(FEATURE_DEPENDENCIES["lead_kanban"], frozenset({"leads"}))

    def test_lead_kanban_defaults_off(self):
        """A separate frontend dependency and a drag interaction, like
        `internal_chat` — not a read-only convenience like `reminders`."""
        self.assertIn("lead_kanban", DEFAULT_OFF_FEATURES)


class DockerImageContentTests(SimpleTestCase):
    """The 1.7.5 fullcalendar gap, guarded against recurring for jkanban:
    a bundle a served page loads must actually survive `.dockerignore`."""

    def test_dockerignore_reinstates_the_jkanban_bundle(self):
        self.assertIn("!assets/plugins/custom/jkanban", DOCKERIGNORE)

    def test_the_validator_no_longer_flags_jkanban_as_unused_demo_material(self):
        self.assertNotIn('"assets/plugins/custom/jkanban"', VALIDATOR)

    def test_the_validator_requires_both_jkanban_files(self):
        self.assertIn("assets/plugins/custom/jkanban/jkanban.bundle.js", VALIDATOR)
        self.assertIn("assets/plugins/custom/jkanban/jkanban.bundle.rtl.css", VALIDATOR)


class FeatureGateTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="board.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.login(username="board.manager", password=PASSWORD)

    def test_the_page_is_404_when_lead_kanban_is_off(self):
        with override_active_profile(profile_without("lead_kanban")):
            self.assertEqual(self.client.get("/leads/board/").status_code, 404)

    def test_the_page_is_404_when_leads_itself_is_off(self):
        with override_active_profile(profile_without("leads", "lead_kanban")):
            self.assertEqual(self.client.get("/leads/board/").status_code, 404)

    def test_the_page_renders_when_both_features_are_on(self):
        self.assertEqual(self.client.get("/leads/board/").status_code, 200)

    def test_the_nav_link_only_appears_with_the_feature_on(self):
        with_feature = self.client.get("/leads/").content.decode("utf-8")
        self.assertIn("تابلوی سرنخ‌ها", with_feature)
        with override_active_profile(profile_without("lead_kanban")):
            without_feature = self.client.get("/leads/").content.decode("utf-8")
        self.assertNotIn("تابلوی سرنخ‌ها", without_feature)


class TemplateContentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="board.tpl.manager", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.agent = User.objects.create_user(
            username="board.tpl.agent", password=PASSWORD, role=User.Role.SALES_AGENT
        )

    def page(self, username):
        client = Client()
        client.login(username=username, password=PASSWORD)
        return client.get("/leads/board/").content.decode("utf-8")

    def test_the_jkanban_bundle_is_loaded(self):
        page = self.page("board.tpl.manager")
        self.assertIn("plugins/custom/jkanban/jkanban.bundle.js", page)
        self.assertIn("plugins/custom/jkanban/jkanban.bundle.rtl.css", page)

    def test_a_manager_is_marked_able_to_manage_leads(self):
        page = self.page("board.tpl.manager")
        self.assertIn('data-can-manage-leads="true"', page)

    def test_an_agent_is_also_marked_able_to_manage_their_own_scope(self):
        """`leads.manage` is held by every operational role — object scope,
        not this capability, is what actually confines an agent to their own
        assigned leads (enforced by `update_lead`, not this page)."""
        page = self.page("board.tpl.agent")
        self.assertIn('data-can-manage-leads="true"', page)

    def test_the_page_links_back_to_the_ordinary_list(self):
        page = self.page("board.tpl.manager")
        self.assertIn("فهرست سرنخ‌ها", page)


class ScriptTests(SimpleTestCase):
    body = _function_body("setupLeadBoard", "\n    async function setupAfterSalesCalendar")

    def test_the_three_columns_are_the_real_model_labels_not_invented_ones(self):
        """No parallel status vocabulary — reuses the same map the ordinary
        list's table row and the calendar legend already use."""
        self.assertIn("Object.keys(LEAD_STATUS_LABELS)", self.body)

    def test_dragging_reuses_the_existing_lead_endpoint(self):
        self.assertIn("/api/v1/leads/${leadId}/", self.body)
        self.assertIn('method: "PATCH"', self.body)
        self.assertIn("body: {status: toStatus}", self.body)

    def test_no_second_endpoint_or_status_vocabulary_is_introduced(self):
        self.assertNotIn("/api/v1/lead-board", self.body)
        self.assertNotIn("kanban-status", self.body)

    def test_columns_are_fixed_not_reorderable(self):
        self.assertIn("dragBoards: false", self.body)

    def test_dragging_items_is_gated_by_the_manage_capability(self):
        self.assertIn("dragItems: canManage", self.body)
        self.assertIn('canManageLeads === "true"', self.body)

    def test_a_failed_move_is_reverted_the_same_way_the_calendar_reverts(self):
        self.assertIn("source.append(el)", self.body)
        self.assertIn("showError(error)", self.body)

    def test_card_content_is_built_via_textcontent_not_a_raw_template_literal(self):
        """The same escape-then-serialise pattern `buildEventPopoverContent`
        already uses: every value assigned through `textContent`, `innerHTML`
        read only once, at the end, to satisfy jKanban's own string-based
        item API."""
        self.assertIn("title.textContent =", self.body)
        self.assertIn("return wrap.innerHTML;", self.body)
        self.assertNotIn("innerHTML = `", self.body)

    def test_pagination_is_bounded_not_a_full_table_load(self):
        """One page per column per request, not `loadAllPages` — a column
        with many leads must not load an unbounded result set."""
        self.assertIn("page=1", self.body)
        self.assertNotIn("loadAllPages", self.body)

    def test_a_column_with_more_pages_offers_a_load_more_control(self):
        self.assertIn("renderLoadMore", self.body)
        self.assertIn("not-draggable", self.body)

    def test_empty_columns_are_handled(self):
        self.assertIn("renderEmptyState", self.body)
        self.assertIn("سرنخی در این وضعیت نیست", self.body)


class StylingTests(SimpleTestCase):
    def test_rtl_column_order_is_corrected_not_left_at_the_bundles_default(self):
        """jKanban's own CSS ships physical `float: left`; this panel is RTL,
        so the first, most-urgent column must land on the right instead.

        Plain `row`, not `row-reverse` — measured empirically in a real
        browser: `row-reverse` put the first board on the *left*, because it
        swaps flexbox's main-start to the inline-end on top of the flip
        `direction: rtl` (inherited from `<html>`) already gives plain `row`.
        """
        self.assertIn("#lead-board .kanban-container {", CSS)
        rule = CSS.split("#lead-board .kanban-container {")[1].split("}")[0]
        self.assertIn("flex-direction: row", rule)
        self.assertNotIn("row-reverse", rule)

    def test_hardcoded_bundle_colours_are_repointed_at_theme_tokens(self):
        self.assertIn("#lead-board .kanban-board {", CSS)
        rule = CSS.split("#lead-board .kanban-board {")[1].split("}")[0]
        self.assertIn("var(--bs-gray-100)", rule)
