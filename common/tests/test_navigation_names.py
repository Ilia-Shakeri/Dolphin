"""One navigation registry, one name per page (2.40.0, widened from 2.39.11)."""

from pathlib import Path

from django.test import SimpleTestCase

from common.navigation import GROUPS, LABELS

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "common"
RETIRED = ("مرکز ارتباطات", "اسناد فروش", "اسناد مالی", "اسناد بازرگانی", "آنالیز")


class NavigationRegistryTests(SimpleTestCase):
    def test_groups_follow_the_business_flow_and_stay_small(self):
        keys = [group.key for group in GROUPS]
        flow = ["campaigns", "leads", "customers", "sales", "inventory", "finance"]
        self.assertEqual([key for key in keys if key in flow], flow)
        for group in GROUPS:
            with self.subTest(group=group.key):
                self.assertLessEqual(len(group.items), 6)

    def test_no_label_appears_twice_and_retired_words_are_gone(self):
        labels = [item.label for group in GROUPS for item in group.items]
        self.assertEqual(len(labels), len(set(labels)))
        captions = [group.label for group in GROUPS] + labels
        for word in RETIRED:
            for caption in captions:
                self.assertNotIn(word, caption)

    def test_the_sidebar_is_drawn_from_the_registry(self):
        base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        self.assertIn("{% sidebar_navigation as nav_groups %}", base)
        self.assertNotIn('<span class="menu-title">مشتریان</span>', base)

    def test_page_eyebrows_never_use_a_retired_group_name(self):
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if "block page_eyebrow" not in text:
                continue
            eyebrow = text.split("block page_eyebrow", 1)[1].split("endblock", 1)[0]
            for retired in RETIRED:
                self.assertNotIn(retired, eyebrow, path.name)

    def test_every_eyebrow_anywhere_is_a_group_name(self):
        """Detail and profile pages too, not only the pages in the menu
        (2.40.16): the eyebrow names the menu group the reader came from."""
        import re

        allowed = {group.label for group in GROUPS} | {"مدیریت پلتفرم", "مدیریت تیم فروش", "مدیریت فنی", "حساب من", "تنظیمات استقرار"}
        roots = [TEMPLATES, Path(__file__).resolve().parents[2] / "profiles" / "templates"]
        for root in roots:
            for path in root.rglob("*.html"):
                block = re.search(r"{% block page_eyebrow %}(.*?){% endblock %}", path.read_text(encoding="utf-8"), re.S)
                if not block or "{{" in block.group(1):
                    continue
                text = re.sub(r"<[^>]+>", "", block.group(1))
                for word in re.split(r"{%[^%]*%}", text):
                    if word.strip():
                        self.assertIn(word.strip(), allowed, path.name)

    def test_every_registered_page_has_a_label(self):
        self.assertTrue(all(LABELS.values()))


class EyebrowTests(SimpleTestCase):
    def test_each_listed_pages_eyebrow_is_its_menu_group(self):
        import re

        from django.urls import resolve, reverse

        for group in GROUPS:
            if group.key in {"dashboard", "settings"}:
                continue
            for item in group.items:
                view = resolve(reverse(item.url_name)).func.view_class
                template = (Path(__file__).resolve().parents[1] / "templates" / view.template_name)
                text = template.read_text(encoding="utf-8")
                eyebrow = re.search(r'{% block page_eyebrow %}<span[^>]*>(.*?)</span>', text)
                if eyebrow is None:
                    continue
                with self.subTest(page=item.url_name):
                    expected = "مدیریت" if group.key == "administration" else group.label
                    self.assertEqual(eyebrow.group(1), expected)


class PageTabColourTests(SimpleTestCase):
    """2.40.24: the current page tab is visible (it was white on white)."""

    def test_the_active_tab_has_its_own_colours(self):
        css = (Path(__file__).resolve().parents[1] / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
        rule = css.split(".dolphin-page-tabs.nav-pills-custom .nav-link.active {")[1].split("}")[0]
        self.assertIn("color: var(--bs-primary);", rule)
        self.assertIn("background-color: var(--bs-primary-light);", rule)
