"""Money arithmetic shared by every billing service.

One rounding rule everywhere — `ROUND_HALF_UP` to two decimals — applied at
each step rather than once at the end, so a stored total always equals the sum
of the stored parts and a database check constraint can enforce that.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings

from common.exceptions import BusinessRuleError


MONEY = Decimal("0.01")
PERCENT = Decimal("0.01")
MAX_MONEY = Decimal("9999999999999999.99")
HUNDRED = Decimal("100")


def quantize_money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def clean_money(value, *, field, allow_none=False, allow_zero=True):
    if value is None:
        if allow_none:
            return None
        raise BusinessRuleError({field: "This field is required."})
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BusinessRuleError({field: "Enter a valid amount."}) from exc
    if not amount.is_finite():
        raise BusinessRuleError({field: "Enter a valid amount."})
    amount = quantize_money(amount)
    if amount < 0:
        raise BusinessRuleError({field: "Amount cannot be negative."})
    if not allow_zero and amount == 0:
        raise BusinessRuleError({field: "Amount must be greater than zero."})
    if amount > MAX_MONEY:
        raise BusinessRuleError({field: "Amount is too large."})
    return amount


def clean_percent(value, *, field, maximum=HUNDRED):
    if value is None:
        return Decimal("0.00")
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BusinessRuleError({field: "Enter a valid percentage."}) from exc
    if not percent.is_finite():
        raise BusinessRuleError({field: "Enter a valid percentage."})
    percent = percent.quantize(PERCENT, rounding=ROUND_HALF_UP)
    if percent < 0 or percent > maximum:
        raise BusinessRuleError({field: f"Percentage must be between 0 and {maximum}."})
    return percent


def clean_quantity(value, *, field="quantity", maximum=1_000_000):
    if isinstance(value, bool) or not isinstance(value, int):
        raise BusinessRuleError({field: "Quantity must be a whole number."})
    if value < 1:
        raise BusinessRuleError({field: "Quantity must be positive."})
    if value > maximum:
        raise BusinessRuleError({field: "Quantity is too large."})
    return value


def default_tax_rate():
    return clean_percent(getattr(settings, "BILLING_DEFAULT_TAX_RATE", "0.00"), field="tax_rate")


def max_discount_percent():
    return clean_percent(
        getattr(settings, "BILLING_MAX_DISCOUNT_PERCENT", "100.00"), field="discount_percent"
    )


def line_amounts(*, quantity, unit_price, discount_percent=None, discount_amount=None):
    """Compute one line's discount and total.

    A percentage and an absolute amount are both accepted, but never together:
    two sources for one number is how a document ends up disagreeing with its
    own arithmetic. The percentage, when given, wins and the amount is derived.
    """
    gross = quantize_money(unit_price * quantity)
    if discount_percent is not None and discount_amount is not None:
        raise BusinessRuleError({
            "discount_amount": "Give either a discount percentage or a discount amount, not both."
        })
    if discount_percent is not None:
        percent = clean_percent(discount_percent, field="discount_percent", maximum=max_discount_percent())
        amount = quantize_money(gross * percent / HUNDRED)
    else:
        percent = Decimal("0.00")
        amount = clean_money(discount_amount or 0, field="discount_amount")
    if amount > gross:
        raise BusinessRuleError({"discount_amount": "Line discount cannot exceed the line amount."})
    return percent, amount, quantize_money(gross - amount)


def document_totals(*, line_totals, header_discount, tax_rate):
    """Roll lines up into the four stored header amounts."""
    subtotal = quantize_money(sum(line_totals, Decimal("0.00")))
    discount = clean_money(header_discount or 0, field="discount_amount")
    if discount > subtotal:
        raise BusinessRuleError({"discount_amount": "Discount cannot exceed the document subtotal."})
    taxable = quantize_money(subtotal - discount)
    rate = clean_percent(tax_rate, field="tax_rate")
    tax = quantize_money(taxable * rate / HUNDRED)
    total = quantize_money(taxable + tax)
    if total > MAX_MONEY:
        raise BusinessRuleError({"total_amount": "Document total is too large."})
    return subtotal, discount, rate, tax, total
