"""Settings tabs are history entries and a keyboard tab bar (2.40.13)."""

from pathlib import Path

from django.test import SimpleTestCase

SCRIPT = (Path(__file__).resolve().parents[1] / "static" / "common" / "js" / "features" / "settings" / "settings-page.js").read_text(encoding="utf-8")


class SettingsTabsTests(SimpleTestCase):
    def body(self):
        return SCRIPT.split("function setupSettingsTabs() {")[1].split("\n}\n")[0]

    def test_a_switch_is_a_history_entry_and_back_returns(self):
        body = self.body()
        self.assertIn("history.pushState(", body)
        self.assertNotIn("history.replaceState(", body)
        self.assertIn('window.addEventListener("popstate", () => show(keyFrom(window.location.search)));', body)

    def test_arrow_keys_follow_the_reading_direction_with_roving_tabindex(self):
        body = self.body()
        self.assertIn('event.key === (rtl ? "ArrowLeft" : "ArrowRight")', body)
        self.assertIn('event.key === "Home"', body)
        self.assertIn('event.key === "End"', body)
        self.assertIn("tab.tabIndex = active ? 0 : -1;", body)

    def test_an_unknown_tab_falls_back_to_the_first(self):
        self.assertIn("if (!tabs.some((tab) => tab.dataset.settingsTab === key)) key = tabs[0].dataset.settingsTab;", self.body())
