"""One name per menu group, used the same way in the menu and on its pages (2.39.11)."""

from pathlib import Path

from django.test import SimpleTestCase

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "common"
GROUPS = ("سرنخ‌ها و مشتریان", "کمپین‌ها", "فروش و تأمین", "مالی", "انبار و موجودی")


class NavigationNameTests(SimpleTestCase):
    def test_menu_groups_carry_the_agreed_names_and_the_retired_ones_are_gone(self):
        base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
        for name in GROUPS:
            self.assertIn(f'<span class="menu-title">{name}</span>', base)
        for retired in ("مرکز ارتباطات", "اسناد فروش", "اسناد مالی"):
            self.assertNotIn(f'<span class="menu-title">{retired}</span>', base)

    def test_page_eyebrows_never_use_a_retired_group_name(self):
        for path in TEMPLATES.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            if "block page_eyebrow" not in text:
                continue
            eyebrow = text.split("block page_eyebrow", 1)[1].split("endblock", 1)[0]
            for retired in ("مرکز ارتباطات", "اسناد بازرگانی", "اسناد مالی"):
                self.assertNotIn(retired, eyebrow, path.name)
