"""«سایر» is written out (2.40.22).

Ticking «سایر» as a way of reaching people requires saying what it is — one
or several — and the campaign shows those words where it would have shown
«سایر». Without «سایر» nothing of it is kept.
"""

from pathlib import Path

from django.test import SimpleTestCase, TestCase

from accounts.models import User
from common.exceptions import BusinessRuleError
from sales.campaigns import channel_labels, create_campaign, update_campaign

ROOT = Path(__file__).resolve().parents[2]


class OtherChannelsTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="oc.manager", password="Strong-pass-661!", role=User.Role.SALES_MANAGER)

    def test_other_requires_its_name(self):
        with self.assertRaises(BusinessRuleError) as raised:
            create_campaign(actor=self.manager, name="بی‌نام", channels=["phone", "other"])
        self.assertIn("other_channels", raised.exception.detail)

    def test_several_names_are_kept_and_shown_in_place_of_other(self):
        campaign = create_campaign(
            actor=self.manager, name="بیلبورد", channels=["phone", "other"], other_channels=["بیلبورد", " رادیو ", "بیلبورد"],
        )
        self.assertEqual(campaign.other_channels, ["بیلبورد", "رادیو"])
        self.assertEqual(channel_labels(campaign), ["تماس تلفنی", "بیلبورد", "رادیو"])

    def test_without_other_nothing_is_kept(self):
        campaign = create_campaign(actor=self.manager, name="فقط تلفن", channels=["phone"], other_channels=["بیلبورد"])
        self.assertEqual(campaign.other_channels, [])
        campaign = create_campaign(actor=self.manager, name="با سایر", channels=["other"], other_channels=["رادیو"])
        campaign = update_campaign(actor=self.manager, campaign=campaign, channels=["sms"])
        self.assertEqual(campaign.other_channels, [])


class WizardWordingTests(SimpleTestCase):
    def test_the_two_hint_sentences_are_gone(self):
        text = (ROOT / "common" / "templates" / "common" / "campaigns" / "list.html").read_text(encoding="utf-8")
        self.assertNotIn("یک یا چند مورد را تیک بزنید", text)
        self.assertNotIn("هر کسی را که می‌خواهید تیک بزنید", text)
        self.assertIn('name="other_channels"', text)
        detail = (ROOT / "common" / "templates" / "common" / "campaigns" / "detail.html").read_text(encoding="utf-8")
        self.assertIn('name="other_channels"', detail)
