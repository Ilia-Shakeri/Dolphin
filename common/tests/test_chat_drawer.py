"""Internal chat's header icon + slide-in drawer, replacing the `/chat/` page.

`chat/tests/test_chat.py` already holds every rule about the data itself —
scope, unread counts, the API contract. What is worth proving here is the
1.9.0 move from a standalone page to a header-icon-triggered drawer that
matches the purchased theme's own `kt_drawer_chat` pattern:

* the icon and the drawer render on every authenticated page, gated by the
  same `internal_chat` feature the API already gates, not only on a
  dedicated page;
* the old page is genuinely gone — no route, no sidebar entry — rather than
  left as a second, divergent chat UI beside the new one;
* the drawer is the theme's own real `data-kt-drawer` component (open/close,
  overlay, responsive width all come from it), not a re-implementation;
* the polling that makes it feel live only runs while the drawer is open,
  checked against the theme's own `drawer-on` class.
"""

import pathlib

from django.test import Client, SimpleTestCase, TestCase

from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES

PASSWORD = "Strong-pass-274!"

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin-app.js"
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
        self.assertIn('id="kt_drawer_chat_toggle"', page)
        self.assertIn("گفت‌وگوی داخلی", page)

    def test_the_drawer_itself_is_on_the_page(self):
        page = self.page()
        self.assertIn('id="kt_drawer_chat"', page)
        self.assertIn('data-kt-drawer="true"', page)
        # The real theme component, not a rebuild: direction, overlay and
        # the toggle/close wiring are all attributes the vendor's own KTDrawer
        # reads, the same ones `#app-sidebar` already relies on.
        self.assertIn('data-kt-drawer-direction="end"', page)
        self.assertIn('data-kt-drawer-toggle="#kt_drawer_chat_toggle"', page)
        self.assertIn('data-kt-drawer-close="#kt_drawer_chat_close"', page)

    def test_both_are_absent_when_the_feature_is_off(self):
        with override_active_profile(profile_without("internal_chat")):
            page = self.page()
        self.assertNotIn('id="kt_drawer_chat_toggle"', page)
        self.assertNotIn('id="kt_drawer_chat"', page)

    def test_the_icon_and_drawer_render_on_an_ordinary_page_too(self):
        """Not only the dashboard — every authenticated page carries them."""
        page = self.client.get("/customers/").content.decode("utf-8")
        self.assertIn('id="kt_drawer_chat_toggle"', page)
        self.assertIn('id="kt_drawer_chat"', page)

    def test_the_chat_user_id_is_set_on_the_shell_itself(self):
        """Not through a page-specific `body_data` override — the drawer
        needs it everywhere, so the attribute lives on `<body>` directly."""
        self.assertIn(f'data-chat-user-id="{self.user.pk}"', self.page())

    def test_a_signed_out_visitor_gets_neither(self):
        page = Client().get("/login/").content.decode("utf-8")
        self.assertNotIn("kt_drawer_chat", page)


class OldPageRemovedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="chatdrawer.old", password=PASSWORD, role=User.Role.SALES_MANAGER
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_standalone_chat_page_route_is_gone(self):
        """A second, divergent chat UI is exactly what this move avoids."""
        self.assertEqual(self.client.get("/chat/").status_code, 404)

    def test_the_url_name_no_longer_resolves(self):
        from django.urls import NoReverseMatch, reverse

        with self.assertRaises(NoReverseMatch):
            reverse("common_ui:chat")

    def test_the_sidebar_no_longer_carries_a_chat_entry(self):
        page = self.client.get("/").content.decode("utf-8")
        self.assertNotIn('data-module="chat"', page)


class ScriptBehaviourTests(SimpleTestCase):
    """What the drawer's own script does, pinned by source pattern — the
    same style `test_reminders.py`'s `BadgeStyleTests` and
    `test_dashboard_insights.py`'s `ChartMountOrderTests` already use for a
    behaviour no Django test can execute."""

    def test_setup_chat_runs_on_every_page_not_only_a_named_one(self):
        self.assertIn("setupChat();", SCRIPT)
        # The old page-specific gate must not have survived alongside it.
        self.assertNotIn('if (page === "chat") setupChat();', SCRIPT)

    def test_polling_is_gated_on_the_themes_own_open_state_class(self):
        self.assertIn('drawer.classList.contains("drawer-on")', SCRIPT)

    def test_both_polls_check_the_open_state_before_doing_any_work(self):
        body_start = SCRIPT.index("function setupChat()")
        body = SCRIPT[body_start:SCRIPT.index("\n    setupSearchableSelects();", body_start)]
        self.assertIn("if (!activeThreadId || !isOpen()) return;", body)
        self.assertIn("if (!isOpen()) return;", body)

    def test_opening_the_drawer_polls_immediately_rather_than_waiting(self):
        body_start = SCRIPT.index("function setupChat()")
        body = SCRIPT[body_start:SCRIPT.index("\n    setupSearchableSelects();", body_start)]
        self.assertIn("toggle.addEventListener(\"click\"", body)
        self.assertIn("if (isOpen()) loadThreads();", body)


class LayoutRegressionTests(SimpleTestCase):
    """The flex-scroll pitfall this drawer's own CSS was written to avoid."""

    css = (
        pathlib.Path(__file__).resolve().parents[2] / "common" / "static" / "common" / "dolphin.css"
    ).read_text(encoding="utf-8")

    def test_the_flex_chain_gets_a_real_min_height(self):
        self.assertIn("#kt_drawer_chat_messenger,", self.css)
        self.assertIn("min-height: 0;", self.css.split("#kt_drawer_chat_messenger,")[1][:400])
