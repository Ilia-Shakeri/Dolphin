"""The sign-in page's look and motion (2.40.4) — and that its contract did not move.

`test_login_contract` pins what the page must not offer; this pins what the
redesign added and what it must keep: the same fields and hints, nothing
fetched from elsewhere, motion only on `transform`/`opacity` and none at all
under reduced motion, a refusal announced to assistive technology.
"""

import re
from pathlib import Path

from django.test import SimpleTestCase, TestCase

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "common" / "static" / "common" / "dolphin.css").read_text(encoding="utf-8")
SCRIPT = (ROOT / "common" / "static" / "common" / "js" / "features" / "login" / "login.js").read_text(encoding="utf-8")


def _login_css():
    start = CSS.index("/* Login page (2.40.4)")
    return CSS[start:CSS.index("/* 3. Print", start)]


class RenderedPageTests(TestCase):
    def setUp(self):
        self.page = self.client.get("/login/").content.decode("utf-8")

    def test_the_password_manager_hints_and_autofocus_stay(self):
        self.assertRegex(self.page, r'<input[^>]*name="username"[^>]*autocomplete="username"[^>]*autofocus')
        self.assertRegex(self.page, r'<input[^>]*name="password"[^>]*type="password"[^>]*autocomplete="current-password"')

    def test_a_refusal_is_announced(self):
        self.assertRegex(self.page, r'id="global-message"[^>]*role="alert"')

    def test_nothing_is_requested_from_another_origin(self):
        for attribute in re.findall(r'(?:src|href|srcset)="([^"]+)"', self.page):
            self.assertFalse(attribute.startswith(("http:", "https:", "//")), attribute)
        self.assertNotIn("@import", _login_css())
        self.assertNotIn("url(", _login_css())

    def test_the_password_can_be_shown_by_a_real_button(self):
        self.assertRegex(self.page, r'<button type="button"[^>]*id="login-password-toggle"[^>]*aria-pressed="false"[^>]*aria-label="نمایش گذرواژه"')

    def test_caps_lock_has_a_hint_tied_to_the_field(self):
        self.assertIn('aria-describedby="login-caps"', self.page)
        self.assertRegex(self.page, r'id="login-caps" role="status" hidden')


class MotionTests(SimpleTestCase):
    def test_motion_uses_only_transform_and_opacity(self):
        frames = re.findall(r"@keyframes login-[a-z-]+ \{(.*?)\n\}", _login_css(), flags=re.S)
        self.assertEqual(len(frames), 3)
        for body in frames:
            properties = set(re.findall(r"([a-z-]+):", body))
            self.assertLessEqual(properties, {"opacity", "transform"}, body)

    def test_reduced_motion_turns_every_animation_off(self):
        block = _login_css().split("@media (prefers-reduced-motion: reduce) {")[1]
        for selector in (".login-page .login-enter", ".login-page .login-shake", ".login-page .login-aside-light"):
            self.assertIn(selector, block)
        self.assertIn("animation: none;", block)
        self.assertIn("transition: none;", block)
        self.assertIn('window.matchMedia("(prefers-reduced-motion: reduce)")', SCRIPT)

    def test_the_request_itself_did_not_change(self):
        self.assertIn('formPayload(form, ["username", "password"])', SCRIPT)
        self.assertIn('window.location.assign("/")', SCRIPT)

    def test_the_button_says_it_is_working(self):
        self.assertIn('submit.setAttribute("aria-busy", "true");', SCRIPT)
        self.assertIn('submit.removeAttribute("aria-busy");', SCRIPT)
