"""What the attachments panel tells a person before they pick a file.

Product-owner request 2026-09-19: «قسمت پیوست ها در تمامی صفحه ها باید یک توضیح
کوتاه داشته باشد و حداکثر حجم و فرمت های محدود برای اپلود داشته باشد».

The rules themselves are not new and are not decided here — they were decided
2026-09-03 and live in `attachments/`: four content types, ten megabytes per
file. What was missing is that the panel never said so, and never checked:
a person could pick a thirty-megabyte file, wait for it to upload, and only
then be told it was never allowed.

The one thing worth guarding, then, is that the sentence and the check read
the *same* source as the server. A megabyte figure typed into a template is
correct exactly until someone changes `ATTACHMENT_MAX_BYTES`, and then it is a
lie printed above a form. So these tests change the setting and assert the
rendered panel moves with it.
"""

import pathlib

from django.template import Context, Template
from django.test import SimpleTestCase, override_settings

from attachments.models import ALLOWED_CONTENT_TYPES, DEFAULT_MAX_ATTACHMENT_BYTES


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "common" / "static" / "common" / "dolphin-app.js").read_text(encoding="utf-8")
PANEL = (
    ROOT / "common" / "templates" / "common" / "includes" / "attachments_panel.inc"
).read_text(encoding="utf-8")
DETAIL_PAGES = sorted(
    path for path in (ROOT / "common" / "templates" / "common").rglob("*.html")
    if "common/includes/attachments_panel.inc" in path.read_text(encoding="utf-8")
)


def _function_body(name):
    start = SCRIPT.index(f"function {name}(")
    following = SCRIPT.find("\n    function ", start + 1)
    return SCRIPT[start:following if following != -1 else len(SCRIPT)]


def _render(template_text, context=None):
    return Template(template_text).render(Context(context or {}))


class AttachmentTagTests(SimpleTestCase):
    def test_the_accept_list_is_the_types_the_server_validates(self):
        rendered = _render("{% load attachment_tags %}{% attachment_accept %}")
        self.assertEqual(set(rendered.split(",")), set(ALLOWED_CONTENT_TYPES))

    def test_the_ceiling_is_the_one_the_service_enforces(self):
        rendered = _render("{% load attachment_tags %}{% attachment_max_bytes %}")
        self.assertEqual(int(rendered), DEFAULT_MAX_ATTACHMENT_BYTES)

    def test_the_readable_ceiling_follows_the_setting(self):
        """The whole reason this is a tag and not a typed number."""
        with override_settings(ATTACHMENT_MAX_BYTES=5 * 1024 * 1024):
            rendered = _render("{% load attachment_tags %}{% attachment_max_label %}")
        self.assertIn("۵", rendered)
        self.assertIn("مگابایت", rendered)

    def test_the_ceiling_never_claims_more_than_the_database_allows(self):
        """`max_attachment_bytes()` clamps to the model's own CheckConstraint;
        a setting above it must not be advertised."""
        with override_settings(ATTACHMENT_MAX_BYTES=500 * 1024 * 1024):
            rendered = _render("{% load attachment_tags %}{% attachment_max_bytes %}")
        self.assertEqual(int(rendered), DEFAULT_MAX_ATTACHMENT_BYTES)

    def test_every_accepted_type_is_named_in_the_sentence(self):
        rendered = _render("{% load attachment_tags %}{% attachment_types_label %}")
        for name in ("PDF", "JPG", "PNG", "WebP"):
            with self.subTest(type=name):
                self.assertIn(name, rendered)


class AttachmentPanelMarkupTests(SimpleTestCase):
    def test_the_panel_carries_a_short_explanation(self):
        rendered = _render(PANEL, {"attachments_field": "customer", "can_upload": True})
        self.assertIn("حجم هر فایل حداکثر", rendered)
        self.assertIn("۱۰ مگابایت", rendered)
        self.assertIn("PDF", rendered)

    def test_the_limits_reach_the_browser_as_data_not_as_prose(self):
        """`attachmentRejectionReason` reads these; a sentence it had to parse
        would be a second place the rule could drift."""
        rendered = _render(PANEL, {"attachments_field": "customer", "can_upload": True})
        self.assertIn(f'data-attachments-max-bytes="{DEFAULT_MAX_ATTACHMENT_BYTES}"', rendered)
        self.assertIn("data-attachments-accept=", rendered)

    def test_the_file_input_hints_the_same_types(self):
        rendered = _render(PANEL, {"attachments_field": "customer", "can_upload": True})
        for content_type in ALLOWED_CONTENT_TYPES:
            with self.subTest(type=content_type):
                self.assertIn(content_type, rendered)

    def test_a_reader_who_cannot_upload_still_sees_the_rules(self):
        """The explanation sits above the form, not inside it, so a role
        without upload rights still understands what the list below holds."""
        rendered = _render(PANEL, {"attachments_field": "customer", "can_upload": False})
        self.assertIn("حجم هر فایل حداکثر", rendered)
        self.assertNotIn("افزودن پیوست", rendered)

    def test_the_rules_are_announced_to_a_screen_reader_too(self):
        rendered = _render(PANEL, {"attachments_field": "customer", "can_upload": True})
        self.assertIn('aria-describedby="attachments-rules-customer"', rendered)
        self.assertIn('id="attachments-rules-customer"', rendered)

    def test_every_page_with_attachments_gets_this_one_panel(self):
        """Five detail pages share it, so «در تمامی صفحه ها» is one edit."""
        self.assertGreaterEqual(len(DETAIL_PAGES), 5)


class AttachmentPreflightTests(SimpleTestCase):
    def test_an_oversized_file_is_refused_before_it_is_sent(self):
        body = _function_body("attachmentRejectionReason")
        self.assertIn("panel.dataset.attachmentsMaxBytes", body)
        self.assertIn("file.size > maxBytes", body)

    def test_the_refusal_says_how_big_the_file_actually_is(self):
        """«از سقف بیشتر است» alone leaves the person guessing by how much."""
        body = _function_body("attachmentRejectionReason")
        self.assertIn("file.size / (1024 * 1024)", body)

    def test_a_wrong_type_is_refused_by_the_accept_list_not_by_extension(self):
        body = _function_body("attachmentRejectionReason")
        self.assertIn("panel.dataset.attachmentsAccept", body)
        self.assertNotIn(".pdf", body)

    def test_a_browser_that_guessed_no_type_is_left_to_the_server(self):
        """`file.type` can be empty. Refusing on an empty guess would block a
        file the server would have accepted after reading its real bytes."""
        body = _function_body("attachmentRejectionReason")
        self.assertIn("file.type &&", body)

    def test_the_reason_lands_in_the_panels_own_error_slot(self):
        body = _function_body("setupAttachmentsPanel")
        self.assertIn('[data-error-for="file"]', body)
        self.assertIn("attachmentRejectionReason(panel, file)", body)

    def test_nothing_is_uploaded_when_the_check_refuses(self):
        body = _function_body("setupAttachmentsPanel")
        refusal = body.split("if (reason) {")[1].split("}")[0]
        self.assertIn("return", refusal)
