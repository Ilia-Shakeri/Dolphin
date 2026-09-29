"""Registering a sales document's parcel with Iran Post (Ebazar) and following it.

The one place that turns a `SalesDocument` into carrier calls and carrier
answers into rows. Three separate controls apply, as everywhere: the
`sales_documents` feature, the `sales_documents.manage` capability, and the
document's own data scope (the view hands in only a document the actor may
see). The connection itself is an `Integration` of kind `ebazar_post`, whose
credentials are encrypted and read only here.

Where the parcel is, in Dolphin's four states, is still moved only by
`sales.services.transition_postal_status`; the carrier's own status code and
words are stored beside it, so a status the four states cannot express (a
return, a cancellation) is shown in the provider's words instead of guessed.
"""

import logging
import math

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from accounts.access import has_any_capability
from auditlog.services import log_activity
from common.deployment.profile import feature_enabled
from common.request_context import current_request_context
from common.exceptions import BusinessConflictError, BusinessPermissionDenied, BusinessRuleError
from integrations.crypto import SecretsUnavailable
from integrations.models import Integration
from integrations.providers.ebazar import client_for
from integrations.services import record_health, secrets_of
from sales import ebazar, postal
from sales.models import EbazarProductLink, PostalShipment, SalesDocument
from sales.services import transition_postal_status

logger = logging.getLogger("dolphin.sales.shipping")

PROVIDER_KEY = "ebazar_post"
LOCATION_CACHE_SECONDS = 7 * 24 * 3600
MIN_GOODS_PRICE_RIAL = 50_000
MAX_WEIGHT_GRAMS = 30_000
EXPRESS_ONLY_ABOVE_GRAMS = 5_000
#: Ebazar keeps a stock count per product; Dolphin's own inventory is the
#: truth, so the count sent is large enough never to be the reason a parcel
#: is refused.
PRODUCT_STOCK_COUNT = 100_000
CHANGE_STATUS = {"hold": 0, "cancel": 1, "ready": 2}


def _require_access(actor):
    if not feature_enabled("sales_documents"):
        raise BusinessPermissionDenied("این بخش در این استقرار فعال نیست.")
    if not has_any_capability(actor, "sales_documents.manage"):
        raise BusinessPermissionDenied("ثبت و پیگیری مرسولهٔ پستی مجاز نیست.")


def active_integration():
    return Integration.objects.filter(provider_key=PROVIDER_KEY, enabled=True).first()


def is_connected():
    return active_integration() is not None


def _client():
    integration = active_integration()
    if integration is None:
        raise BusinessRuleError({"post": "اتصال پست ایران (بازار الکترونیک) تنظیم یا فعال نشده است."})
    try:
        secrets = secrets_of(integration)
    except SecretsUnavailable as error:
        raise BusinessRuleError({"post": "گذرواژهٔ ذخیره‌شدهٔ اتصال پست با کلید فعلی باز نمی‌شود؛ دوباره واردش کنید."}) from error
    try:
        return integration, client_for(integration.config, secrets)
    except ebazar.EbazarError as error:
        raise BusinessRuleError({"post": error.message}) from error


def _call(integration, fn):
    """Run one carrier call; record its health; a failure is a plain message."""
    try:
        result = fn()
    except ebazar.EbazarError as error:
        record_health(integration, False, error.message)
        raise BusinessRuleError({"post": error.message}) from error
    record_health(integration, True)
    return result


# --- places ----------------------------------------------------------------------


def provinces():
    _, client = _client()
    return cache.get_or_set("ebazar:provinces", lambda: client.provinces(), LOCATION_CACHE_SECONDS)


def cities(province_code):
    _, client = _client()
    return cache.get_or_set(
        f"ebazar:cities:{int(province_code)}", lambda: client.cities(int(province_code)), LOCATION_CACHE_SECONDS
    )


def resolve_place(document):
    """`{province_code, city_id}` from the document's address text, or `{}`.

    A name that matches more than one city, or none, is left unresolved: the
    operator picks it, because a parcel sent to the wrong same-named city is
    worse than one more click.
    """
    province_name = ebazar.normalize_name(document.province_snapshot)
    city_name = ebazar.normalize_name(document.city_snapshot)
    if not province_name or not city_name:
        return {}
    found = [p for p in provinces() if ebazar.normalize_name(p.get("pName")) == province_name]
    if len(found) != 1:
        return {}
    matches = [c for c in cities(found[0]["Code"]) if ebazar.normalize_name(c.get("pName")) == city_name]
    if len(matches) != 1:
        return {}
    return {"province_code": found[0]["Code"], "city_id": matches[0]["CityID"]}


# --- building the request ---------------------------------------------------------


def _recipient(document, email):
    customer = document.customer
    words = customer.full_name.split()
    first, last = (" ".join(words[:-1]), words[-1]) if len(words) > 1 else (customer.full_name, customer.full_name)
    phone = customer.phones.filter(is_active=True).order_by("-is_primary", "id").first()
    mobile = ""
    if phone is not None and phone.normalized_phone.startswith("+98"):
        mobile = "0" + phone.normalized_phone[3:]
    return {
        "RegisterFirstName": first or customer.full_name,
        "RegisterLastName": last or customer.full_name,
        "RegisterMobile": mobile,
        "RegisterPhoneNumber": mobile,
        "RegisterEmail": (email or customer.email or "").strip(),
        "RegisterAddress": document.address_snapshot,
        "RegisterPostalCode": document.postal_code_snapshot,
    }


def _sale_of(document):
    sale = document.sale
    if sale is None or sale.product_id is None or sale.status != "confirmed":
        raise BusinessRuleError({"document": "این سند به فروشِ تأییدشده‌ای با کالا وصل نیست؛ مرسوله بدون کالا ثبت نمی‌شود."})
    return sale


def _check_terms(*, weight_grams, service_type, pay_type, goods_price):
    if service_type not in ebazar.SERVICE_TYPES:
        raise BusinessRuleError({"service_type": "نوع سرویس نامعتبر است."})
    if pay_type not in ebazar.PAY_TYPES:
        raise BusinessRuleError({"pay_type": "نوع پرداخت نامعتبر است."})
    if not 1 <= weight_grams <= MAX_WEIGHT_GRAMS:
        raise BusinessRuleError({"weight_grams": "وزن مرسوله باید بین ۱ تا ۳۰٬۰۰۰ گرم باشد."})
    if weight_grams > EXPRESS_ONLY_ABOVE_GRAMS and service_type != 1:
        raise BusinessRuleError({"service_type": "مرسولهٔ بیش از ۵۰۰۰ گرم باید «پیشتاز» ارسال شود."})
    if goods_price < MIN_GOODS_PRICE_RIAL:
        raise BusinessRuleError({"document": "ارزش کالا کمتر از حداقل مجاز پست (۵۰٬۰۰۰ ریال) است."})


def _options(integration, *, sms_service, pod, box_size_id, kiosk_id, pudo_id):
    config = integration.config
    options = {
        "SMSService": bool(config.get("sms_service")) if sms_service is None else bool(sms_service),
        "Pod": bool(config.get("pod")) if pod is None else bool(pod),
    }
    if box_size_id:
        options["BoxSizeID"] = int(box_size_id)
    if kiosk_id and pudo_id:
        raise BusinessRuleError({"kiosk_id": "کیوسک و پستی‌گاه را هم‌زمان انتخاب نکنید."})
    if kiosk_id:
        options["KioskID"] = int(kiosk_id)
    if pudo_id:
        options["PudoPostnodeID"] = int(pudo_id)
    return options


def _resolve_city(document, city_id):
    if city_id:
        return int(city_id)
    place = resolve_place(document)
    if not place:
        raise BusinessRuleError({"city_id": "شهر این نشانی با فهرست پست تطبیق داده نشد؛ شهر را از فهرست انتخاب کنید."})
    return int(place["city_id"])


# --- quote -------------------------------------------------------------------------


def quote(*, actor, document, weight_grams, service_type, pay_type, city_id=None,
          sms_service=None, pod=None, box_size_id=None, kiosk_id=None, pudo_id=None):
    """Postage for this document's goods, without registering anything."""
    _require_access(actor)
    sale = _sale_of(document)
    goods_price = int(sale.total_amount)
    _check_terms(weight_grams=weight_grams, service_type=service_type, pay_type=pay_type, goods_price=goods_price)
    integration, client = _client()
    item = {
        "ClientOrderId": document.pk,
        "CityID": _resolve_city(document, city_id),
        "Price": goods_price,
        "Weight": weight_grams,
        "ServiceType": service_type,
        "PayType": pay_type,
        "NonStandardPackage": weight_grams > 2600,
        **_options(integration, sms_service=sms_service, pod=pod, box_size_id=box_size_id, kiosk_id=kiosk_id, pudo_id=pudo_id),
    }
    items = _call(integration, lambda: client.delivery_price([item]))
    result = items[0] if items else {}
    problems = ebazar.item_errors(result)
    if problems or "ShippingCost" not in result:
        raise BusinessRuleError({"post": " — ".join(problems) or "پست هزینهٔ ارسال را برنگرداند."})
    return {
        "shipping_cost": result.get("ShippingCost"),
        "shipping_tax": result.get("ShippingTax"),
        "return_shipping_cost": result.get("ReturnShippingCost"),
        "goods_price": goods_price,
    }


# --- create ------------------------------------------------------------------------


def _ensure_product_link(integration, client, product, *, unit_weight, price):
    link = EbazarProductLink.objects.filter(product=product).first()
    if link is not None:
        return link
    item = {
        "ClientProductID": product.pk,
        "Name": product.name[:70],
        "Price": price,
        "PercentDiscount": 0,
        "Weight": unit_weight,
        "Count": PRODUCT_STOCK_COUNT,
        "Enabled": True,
        "Visible": False,
        "IsStandard": True,
        "IsPocket": False,
        "Description": (product.description or "")[:4000],
    }
    results = _call(integration, lambda: client.product_add([item]))
    result = results[0] if results else {}
    problems = ebazar.item_errors(result)
    if problems or not result.get("EbazaarProductID"):
        raise BusinessRuleError({"post": "ثبت کالا در بازار الکترونیک ناموفق بود: " + (" — ".join(problems) or "شناسهٔ کالا برنگشت.")})
    return EbazarProductLink.objects.create(
        product=product, ebazar_product_id=str(result["EbazaarProductID"]), unit_weight_grams=unit_weight
    )


def active_shipment(document):
    return document.shipments.filter(is_cancelled=False).order_by("-created_at", "-id").first()


def create_shipment(*, actor, document, weight_grams, service_type, pay_type, city_id=None,
                    recipient_email="", client_ip="", sms_service=None, pod=None,
                    box_size_id=None, kiosk_id=None, pudo_id=None):
    """Register the parcel with the carrier and keep the barcode it issues."""
    _require_access(actor)
    document = SalesDocument.objects.select_related("customer", "sale", "sale__product").get(pk=document.pk)
    if not document.is_active:
        raise BusinessConflictError({"is_active": "برای سند غیرفعال مرسوله ثبت نمی‌شود."})
    sale = _sale_of(document)
    goods_price = int(sale.total_amount)
    _check_terms(weight_grams=weight_grams, service_type=service_type, pay_type=pay_type, goods_price=goods_price)
    integration, client = _client()
    city = _resolve_city(document, city_id)
    options = _options(integration, sms_service=sms_service, pod=pod, box_size_id=box_size_id, kiosk_id=kiosk_id, pudo_id=pudo_id)
    recipient = _recipient(document, recipient_email)
    missing = [
        label for key, label in (
            ("RegisterMobile", "شمارهٔ موبایل مشتری"), ("RegisterEmail", "ایمیل گیرنده"),
        ) if not recipient[key]
    ]
    if "KioskID" not in options and "PudoPostnodeID" not in options:
        missing += [label for key, label in (("RegisterAddress", "نشانی"), ("RegisterPostalCode", "کد پستی")) if not recipient[key]]
    if missing:
        raise BusinessRuleError({"document": "برای ثبت مرسوله این اطلاعات لازم است: " + "، ".join(missing) + "."})

    with transaction.atomic():
        locked = SalesDocument.objects.select_for_update().get(pk=document.pk)
        shipment = PostalShipment.objects.filter(document=locked, is_cancelled=False).first()
        if shipment is not None and shipment.parcel_code:
            raise BusinessConflictError({"document": "برای این سند مرسولهٔ فعال ثبت شده است؛ ابتدا آن را لغو کنید."})
        if shipment is None:
            shipment = PostalShipment.objects.create(
                document=locked, service_type=service_type, pay_type=pay_type, city_id=city,
                weight_grams=weight_grams, goods_price_rial=goods_price, created_by=actor,
            )
        else:
            shipment.service_type, shipment.pay_type, shipment.city_id = service_type, pay_type, city
            shipment.weight_grams, shipment.goods_price_rial = weight_grams, goods_price
            shipment.save()

    # A previous attempt may have reached the carrier and lost the answer;
    # asking first is what keeps a retry from filing the parcel twice.
    if _adopt_if_registered(integration, client, shipment):
        return shipment

    unit_weight = max(1, math.ceil(weight_grams / sale.quantity))
    link = _ensure_product_link(integration, client, sale.product, unit_weight=unit_weight, price=int(sale.unit_price_snapshot))
    parcel = {
        "ClientOrderId": shipment.pk,
        "CityID": city,
        "ServiceType": service_type,
        "PayType": pay_type,
        "RegisterIp": client_ip or current_request_context().ip_address or "127.0.0.1",
        "DiscountAmount": 0,
        "PackingWeight": 0,
        "PrePaidAmount": 0,
        "NonStandardPackage": weight_grams > 2600,
        **recipient,
        **options,
        "Products": [{
            "EbazaarProductID": int(link.ebazar_product_id),
            "Count": sale.quantity,
            "Weight": unit_weight,
            "Price": int(sale.unit_price_snapshot),
            "DisCountPercent": 0,
        }],
    }
    results = _call(integration, lambda: client.add_parcel([parcel]))
    result = results[0] if results else {}
    problems = ebazar.item_errors(result)
    if problems or not result.get("ParcelCode") or not result.get("Shenase"):
        raise BusinessRuleError({"post": "پست مرسوله را نپذیرفت: " + (" — ".join(problems) or "بارکد یا شناسهٔ مرسوله برنگشت.")})
    _store_registration(shipment, result)
    log_activity(actor=actor, operation="postal_shipment.created", instance=shipment, changes={"document": document.pk})
    return shipment


def _store_registration(shipment, result):
    shipment.parcel_code = str(result.get("ParcelCode") or "")
    shipment.shenase = str(result.get("Shenase") or "")
    shipment.shipping_cost_rial = result.get("ShippingCost")
    shipment.shipping_tax_rial = result.get("ShippingCostTax")
    shipment.save()


def _adopt_if_registered(integration, client, shipment):
    try:
        found = client.inquiry(shipment.pk)
    except ebazar.EbazarError:
        return False
    if not isinstance(found, dict) or not found.get("ParcelCode"):
        return False
    shipment.parcel_code = str(found["ParcelCode"])
    shipment.shenase = str(found.get("ParcelShenase") or "")
    shipment.shipping_cost_rial = found.get("Postalprice")
    shipment.shipping_tax_rial = found.get("PostalpriceTax")
    shipment.save()
    return True


# --- follow / change ---------------------------------------------------------------


def _apply_status(shipment, code, *, actor=None):
    shipment.carrier_status_code = code
    shipment.carrier_status_text = ebazar.status_label(code)
    shipment.last_synced_at = timezone.now()
    if code == 1:
        shipment.is_cancelled = True
    shipment.save()
    target = ebazar.dolphin_state_for(code)
    document = SalesDocument.objects.get(pk=shipment.document_id)
    current = postal.state_index(document.postal_status)
    if target and (current is None or postal.state_index(target) > current):
        try:
            transition_postal_status(
                actor=actor or shipment.created_by, document=document, to_status=target,
                reason=f"پست: {shipment.carrier_status_text}",
            )
        except (BusinessPermissionDenied, BusinessConflictError):
            logger.warning("carrier status %s could not move document %s", code, document.pk)


def refresh_shipment(shipment, *, actor=None):
    """Ask the carrier where the parcel is and store the answer."""
    if actor is not None:
        _require_access(actor)
    if not shipment.parcel_code:
        return shipment
    integration, client = _client()
    rows = _call(integration, lambda: client.parcel_status([shipment.parcel_code]))
    row = rows[0] if rows else {}
    if "StatusCode" not in row:
        raise BusinessRuleError({"post": "پست وضعیتی برای این مرسوله برنگرداند."})
    _apply_status(shipment, int(row["StatusCode"]), actor=actor)
    return shipment


def change_shipment(*, actor, shipment, action):
    """Hold, cancel or mark the parcel ready to send, at the carrier."""
    _require_access(actor)
    if action not in CHANGE_STATUS:
        raise BusinessRuleError({"action": "این تغییر پشتیبانی نمی‌شود."})
    if not shipment.parcel_code:
        raise BusinessRuleError({"shipment": "این مرسوله هنوز در پست ثبت نشده است."})
    integration, client = _client()
    rows = _call(integration, lambda: client.change_status(CHANGE_STATUS[action], [shipment.parcel_code]))
    row = rows[0] if rows else {}
    if row.get("ResCode") != 0:
        raise BusinessRuleError({"post": row.get("Description") or "پست تغییر وضعیت را نپذیرفت."})
    log_activity(actor=actor, operation=f"postal_shipment.{action}", instance=shipment, changes={})
    return refresh_shipment(shipment, actor=actor)


def wallet(*, actor):
    _require_access(actor)
    integration, client = _client()
    return _call(integration, client.wallet_credit) or {}


def sync_open_shipments(limit=200):
    """The worker's job: refresh every parcel the carrier can still change."""
    if not feature_enabled("sales_documents") or not is_connected():
        return 0
    done = 0
    open_ones = (
        PostalShipment.objects.filter(is_cancelled=False).exclude(parcel_code="")
        .exclude(carrier_status_code__in=ebazar.FINAL_STATUS_CODES)
        .select_related("document", "created_by")[:limit]
    )
    for shipment in open_ones:
        try:
            refresh_shipment(shipment)
            done += 1
        except BusinessRuleError:
            break
    return done


def track(parcel_code):
    """`(state_key, raw_status)` for one barcode, as `PostalCarrier.track` promises."""
    integration, client = _client()
    rows = _call(integration, lambda: client.parcel_status([parcel_code]))
    if not rows or "StatusCode" not in rows[0]:
        return None
    code = int(rows[0]["StatusCode"])
    return ebazar.dolphin_state_for(code), ebazar.status_label(code)


SYNC_EVERY_SECONDS = 900


def register():
    from integrations.worker import register_job

    register_job("sales.postal_sync", sync_open_shipments, SYNC_EVERY_SECONDS)
