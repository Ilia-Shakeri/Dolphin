"""Iran Post («بازار الکترونیک») shipping — client, provider, service and API.

The carrier is a real HTTP server this suite starts itself (the approach the
post-provider settings tests already use), so the token handshake, the
`api/v0` paths, the JSON bodies and the per-item `Errors` handling are all
exercised on the wire and not assumed.
"""

import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from auditlog.models import ActivityLog
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from integrations.models import Integration
from integrations.services import create_integration
from sales import ebazar, postal, shipping
from sales.models import EbazarProductLink, PostalShipment
from sales.services import (
    assign_lead,
    create_customer_with_phone,
    create_lead,
    create_product,
    mark_sale,
    register_sales_document,
)

PASSWORD = "Strong-pass-771!"


class FakeEbazar:
    """A tiny Ebazar: one token endpoint, one handler per `api/v0` path."""

    def __init__(self):
        self.calls = []
        self.token_requests = 0
        self.handlers = {}
        self.token_error = None
        self.revoke_next_token = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                if self.path == "/token":
                    outer.token_requests += 1
                    form = parse_qs(body)
                    if outer.token_error or form.get("password") != ["good-password"]:
                        return self._send(400, {"error": outer.token_error or "401"})
                    return self._send(200, {"access_token": f"tok-{outer.token_requests}", "expires_in": 3600})
                if outer.revoke_next_token:
                    outer.revoke_next_token = False
                    return self._send(401, {"Message": "expired"})
                auth = self.headers.get("Authorization", "")
                payload = json.loads(body or "{}")
                outer.calls.append((self.path, payload, auth))
                name = self.path.split("/api/v0/", 1)[-1]
                handler = outer.handlers.get(name)
                if handler is None:
                    return self._send(404, {"ResCode": 404, "ResMsg": "no such method"})
                return self._send(200, {"ResCode": 0, "ResMsg": "ok", "Data": handler(payload)})

            def _send(self, status, data):
                raw = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def paths(self):
        return [path.split("/api/v0/", 1)[-1] for path, _, _ in self.calls]


def standard_handlers(fake, *, parcel_code="RR123456789IR", status=0):
    fake.handlers.update({
        "BaseInfo/Province": lambda p: [{"Code": 1, "pName": "تهران", "eName": "Tehran"}, {"Code": 7, "pName": "فارس", "eName": "Fars"}],
        "BaseInfo/City": lambda p: [
            {"CityID": 101, "Code": 1, "pName": "تهران", "eName": "Tehran"},
            {"CityID": 102, "Code": 2, "pName": "ری", "eName": "Rey"},
        ] if p["ProvinceCode"] == 1 else [{"CityID": 701, "Code": 3, "pName": "شیراز", "eName": "Shiraz"}],
        "Order/DeliveryPrice": lambda p: [{"ClientOrderId": p[0]["ClientOrderId"], "ShippingCost": 900000, "ShippingTax": 81000, "ReturnShippingCost": 400000, "Errors": []}],
        "Product/Add": lambda p: [{"ClientProductID": p[0]["ClientProductID"], "EbazaarProductID": 555, "Succ": True, "Errors": []}],
        "Order/AddParcel": lambda p: [{
            "ClientOrderId": p[0]["ClientOrderId"], "Shenase": "SH-1", "ParcelCode": parcel_code,
            "ShippingCost": 900000, "ShippingCostTax": 81000, "Errors": [],
        }],
        "Order/Inquiry": lambda p: {},
        "Order/ParcelStatus": lambda p: [{"ParcelCode": c, "StatusCode": status, "Description": ""} for c in p],
        "Order/ChangeStatus": lambda p: [{"ParcelCode": c, "ResCode": 0, "Description": ""} for c in p["ParcelCodes"]],
        "Wallet/Credit": lambda p: {"Credit": 12000000},
    })


class ShippingBase(TestCase):
    def setUp(self):
        cache.clear()
        ebazar._TOKENS.clear()
        self.fake = FakeEbazar()
        self.addCleanup(self.fake.stop)
        standard_handlers(self.fake)
        self.admin = User.objects.create_user(username="ship-admin", password=PASSWORD, role=User.Role.PLATFORM_ADMIN)
        self.manager = User.objects.create_user(username="ship-manager", password=PASSWORD, role=User.Role.SALES_MANAGER)
        self.agent = User.objects.create_user(username="ship-agent", password=PASSWORD, role=User.Role.SALES_AGENT)
        self.integration = create_integration(
            actor=self.admin, provider_key="ebazar_post", name="پست",
            config={"base_url": self.fake.url}, secrets={"username": "shop", "password": "good-password"}, enabled=True,
        )
        self.customer = create_customer_with_phone(
            actor=self.agent, full_name="علی رضایی", province="تهران", city="تهران", postal_code="1234567890",
            address="خیابان آزادی، پلاک ۱", email="ali@example.com",
            phone={"raw_phone": "09121230001", "is_primary": True},
        )
        self.product = create_product(actor=self.manager, sku="P-1", name="کالای آزمایشی", current_price=Decimal("300000"))
        self.lead = create_lead(actor=self.agent, customer=self.customer, source="manual")
        assign_lead(actor=self.manager, lead=self.lead, to_user=self.agent, reason="shipping")
        self.sale = mark_sale(actor=self.agent, lead=self.lead, product=self.product, quantity=2, sold_at=timezone.now())
        self.document = register_sales_document(
            actor=self.manager, customer=self.customer, sale=self.sale, document_number="DOC-SHIP", postal_status="in_store",
        )

    def create(self, **overrides):
        terms = {"weight_grams": 1200, "service_type": 1, "pay_type": 1}
        terms.update(overrides)
        return shipping.create_shipment(actor=self.manager, document=self.document, **terms)


class ClientTests(ShippingBase):
    def test_the_token_is_fetched_once_and_reused_then_refreshed_after_a_401(self):
        client = shipping._client()[1]
        client.provinces()
        client.provinces()
        self.assertEqual(self.fake.token_requests, 1)
        self.assertTrue(all(auth == "bearer tok-1" for _, _, auth in self.fake.calls))
        self.fake.revoke_next_token = True
        client.provinces()
        self.assertEqual(self.fake.token_requests, 2)

    def test_a_wrong_password_is_a_readable_persian_error_and_never_echoed(self):
        client = ebazar.EbazarClient(base_url=self.fake.url, username="shop", password="wrong")
        with self.assertRaises(ebazar.EbazarError) as caught:
            client.token()
        self.assertNotIn("wrong", caught.exception.message)
        self.assertTrue(caught.exception.message)

    def test_paths_carry_the_documented_api_version(self):
        shipping._client()[1].provinces()
        self.assertEqual(self.fake.calls[0][0], "/api/v0/BaseInfo/Province")

    def test_a_per_item_error_is_found_even_when_the_call_succeeds(self):
        self.assertTrue(ebazar.item_errors({"Errors": [{"ErrorCode": 1, "ErrorMessage": "x"}]}))
        self.assertFalse(ebazar.item_errors({"Errors": []}))

    def test_status_mapping_moves_only_the_four_known_states(self):
        self.assertEqual(ebazar.dolphin_state_for(0), "in_store")
        self.assertEqual(ebazar.dolphin_state_for(2), "handed_to_post")
        self.assertEqual(ebazar.dolphin_state_for(5), "with_post")
        self.assertEqual(ebazar.dolphin_state_for(7), "out_for_delivery")
        self.assertIsNone(ebazar.dolphin_state_for(1))
        self.assertIsNone(ebazar.dolphin_state_for(9999))
        self.assertEqual(postal.carrier_for("ebazar").map_status("5"), "with_post")


class ProviderTests(ShippingBase):
    def test_secrets_are_encrypted_and_never_in_config(self):
        row = Integration.objects.get(provider_key="ebazar_post")
        self.assertNotIn("good-password", json.dumps(row.config))
        self.assertNotIn("good-password", row.secrets_token)
        self.assertNotIn("password", row.config)

    def test_connection_test_reports_the_wallet_credit(self):
        from integrations.services import test_integration
        result = test_integration(actor=self.admin, integration=self.integration)
        self.assertTrue(result.ok, result.message)
        self.assertIn("Wallet/Credit", self.fake.paths())

    def test_only_one_connection_is_allowed(self):
        with self.assertRaises(BusinessConflictError):
            create_integration(
                actor=self.admin, provider_key="ebazar_post", name="دوم",
                config={"base_url": self.fake.url}, secrets={"username": "a", "password": "b"},
            )


class PlaceTests(ShippingBase):
    def test_an_exact_province_and_city_are_resolved(self):
        self.assertEqual(shipping.resolve_place(self.document), {"province_code": 1, "city_id": 101})

    def test_persian_and_arabic_letter_variants_still_match(self):
        self.document.city_snapshot = "تهران"
        self.document.province_snapshot = "تهران"
        self.assertEqual(shipping.resolve_place(self.document)["city_id"], 101)
        self.document.city_snapshot = "شيراز"
        self.document.province_snapshot = "فارس"
        self.assertEqual(shipping.resolve_place(self.document)["city_id"], 701)

    def test_an_unknown_city_is_left_for_the_operator(self):
        self.document.city_snapshot = "ناکجاآباد"
        self.assertEqual(shipping.resolve_place(self.document), {})

    def test_lookups_are_cached(self):
        shipping.provinces()
        shipping.provinces()
        self.assertEqual(self.fake.paths().count("BaseInfo/Province"), 1)


class CreateShipmentTests(ShippingBase):
    def test_creation_registers_the_product_then_the_parcel_and_stores_the_barcode(self):
        shipment = self.create()
        self.assertEqual(shipment.parcel_code, "RR123456789IR")
        self.assertEqual(shipment.shenase, "SH-1")
        self.assertEqual(shipment.shipping_cost_rial, 900000)
        self.assertEqual(shipment.goods_price_rial, 600000)
        self.assertEqual(EbazarProductLink.objects.get(product=self.product).ebazar_product_id, "555")
        parcel = next(p for path, p, _ in self.fake.calls if path.endswith("Order/AddParcel"))[0]
        self.assertEqual(parcel["ClientOrderId"], shipment.pk)
        self.assertEqual(parcel["CityID"], 101)
        self.assertEqual(parcel["RegisterMobile"], "09121230001")
        self.assertEqual(parcel["RegisterFirstName"], "علی")
        self.assertEqual(parcel["RegisterLastName"], "رضایی")
        self.assertEqual(parcel["Products"][0]["Count"], 2)
        self.assertEqual(parcel["Products"][0]["EbazaarProductID"], 555)
        self.assertTrue(ActivityLog.objects.filter(operation="postal_shipment.created").exists())

    def test_the_product_is_registered_only_once(self):
        self.create()
        PostalShipment.objects.all().update(is_cancelled=True)
        self.create()
        self.assertEqual(self.fake.paths().count("Product/Add"), 1)

    def test_a_second_active_shipment_is_refused(self):
        self.create()
        with self.assertRaises(BusinessConflictError):
            self.create()

    def test_a_carrier_rejection_keeps_no_barcode_and_shows_the_reason(self):
        self.fake.handlers["Order/AddParcel"] = lambda p: [
            {"ClientOrderId": p[0]["ClientOrderId"], "ParcelCode": None, "Errors": [{"ErrorCode": 2001, "ErrorMessage": "bad postal code"}]}
        ]
        with self.assertRaises(BusinessRuleError) as caught:
            self.create()
        self.assertIn("post", caught.exception.detail if hasattr(caught.exception, "detail") else str(caught.exception))
        shipment = PostalShipment.objects.get()
        self.assertEqual(shipment.parcel_code, "")

    def test_a_retry_after_a_lost_answer_adopts_the_registered_parcel_instead_of_duplicating(self):
        self.fake.handlers["Order/AddParcel"] = lambda p: [{"ClientOrderId": p[0]["ClientOrderId"], "ParcelCode": None, "Errors": [{"ErrorCode": 1, "ErrorMessage": "lost"}]}]
        with self.assertRaises(BusinessRuleError):
            self.create()
        pending = PostalShipment.objects.get()
        self.fake.handlers["Order/Inquiry"] = lambda p: {"ParcelCode": "RR999IR", "ParcelShenase": "SH-9", "Postalprice": 800000, "PostalpriceTax": 72000}
        again = self.create()
        self.assertEqual(again.pk, pending.pk)
        self.assertEqual(again.parcel_code, "RR999IR")
        self.assertEqual(PostalShipment.objects.count(), 1)

    def test_the_documented_limits_are_enforced_before_any_call(self):
        for terms in (
            {"weight_grams": 30001},
            {"weight_grams": 6000, "service_type": 0},
            {"service_type": 9},
            {"pay_type": 5},
        ):
            with self.assertRaises(BusinessRuleError):
                self.create(**terms)
        self.assertEqual(self.fake.calls, [])

    def test_missing_recipient_facts_are_named_and_not_invented(self):
        self.customer.email = ""
        self.customer.save(update_fields=["email"])
        with self.assertRaises(BusinessRuleError) as caught:
            self.create()
        self.assertIn("ایمیل", str(caught.exception.args))
        self.assertNotIn("Order/AddParcel", self.fake.paths())
        shipment = self.create(recipient_email="ali@example.com")
        self.assertTrue(shipment.parcel_code)

    def test_an_unresolvable_city_asks_for_a_choice_and_a_chosen_city_works(self):
        self.document.city_snapshot = "ناکجاآباد"
        self.document.save(update_fields=["city_snapshot"])
        with self.assertRaises(BusinessRuleError):
            self.create()
        self.assertTrue(self.create(city_id=102).parcel_code)

    def test_no_connection_is_a_clear_refusal(self):
        Integration.objects.all().update(enabled=False)
        with self.assertRaises(BusinessRuleError):
            self.create()

    def test_a_document_without_a_product_sale_is_refused(self):
        self.document.sale = None
        self.document.save(update_fields=["sale"])
        with self.assertRaises(BusinessRuleError):
            self.create()

    def test_kiosk_and_pudo_are_mutually_exclusive(self):
        with self.assertRaises(BusinessRuleError):
            self.create(kiosk_id=1, pudo_id=2)

    def test_quote_registers_nothing(self):
        result = shipping.quote(actor=self.manager, document=self.document, weight_grams=1200, service_type=1, pay_type=1)
        self.assertEqual(result["shipping_cost"], 900000)
        self.assertFalse(PostalShipment.objects.exists())
        self.assertNotIn("Order/AddParcel", self.fake.paths())


class PermissionTests(ShippingBase):
    def test_an_agent_without_the_capability_cannot_ship(self):
        with self.assertRaises(BusinessPermissionDenied):
            shipping.create_shipment(actor=self.agent, document=self.document, weight_grams=1000, service_type=1, pay_type=1)
        self.assertEqual(self.fake.calls, [])

    def test_the_feature_gate_is_enforced(self):
        from common.deployment.profile import DeploymentProfile, override_active_profile
        from common.deployment.registry import ALL_FEATURES
        profile = DeploymentProfile(profile_id="c", features=frozenset(ALL_FEATURES) - {"sales_documents"}, source="signed-manifest")
        with override_active_profile(profile):
            with self.assertRaises(BusinessPermissionDenied):
                self.create()


class StatusTests(ShippingBase):
    def test_refresh_moves_a_mapped_state_forward_and_records_the_raw_status(self):
        shipment = self.create()
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 5, "Description": ""} for c in p]
        shipping.refresh_shipment(shipment, actor=self.manager)
        shipment.refresh_from_db()
        self.document.refresh_from_db()
        self.assertEqual(shipment.carrier_status_code, 5)
        self.assertEqual(self.document.postal_status, "with_post")

    def test_an_unmapped_status_never_moves_the_document(self):
        shipment = self.create()
        before = self.document.postal_status
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 9, "Description": ""} for c in p]
        shipping.refresh_shipment(shipment, actor=self.manager)
        shipment.refresh_from_db()
        self.document.refresh_from_db()
        self.assertEqual(shipment.carrier_status_code, 9)
        self.assertEqual(self.document.postal_status, before)

    def test_the_document_never_moves_backwards(self):
        shipment = self.create()
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 7, "Description": ""} for c in p]
        shipping.refresh_shipment(shipment, actor=self.manager)
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 2, "Description": ""} for c in p]
        shipping.refresh_shipment(shipment, actor=self.manager)
        self.document.refresh_from_db()
        self.assertEqual(self.document.postal_status, "out_for_delivery")

    def test_cancelling_marks_the_shipment_and_frees_the_document(self):
        shipment = self.create()
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 1, "Description": ""} for c in p]
        shipping.change_shipment(actor=self.manager, shipment=shipment, action="cancel")
        shipment.refresh_from_db()
        self.assertTrue(shipment.is_cancelled)
        self.assertEqual(self.fake.calls[-2][1]["NewStatus"], 1)
        self.assertTrue(self.create().parcel_code)

    def test_the_worker_job_refreshes_open_shipments_only(self):
        open_one = self.create()
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 5, "Description": ""} for c in p]
        self.assertEqual(shipping.sync_open_shipments(), 1)
        open_one.refresh_from_db()
        self.assertEqual(open_one.carrier_status_code, 5)
        PostalShipment.objects.update(carrier_status_code=7)
        self.assertEqual(shipping.sync_open_shipments(), 0)

    def test_carrier_track_answers_in_the_products_states(self):
        shipment = self.create()
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 2, "Description": ""} for c in p]
        self.assertEqual(postal.carrier_for("ebazar").track(shipment.parcel_code)[0], "handed_to_post")


class ApiTests(ShippingBase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.manager)
        self.base = f"/api/v1/sales-documents/{self.document.pk}"

    def test_create_then_read_then_refresh_then_cancel(self):
        made = self.api.post(f"{self.base}/shipment-create/", {"weight_grams": 1200, "service_type": 1, "pay_type": 1}, format="json")
        self.assertEqual(made.status_code, 201, made.data)
        self.assertEqual(made.data["parcel_code"], "RR123456789IR")
        listed = self.api.get(f"{self.base}/shipments/")
        self.assertTrue(listed.data["connected"])
        self.assertEqual(len(listed.data["results"]), 1)
        refreshed = self.api.post(f"{self.base}/shipment-refresh/")
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.fake.handlers["Order/ParcelStatus"] = lambda p: [{"ParcelCode": c, "StatusCode": 1, "Description": ""} for c in p]
        cancelled = self.api.post(f"{self.base}/shipment-change/", {"action": "cancel"}, format="json")
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        self.assertTrue(cancelled.data["is_cancelled"])

    def test_validation_and_unknown_fields(self):
        bad = self.api.post(f"{self.base}/shipment-create/", {"weight_grams": 0, "service_type": 1, "pay_type": 1}, format="json")
        self.assertEqual(bad.status_code, 400)
        bad = self.api.post(f"{self.base}/shipment-change/", {"action": "explode"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_an_agent_cannot_create(self):
        agent_api = APIClient()
        agent_api.force_authenticate(self.agent)
        response = agent_api.post(f"{self.base}/shipment-create/", {"weight_grams": 1200, "service_type": 1, "pay_type": 1}, format="json")
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(PostalShipment.objects.exists())

    def test_places_endpoints(self):
        provinces = self.api.get("/api/v1/sales-documents/shipping-places/")
        self.assertEqual(provinces.status_code, 200, getattr(provinces, "data", None))
        self.assertEqual(provinces.data["results"][0]["Code"], 1)
        cities = self.api.get("/api/v1/sales-documents/shipping-places/", {"province": "1"})
        self.assertEqual(cities.data["results"][0]["CityID"], 101)
        bad = self.api.get("/api/v1/sales-documents/shipping-places/", {"province": "x"})
        self.assertEqual(bad.status_code, 400)

    def test_no_secret_reaches_any_response_or_log(self):
        made = self.api.post(f"{self.base}/shipment-create/", {"weight_grams": 1200, "service_type": 1, "pay_type": 1}, format="json")
        self.assertNotIn("good-password", json.dumps(made.data))
        from integrations.models import IntegrationLog
        for row in IntegrationLog.objects.all():
            self.assertNotIn("good-password", row.message + json.dumps(row.payload))
        for row in ActivityLog.objects.all():
            self.assertNotIn("good-password", json.dumps(row.safe_changes))


class UiTests(ShippingBase):
    def test_card_is_shown_to_managers_only(self):
        url = f"/sales-documents/{self.document.pk}/"
        self.client.force_login(self.manager)
        page = self.client.get(url)
        self.assertContains(page, 'id="postal-shipment-card"')
        self.assertContains(page, "postal-shipment.js")
        self.client.force_login(self.agent)
        agent_page = self.client.get(url)
        self.assertNotContains(agent_page, 'id="postal-shipment-card"')

    def test_post_settings_page_carries_the_guide(self):
        self.client.force_login(self.admin)
        page = self.client.get("/settings/post-provider/")
        self.assertContains(page, 'id="post-guide"')
        self.assertContains(page, "بازار الکترونیک")
