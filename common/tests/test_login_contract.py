"""The login page offers exactly one way in: a username and a password.

Client-1 policy names several things that must **not** be on this page. A
missing feature is invisible, so it is the kind of requirement that silently
regresses the first time someone copies a login template from elsewhere. This
module pins it against the rendered page rather than the source.
"""

import re
from pathlib import Path

from django.test import TestCase


ROOT = Path(__file__).resolve().parents[2]


class LoginPageContractTests(TestCase):
    def setUp(self):
        self.content = self.client.get("/login/").content.decode("utf-8")

    def test_the_page_renders_in_persian_rtl(self):
        self.assertIn('<html lang="fa" dir="rtl">', self.content)
        self.assertIn("ورود به سامانه", self.content)

    def test_exactly_one_form_posting_to_the_session_login_endpoint(self):
        forms = re.findall(r"<form\b[^>]*>", self.content)
        self.assertEqual(len(forms), 1, forms)
        self.assertIn('action="/api/v1/auth/login/"', forms[0])
        self.assertIn('method="post"', forms[0])

    def test_only_a_username_and_a_password_are_collected(self):
        names = re.findall(r'<input\b[^>]*\bname="([^"]+)"', self.content)
        self.assertEqual(sorted(set(names)), ["csrfmiddlewaretoken", "password", "username"])

    def test_the_page_offers_no_alternative_route_in(self):
        # Social sign-in, registration, password recovery, a demo account, and
        # multi-factor prompts are all outside Client-1 policy. None of them may
        # appear, even as a disabled control.
        forbidden = (
            "google", "Google", "oauth", "OAuth", "sso", "SSO", "facebook", "apple",
            "signup", "sign-up", "register", "ثبت‌نام", "ثبت نام",
            "forgot", "reset", "فراموشی", "بازیابی",
            "demo", "Demo", "دمو", "نمونه",
            "otp", "OTP", "2fa", "mfa", "کد یک‌بارمصرف", "احراز دومرحله",
        )
        body = self.content.partition("<body")[2]
        for token in forbidden:
            self.assertNotIn(token, body, token)

    def test_the_page_offers_no_language_switcher(self):
        for token in ("lang-switch", "language", "English", "EN</", "زبان", 'hreflang'):
            self.assertNotIn(token, self.content, token)
        # One document language, so no alternate-language link either.
        self.assertNotIn("<link rel=\"alternate\"", self.content)

    def test_the_page_loads_nothing_from_a_third_party(self):
        self.assertNotIn('href="http', self.content)
        self.assertNotIn('src="http', self.content)

    def test_the_served_template_itself_stays_this_narrow(self):
        template = ROOT / "common" / "templates" / "common" / "login.html"
        text = template.read_text(encoding="utf-8")
        self.assertNotIn("href=\"#\"", text)
        self.assertEqual(len(re.findall(r"<form\b", text)), 1)
