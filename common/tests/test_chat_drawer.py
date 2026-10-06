"""Internal chat's header icon + slide-in drawer, and the `/chat/` page beside it.

`chat/tests/test_chat.py` already holds every rule about the data itself —
scope, unread counts, the API contract. What is worth proving here is the
1.9.0 move from a standalone page to a header-icon-triggered drawer, and
2.25.0's return of the page alongside it (`PageReturnedTests` — the
product owner asked for both back: "a chat page in the sidebar menu plus
the icon in the header"):

* the icon and the drawer render on every authenticated page, gated by the
  same `internal_chat` feature the API already gates, not only on a
  dedicated page;
* the page is the same engine as the drawer, not a second one — `setupChat`
  parametrised by which markup it drives, so both read and write through the
  identical API calls, cache key and read/unread rules (`ScriptBehaviourTests`
  below, `PageReturnedTests`);
* the drawer is the theme's own real `data-dolphin-drawer` component (open/close,
  overlay, responsive width all come from it), not a re-implementation;
* the polling that makes it feel live only runs while the drawer is open
  (checked against the theme's own `drawer-on` class) or, for the page,
  while it exists in the DOM at all.
"""

from common.tests.panel_js import PANEL_SCRIPT, function_body
import pathlib

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES

PASSWORD = "Strong-pass-274!"

SCRIPT = (
    PANEL_SCRIPT
).read_text(encoding="utf-8")


def profile_without(*features):
    return DeploymentProfile(
        profile_id="client-1",
        features=frozenset(ALL_FEATURES) - frozenset(features),
        source="signed-manifest",
    )


class DrawerRenderingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="chatdrawer.user", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)

    def page(self):
        return self.client.get("/").content.decode("utf-8")

    def test_the_header_icon_is_on_the_page_by_default(self):
        page = self.page()
        self.assertIn('id="dolphin_drawer_chat_toggle"', page)
        self.assertIn("گفت‌وگوی داخلی", page)

    def test_the_drawer_itself_is_on_the_page(self):
        page = self.page()
        self.assertIn('id="dolphin_drawer_chat"', page)
        self.assertIn('data-dolphin-drawer="true"', page)
        # The real theme component, not a rebuild: direction, overlay and
        # the toggle/close wiring are all attributes the vendor's own DolphinDrawer
        # reads, the same ones `#app-sidebar` already relies on.
        self.assertIn('data-dolphin-drawer-direction="end"', page)
        self.assertIn('data-dolphin-drawer-toggle="#dolphin_drawer_chat_toggle"', page)
        self.assertIn('data-dolphin-drawer-close="#dolphin_drawer_chat_close"', page)

    def test_both_are_absent_when_the_feature_is_off(self):
        with override_active_profile(profile_without("internal_chat")):
            page = self.page()
        self.assertNotIn('id="dolphin_drawer_chat_toggle"', page)
        self.assertNotIn('id="dolphin_drawer_chat"', page)

    def test_the_icon_and_drawer_render_on_an_ordinary_page_too(self):
        """Not only the dashboard — every authenticated page carries them."""
        page = self.client.get("/customers/").content.decode("utf-8")
        self.assertIn('id="dolphin_drawer_chat_toggle"', page)
        self.assertIn('id="dolphin_drawer_chat"', page)

    def test_the_chat_user_id_is_set_on_the_shell_itself(self):
        """Not through a page-specific `body_data` override — the drawer
        needs it everywhere, so the attribute lives on `<body>` directly."""
        self.assertIn(f'data-chat-user-id="{self.user.pk}"', self.page())

    def test_a_signed_out_visitor_gets_neither(self):
        page = Client().get("/login/").content.decode("utf-8")
        self.assertNotIn("dolphin_drawer_chat", page)


class PageReturnedTests(TestCase):
    """`/chat/` came back (product-owner decision, 2026-09-28), reversing the
    1.9.0 removal `OldPageRemovedTests` used to pin here. The 1.9.0 worry —
    "a second, divergent chat UI" — is answered by *how* the page comes
    back, not by keeping it gone: `DolphinChatView` renders the same
    `setupChat` engine the drawer runs, only given `chat-page-*` ids and
    `isOpen: () => true` instead of `data-dolphin-drawer`'s own state (see
    `DolphinChatView`'s docstring and `ScriptBehaviourTests` below). One
    engine, two presentations — the drawer for a quick reply from anywhere,
    this page for the fuller workspace the sidebar now links to."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="chatdrawer.page", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_page_renders_for_an_ordinary_role(self):
        response = self.client.get("/chat/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="chat-page-thread-list"')
        self.assertContains(response, 'id="chat-page-messenger"')

    def test_the_url_name_resolves(self):
        from django.urls import reverse

        self.assertEqual(reverse("common_ui:chat"), "/chat/")

    def test_the_page_is_gone_when_the_feature_is_off(self):
        with override_active_profile(profile_without("internal_chat")):
            self.assertEqual(self.client.get("/chat/").status_code, 404)

    def test_the_sidebar_carries_a_chat_entry_gated_on_the_same_feature(self):
        page = self.client.get("/").content.decode("utf-8")
        self.assertIn('data-module="chat"', page)
        with override_active_profile(profile_without("internal_chat")):
            page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('data-module="chat"', page)

    def test_a_signed_out_visitor_is_redirected_not_shown_the_page(self):
        response = Client().get("/chat/")
        self.assertEqual(response.status_code, 302)


class ScriptBehaviourTests(SimpleTestCase):
    """What the drawer's own script does, pinned by source pattern — the
    same style `test_reminders.py`'s `BadgeStyleTests` and
    `test_dashboard_insights.py`'s `ChartMountOrderTests` already use for a
    behaviour no Django test can execute."""

    def test_setup_chat_runs_on_every_page_not_only_a_named_one(self):
        """Restated 2.25.0: `setupChat` now runs twice, once per markup it
        can drive (the header drawer, the full page from `DolphinChatView`)
        — unconditionally, not gated on which page this is; the function
        itself is what no-ops where its markup is absent."""
        self.assertIn('setupChat("chat-drawer", {container: "dolphin_drawer_chat", toggle: "dolphin_drawer_chat_toggle"});', SCRIPT)
        self.assertIn('setupChat("chat-page", {isOpen: () => true, openFromUrl: true});', SCRIPT)
        self.assertNotIn('if (page === "chat") setupChat();', SCRIPT)

    def test_polling_is_gated_on_the_themes_own_open_state_class(self):
        self.assertIn('drawer.classList.contains("drawer-on")', SCRIPT)

    def body(self):
        body_start = SCRIPT.index("function setupChat(prefix")
        return SCRIPT[body_start:SCRIPT.index("\n    setupSearchableSelects();", body_start)]

    def test_both_polls_check_the_open_state_before_doing_any_work(self):
        """Restated 2.18.5: and the tab's visibility too — a background tab
        polls nothing."""
        body = self.body()
        self.assertIn("if (!activeThreadId || !isOpen() || document.hidden) return;", body)
        self.assertIn("if (!isOpen() || document.hidden) return;", body)

    def test_opening_the_drawer_polls_immediately_rather_than_waiting(self):
        """Restated 2.18.5: opening draws what this tab already knows at once
        and refreshes behind it, and warms the likeliest next threads."""
        body = self.body()
        self.assertIn("toggle.addEventListener(\"click\"", body)
        self.assertIn("if (!activeThreadId) renderThreadList();", body)
        self.assertIn("threads.slice(0, 3).forEach((thread) => peekThread(thread.id));", body)


class LiveChatTests(SimpleTestCase):
    """«وقتی چت باز می‌شود نمایش چت‌های قبلی خیلی طول می‌کشد؛ باید خیلی سریع
    و زنده باشد» (2.18.5)."""

    def body(self):
        body_start = SCRIPT.index("function setupChat(prefix")
        return SCRIPT[body_start:SCRIPT.index("\n    setupSearchableSelects();", body_start)]

    def test_polls_are_faster_than_before(self):
        body = self.body()
        self.assertIn("const ACTIVE_THREAD_POLL_MS = 2000;", body)
        self.assertIn("const THREAD_LIST_POLL_MS = 5000;", body)

    def test_a_reopened_thread_is_drawn_from_what_this_tab_already_has(self):
        body = self.body()
        self.assertIn("const cached = messageCache.get(threadId) || [];", body)
        self.assertIn("drawMessages(cached);", body)
        self.assertIn("/messages/?after_id=${lastMessageId}", body)

    def test_hover_warms_a_thread_without_marking_it_read(self):
        body = self.body()
        self.assertIn('row.addEventListener("pointerenter", () => peekThread(thread.id));', body)
        self.assertIn("/messages/?peek=1", body)

    def test_the_tab_copy_is_per_account_and_dies_with_the_session(self):
        self.assertIn('const CHAT_CACHE_PREFIX = "dolphin.chat.v1.";', SCRIPT)
        self.assertIn("`${CHAT_CACHE_PREFIX}${document.body.dataset.chatUserId || \"\"}`", self.body())
        logout = function_body("setupLogout")
        self.assertIn("clearChatCache();", logout)

    def test_a_sent_message_appears_before_the_server_answers(self):
        body = self.body()
        self.assertIn("appendMessageBubble({id: null, mine: true, pending: true, body})", body)

    def test_a_message_is_never_drawn_twice(self):
        body = self.body()
        self.assertIn("if (renderedIds.has(message.id)) return null;", body)


class LayoutRegressionTests(SimpleTestCase):
    """The flex-scroll pitfall this drawer's own CSS was written to avoid."""

    css = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
    ).read_text(encoding="utf-8")

    def test_the_flex_chain_gets_a_real_min_height(self):
        self.assertIn("#dolphin_drawer_chat_messenger,", self.css)
        self.assertIn("min-height: 0;", self.css.split("#dolphin_drawer_chat_messenger,")[1][:400])


class DrawerToPageTests(TestCase):
    """Product owner, 2026-10-06: «پاپ‌آپ گفت‌وگوها … باید یه دکمه برای رفتن
    به صفحهٔ خودش داشته باشد (و یا کلیک بر روی هدر آن ما را به صفحهٔ اصلی
    گفت‌وگوها ببرد)» — both, and an open conversation goes along."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="chatdrawer.link", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client.force_login(self.user)

    def drawer(self):
        page = self.client.get("/").content.decode("utf-8")
        start = page.index('id="dolphin_drawer_chat"')
        return page[start:page.index('id="chat-drawer-list-panel"', start)]

    def test_a_small_arrow_beside_the_title_leads_to_the_chats_page(self):
        """2.40.29: «یه فلش کوچک بغل هدر» — beside the list's title and beside
        an open conversation's name, not a button in the toolbar."""
        drawer = self.drawer()
        self.assertEqual(drawer.count('href="/chat/" data-chat-page-link="chat-drawer"'), 2)
        self.assertEqual(drawer.count("di-arrow-up-left fs-3"), 2)
        self.assertIn('گفت‌وگوها<i class="di-duotone di-arrow-up-left fs-3"', drawer)
        toolbar = drawer[drawer.index('class="card-toolbar"'):]
        self.assertNotIn("data-chat-page-link", toolbar)
        # A `{# #}` comment spanning lines is printed, not dropped — measured
        # here in 2.40.29 before it shipped.
        self.assertNotIn("{#", drawer)

    def test_an_open_conversation_is_carried_to_the_page(self):
        self.assertIn("pointPageLinks(threadId);", SCRIPT)
        self.assertIn('url.searchParams.set("thread", String(threadId))', SCRIPT)
        self.assertIn('setupChat("chat-page", {isOpen: () => true, openFromUrl: true})', SCRIPT)
        self.assertIn("if (threads.some((thread) => thread.id === wanted)) openThread(wanted);", SCRIPT)
