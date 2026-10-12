"""Wizards that keep still, a better conversation, themed lists, plain errors (2.40.40).

Product owner, 2026-10-12, after deploying 2.40.38: the date picker in some
wizards opened in the wrong place and the wizards changed width when their
scroll bar appeared; the conversation's composer should read better and a
message's time show only on hover or tap; every dropdown should look like the
panel; and every error should be short, plain Persian — the login page's just
«نام کاربری یا رمز عبور اشتباه می‌باشد».
"""

from pathlib import Path

from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import ErrorDetail
from rest_framework.test import APIClient

from accounts.models import User
from common.persian_errors import persianise

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "common" / "static" / "common"
JS = STATIC / "js"
CSS = (STATIC / "dolphin.css").read_text(encoding="utf-8")
PASSWORD = "Strong-pass-740!"


class WizardTests(SimpleTestCase):
    def test_an_open_dialog_is_not_a_containing_block(self):
        # A `scale` or `translate` other than none makes the dialog the box a
        # `position: fixed` date picker is placed in, so it opened far from
        # its field.
        self.assertIn("dialog[open] { opacity: 1; scale: none; translate: none; animation: none; }", CSS)

    def test_the_scroll_bar_does_not_resize_a_wizard(self):
        self.assertIn("scrollbar-gutter: stable;", CSS)


class ConversationTests(SimpleTestCase):
    def test_a_message_is_a_bubble_with_its_time_on_hover(self):
        chat = (JS / "shell" / "chat.js").read_text(encoding="utf-8")
        self.assertIn('row.className = `chat-msg ${message.mine ? "is-mine" : "is-theirs"}`;', chat)
        self.assertIn('row.classList.toggle("show-time");', chat)
        self.assertIn(".chat-msg:hover .chat-msg-time,", CSS)
        self.assertIn(".chat-msg.show-time .chat-msg-time,", CSS)

    def test_both_composers_are_one_field_with_the_send_button_inside(self):
        for name, prefix in (("chat.html", "chat-page"), ("base.html", "chat-drawer")):
            template = (ROOT / "common" / "templates" / "common" / name).read_text(encoding="utf-8")
            with self.subTest(template=name):
                self.assertIn(f'<form id="{prefix}-send-form" class="chat-composer" novalidate>', template)
                self.assertIn('class="btn btn-icon btn-primary chat-composer-send"', template)
                self.assertIn('aria-label="ارسال"', template)


class SelectTests(SimpleTestCase):
    def test_dropdowns_wear_the_panel_theme(self):
        self.assertIn("@supports (appearance: base-select)", CSS)
        self.assertIn("::picker(select)", CSS)


class PlainErrorTests(SimpleTestCase):
    def test_the_frameworks_stiff_defaults_are_replaced(self):
        cleaned = persianise({
            "name": [ErrorDetail("این مقدار لازم است.", code="required")],
            "phone": [ErrorDetail("این مقدار نباید توهی باشد.", code="null")],
            "detail": ErrorDetail("شما اجازه انجام این دستور را ندارید.", code="permission_denied"),
        })
        self.assertEqual(cleaned["name"][0], "این فیلد را پر کنید.")
        self.assertEqual(cleaned["phone"][0], "این فیلد را پر کنید.")
        self.assertEqual(cleaned["detail"], "اجازهٔ این کار را ندارید.")

    def test_a_business_refusal_keeps_its_own_words(self):
        detail = ErrorDetail("مدیریت کاربران مجاز نیست.", code="permission_denied")
        self.assertEqual(persianise(detail), "مدیریت کاربران مجاز نیست.")

    def test_the_panels_own_messages_are_short(self):
        api = (JS / "core" / "api.js").read_text(encoding="utf-8")
        self.assertIn('403: "اجازهٔ این کار را ندارید."', api)
        self.assertIn('export const GENERIC_MESSAGE = "مشکلی پیش آمد؛ دوباره امتحان کنید.";', api)


class LoginErrorTests(TestCase):
    def test_a_wrong_password_says_so_plainly(self):
        User.objects.create_user(username="plain.login", password=PASSWORD, role=User.Role.SALES_MANAGER)
        response = APIClient().post(
            "/api/v1/auth/login/", {"username": "plain.login", "password": "wrong-password"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["non_field_errors"], ["نام کاربری یا رمز عبور اشتباه می‌باشد."])

    def test_an_empty_field_asks_to_be_filled(self):
        response = APIClient().post("/api/v1/auth/login/", {"username": "plain.login"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["password"], ["این فیلد را پر کنید."])
