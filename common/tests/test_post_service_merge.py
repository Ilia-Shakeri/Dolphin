"""«سرویس پست» is one service (2.40.7).

The carrier connection («پست ایران — بازار الکترونیک», the framework's
`ebazar_post` provider) is no longer a second entry beside the «سرویس پست»
row: the row reads that connection's real state, its settings page shows the
connection and the guide, and its editor is opened from there. Every postal
state has its own icon from one table.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from accounts.models import User
from common.integrations import visible_integrations
from integrations.models import Integration
from sales import postal
from sales.models import PostProviderSettings

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "js" / "features" / "settings" / "integrations.js").read_text(encoding="utf-8")
ICON_CSS = (ROOT / "common" / "static" / "common" / "ui" / "css" / "dolphin-plugins.rtl.css").read_text(encoding="utf-8")


def _post_row(user):
    return next(row for row in visible_integrations(user) if row["key"] == "post")


class OneRowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="post.admin", password="Strong-pass-661!", role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="post.manager", password="Strong-pass-661!", role=User.Role.SALES_MANAGER)

    def test_the_row_names_the_carrier_and_starts_unconfigured(self):
        row = _post_row(self.admin)
        self.assertEqual(row["label"], "سرویس پست")
        self.assertTrue(row["description"].startswith("پست ایران — بازار الکترونیک"))
        self.assertEqual(row["state"], "unconfigured")
        self.assertIsNone(row["test_url"])

    def test_the_row_reads_the_real_connection(self):
        connection = Integration.objects.create(provider_key="ebazar_post", name="پست", enabled=True, status="ok",
                                                secret_hints={"username": "••••abcd"})
        row = _post_row(self.admin)
        self.assertEqual(row["state"], "connected")
        self.assertEqual(row["secret_hint"], "••••abcd")
        self.assertEqual(row["test_url"], f"/api/v1/integrations/{connection.pk}/test/")
        # The framework's test is the Platform Admin's; a sales manager sees
        # the state but gets no button that would answer 403.
        self.assertIsNone(_post_row(self.manager)["test_url"])
        connection.enabled = False
        connection.save()
        self.assertEqual(_post_row(self.admin)["state"], "disabled")

    def test_the_old_generic_settings_row_is_kept_not_deleted(self):
        PostProviderSettings.objects.get_or_create(singleton=PostProviderSettings.SINGLETON, defaults={"base_url": "https://example.test"})
        self.assertTrue(PostProviderSettings.objects.exists())
        self.assertEqual(_post_row(self.admin)["state"], "unconfigured")

    def test_the_settings_page_shows_the_connection_and_whom_to_ask(self):
        self.client.force_login(self.manager)
        page = self.client.get("/settings/post-provider/").content.decode("utf-8")
        self.assertIn('id="post-connection"', page)
        self.assertNotIn('id="post-provider-form"', page)
        self.assertIn("با <strong>مدیر پلتفرم</strong> است", page)
        self.client.force_login(self.admin)
        page = self.client.get("/settings/post-provider/").content.decode("utf-8")
        self.assertIn('?edit=ebazar_post">ساختن اتصال</a>', page)


class IntegrationsPageTests(SimpleTestCase):
    def test_the_connection_is_not_listed_twice(self):
        self.assertIn('const POST_PROVIDER = "ebazar_post";', SCRIPT)
        self.assertIn("catalog.providers.filter((provider) => provider.key !== POST_PROVIDER)", SCRIPT)
        self.assertIn("integrations.filter((integration) => integration.provider_key !== POST_PROVIDER).map(connectionRow)", SCRIPT)

    def test_the_post_row_opens_the_connection_editor(self):
        self.assertIn('if (wanted === POST_PROVIDER && providersByKey[POST_PROVIDER]) {', SCRIPT)
        self.assertIn("openConnection(existing || null, POST_PROVIDER);", SCRIPT)


class StateIconTests(SimpleTestCase):
    def test_every_state_has_its_own_icon(self):
        icons = [state.icon for state in postal.POSTAL_STATES]
        self.assertEqual(len(icons), len(set(icons)))

    def test_every_icon_exists_with_its_path_count(self):
        for state in postal.POSTAL_STATES:
            with self.subTest(state=state.key):
                paths = set(re.findall(rf"\.{re.escape(state.icon)} \.path(\d+):before", ICON_CSS))
                self.assertEqual(paths, {str(n) for n in range(1, state.icon_paths + 1)})

    def test_the_history_carries_the_icons(self):
        self.assertEqual(postal.icon_for("with_post"), {"icon": "di-parcel-tracking", "icon_paths": 3})
        self.assertIsNone(postal.icon_for("متن آزاد قدیمی"))
