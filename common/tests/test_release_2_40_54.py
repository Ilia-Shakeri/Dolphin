"""2.40.54 — personalization, part two: saved list views and richer SMS templates.

Owner decision 2026-10-14 (Q18): saved table views, personal or for the team,
and advanced SMS templates with more variables — both inside the
`customization` feature.
"""

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.access import has_any_capability
from accounts.models import User
from common.deployment.profile import DeploymentProfile, override_active_profile
from common.deployment.registry import ALL_FEATURES
from common.exceptions import BusinessPermissionDenied, BusinessRuleError
from communications import sms
from communications.models import OutboundSMS
from communications.services import render_sms_template, send_outbound_sms, sms_template_tokens
from customization import saved_views, services
from customization.models import SavedView
from sales.services import create_customer_with_phone

PASSWORD = "Strong-pass-954!"
PAGE = "customers:customer-search-form"


def without_customization():
    return DeploymentProfile(profile_id="client-1", features=frozenset(ALL_FEATURES) - {"customization"}, source="signed-manifest")


class SavedViewTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="v.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="v.agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.other = User.objects.create_user(username="v.other", password=PASSWORD, role=User.Role.SALES_AGENT)

    def test_personal_and_shared_views(self):
        self.assertTrue(has_any_capability(self.manager, "views.share"))
        self.assertFalse(has_any_capability(self.agent, "views.share"))
        mine = saved_views.save_view(actor=self.agent, page=PAGE, name="تهرانی‌ها", state={"customer-province-filter": "تهران"})
        with self.assertRaises(BusinessPermissionDenied):
            saved_views.save_view(actor=self.agent, page=PAGE, name="همه", state={}, shared=True)
        team = saved_views.save_view(actor=self.manager, page=PAGE, name="فعال‌ها", state={"customer-active-filter": "true"}, shared=True)
        self.assertEqual({view.pk for view in saved_views.views_for(self.agent, PAGE)}, {mine.pk, team.pk})
        self.assertEqual({view.pk for view in saved_views.views_for(self.other, PAGE)}, {team.pk})
        # The same name again overwrites one's own.
        again = saved_views.save_view(actor=self.agent, page=PAGE, name="تهرانی‌ها", state={"customer-city-filter": "تهران"})
        self.assertEqual(again.pk, mine.pk)
        self.assertEqual(SavedView.objects.get(pk=mine.pk).state, {"customer-city-filter": "تهران"})
        with self.assertRaises(BusinessPermissionDenied):
            saved_views.delete_view(actor=self.other, view=mine)
        with self.assertRaises(BusinessPermissionDenied):
            saved_views.delete_view(actor=self.other, view=team)
        for bad in ({"page": "Customers!"}, {"state": {"a b": "x"}}, {"name": "  "}):
            with self.assertRaises(BusinessRuleError):
                saved_views.save_view(actor=self.agent, **{"page": PAGE, "name": "x", "state": {}, **bad})

    def test_the_api(self):
        client = APIClient()
        client.force_authenticate(self.agent)
        made = client.post("/api/v1/saved-views/", {"page": PAGE, "name": "شخصی", "state": {"customer-search": "علی"}}, format="json")
        self.assertEqual(made.status_code, 201, made.content)
        listed = client.get("/api/v1/saved-views/", {"page": PAGE}).json()
        self.assertEqual((listed["can_share"], [view["name"] for view in listed["views"]]), (False, ["شخصی"]))
        self.assertEqual(client.delete(f"/api/v1/saved-views/{made.json()['id']}/").status_code, 204)
        with override_active_profile(without_customization()):
            self.assertEqual(client.get("/api/v1/saved-views/", {"page": PAGE}).status_code, 404)

    def test_the_page_offers_it_only_with_the_feature(self):
        self.client.force_login(self.agent)
        self.assertContains(self.client.get("/customers/"), 'data-saved-views="1"')
        with override_active_profile(without_customization()):
            self.assertNotContains(self.client.get("/customers/"), 'data-saved-views="1"')


class SmsTemplateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="t.admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="t.manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.level = services.create_definition(actor=self.admin, entity="customer", label="سطح", field_type="choice", choices=["طلایی", "نقره‌ای"])
        services.create_definition(actor=self.admin, entity="customer", label="تولد", field_type="date")
        self.customer = create_customer_with_phone(
            actor=self.manager, full_name="مریم احمدی", city="شیراز", province="فارس",
            phone={"raw_phone": "09129990081", "is_primary": True},
            custom_fields={"cf_1": "طلایی", "cf_2": "2026-03-21"},
        )

    def test_more_tokens_with_the_feature(self):
        text = render_sms_template("{نام} از {شهر}، {استان}؛ سطح {سطح}، تولد {تولد}، {تلفن}", customer=self.customer)
        self.assertEqual(text, "مریم احمدی از شیراز، فارس؛ سطح طلایی، تولد ۱۴۰۵/۰۱/۰۱، 09129990081")
        tokens = [token for token, _ in sms_template_tokens()]
        self.assertIn("{سطح}", tokens)
        self.assertIn("{امروز}", tokens)
        with override_active_profile(without_customization()):
            self.assertEqual(render_sms_template("{نام} {شهر}", customer=self.customer), "مریم احمدی {شهر}")
            self.assertEqual([token for token, _ in sms_template_tokens()], ["{نام}"])

    def test_a_single_send_fills_the_template(self):
        with mock.patch.object(sms, "provider_is_available", return_value=True), mock.patch.object(
            sms, "send_via_configured_provider", return_value=sms.SmsSendResult(provider_code="http", success=True, status_detail="200"),
        ) as sender:
            send_outbound_sms(actor=self.manager, body="سلام {نام}، سطح شما {سطح} است.", customer=self.customer)
        self.assertEqual(sender.call_args.kwargs["body"], "سلام مریم احمدی، سطح شما طلایی است.")
        self.assertEqual(OutboundSMS.objects.get().body_text, "سلام مریم احمدی، سطح شما طلایی است.")

    def test_the_sms_page_lists_the_tokens(self):
        self.client.force_login(self.manager)
        page = self.client.get("/sms/")
        self.assertContains(page, 'id="sms-template-tokens"')
        self.assertContains(page, "{سطح}")
