"""A sample invoice to preview the print layout with (2.40.44).

The settings page shows what the company's printed invoice will look like
before any real one is printed with it. Nothing here is a document: no row is
read or written, the figures are made up and stated as such, and the page
carries a «نمونه» banner (`sample` in the context). The seller block is the
deployment's real one (`SELLER_*`), since that is what will print.
"""

from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.utils import timezone

from billing.money import printed_line_breakdown
from billing.words import amount_in_words
from common import labels

TAX_RATE = Decimal("10")
#: (sku, name, quantity, unit price, line discount)
LINES = (
    ("PRD-1001", "کالای نمونهٔ الف", 2, Decimal("1500000"), Decimal("0")),
    ("SRV-2001", "خدمت نمونهٔ ب", 1, Decimal("3200000"), Decimal("200000")),
    ("PRD-1003", "کالای نمونهٔ ج", 5, Decimal("480000"), Decimal("0")),
)
PAID = Decimal("3000000")


def sample_invoice_context(user):
    """Everything `common/invoices/print.html` reads, for a made-up invoice."""
    unit = SimpleNamespace(get_unit_display="عدد")
    items = [
        SimpleNamespace(
            line_number=index, product_sku_snapshot=sku, product_name_snapshot=name, description="",
            quantity=quantity, product=unit, unit_price=price, discount_amount=discount,
            line_total=price * quantity - discount,
        )
        for index, (sku, name, quantity, price, discount) in enumerate(LINES, start=1)
    ]
    subtotal = sum((item.line_total for item in items), Decimal("0"))
    tax = (subtotal * TAX_RATE / 100).quantize(Decimal("1"))
    total = subtotal + tax
    document = SimpleNamespace(
        status="issued", invoice_type="official", official_number="", number="S-1001",
        issued_at=timezone.now(), due_at=None, warehouse=SimpleNamespace(name="انبار مرکزی"),
        subtotal_amount=subtotal, discount_amount=Decimal("0"), tax_rate=TAX_RATE, tax_amount=tax,
        total_amount=total, paid_amount=PAID, balance_due=total - PAID,
        notes="یادداشت نمونهٔ فاکتور.", created_by=user,
    )
    rows, totals = printed_line_breakdown(
        items=items, header_discount=document.discount_amount, tax_rate=TAX_RATE, tax_amount=tax,
    )
    return {
        "sample": True,
        "document": document,
        "items": items,
        "line_rows": rows,
        "line_totals": totals,
        "taxable_amount": subtotal,
        "total_in_words": amount_in_words(total),
        "settlement_label": labels.SETTLEMENT_LABELS["partially_paid"],
        "identity_is_snapshot": True,
        "pdf_available": False,
        "buyer": {
            "name": "خریدار نمونه", "national_id": "0012345678", "economic_code": "411111111111",
            "address": "تهران، خیابان نمونه، پلاک ۱", "postal_code": "1234567890", "city": "تهران",
            "phone": "021-00000000",
        },
        "seller": {
            "name": settings.SELLER_LEGAL_NAME,
            "registration_number": settings.SELLER_REGISTRATION_NUMBER,
            "national_id": settings.SELLER_NATIONAL_ID,
            "economic_code": settings.SELLER_ECONOMIC_CODE,
            "address": settings.SELLER_ADDRESS,
            "postal_code": settings.SELLER_POSTAL_CODE,
            "city": settings.SELLER_CITY,
            "phone": settings.SELLER_PHONE,
        },
    }
