"""Money arithmetic shared by every billing service.

One rounding rule everywhere — `ROUND_HALF_UP` to two decimals — applied at
each step rather than once at the end, so a stored total always equals the sum
of the stored parts and a database check constraint can enforce that.
"""

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP

from django.conf import settings

from common.exceptions import BusinessRuleError


MONEY = Decimal("0.01")
PERCENT = Decimal("0.01")
MAX_MONEY = Decimal("9999999999999999.99")
HUNDRED = Decimal("100")


def quantize_money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def _quantized_or_invalid(value, *, field):
    """Quantize, turning a value too large to quantize into a field error.

    `Decimal("1e100")` is finite, so it passes the checks above and then raises
    `InvalidOperation` inside `quantize` — a 500 out of the function whose job is
    to reject bad input. The API's `DecimalField(max_digits=18)` currently
    catches such values first, but this is the layer that is supposed to be
    defensive, so it defends.
    """
    try:
        return quantize_money(value)
    except (InvalidOperation, ArithmeticError) as exc:
        raise BusinessRuleError({field: "مبلغ بیش از حد مجاز است."}) from exc


def clean_money(value, *, field, allow_none=False, allow_zero=True):
    if value is None:
        if allow_none:
            return None
        raise BusinessRuleError({field: "این فیلد الزامی است."})
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BusinessRuleError({field: "مبلغ معتبر وارد کنید."}) from exc
    if not amount.is_finite():
        raise BusinessRuleError({field: "مبلغ معتبر وارد کنید."})
    amount = _quantized_or_invalid(amount, field=field)
    if amount < 0:
        raise BusinessRuleError({field: "مبلغ نمی‌تواند منفی باشد."})
    if not allow_zero and amount == 0:
        raise BusinessRuleError({field: "مبلغ باید بیشتر از صفر باشد."})
    if amount > MAX_MONEY:
        raise BusinessRuleError({field: "مبلغ بیش از حد مجاز است."})
    return amount


def clean_percent(value, *, field, maximum=HUNDRED):
    if value is None:
        return Decimal("0.00")
    try:
        percent = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BusinessRuleError({field: "درصد معتبر وارد کنید."}) from exc
    if not percent.is_finite():
        raise BusinessRuleError({field: "درصد معتبر وارد کنید."})
    try:
        percent = percent.quantize(PERCENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ArithmeticError) as exc:
        raise BusinessRuleError({field: "درصد معتبر وارد کنید."}) from exc
    if percent < 0 or percent > maximum:
        raise BusinessRuleError({field: f"درصد باید بین ۰ و {maximum} باشد."})
    return percent


def clean_quantity(value, *, field="quantity", maximum=1_000_000):
    if isinstance(value, bool) or not isinstance(value, int):
        raise BusinessRuleError({field: "تعداد باید عددی صحیح باشد."})
    if value < 1:
        raise BusinessRuleError({field: "تعداد باید مثبت باشد."})
    if value > maximum:
        raise BusinessRuleError({field: "تعداد بیش از حد مجاز است."})
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
            "discount_amount": "فقط یکی از درصد تخفیف یا مبلغ تخفیف را وارد کنید، نه هر دو را."
        })
    if discount_percent is not None:
        percent = clean_percent(discount_percent, field="discount_percent", maximum=max_discount_percent())
        amount = quantize_money(gross * percent / HUNDRED)
    else:
        percent = Decimal("0.00")
        amount = clean_money(discount_amount or 0, field="discount_amount")
    if amount > gross:
        raise BusinessRuleError({"discount_amount": "تخفیف ردیف نمی‌تواند از مبلغ ردیف بیشتر باشد."})
    return percent, amount, quantize_money(gross - amount)


def document_totals(*, line_totals, header_discount, tax_rate):
    """Roll lines up into the four stored header amounts."""
    subtotal = quantize_money(sum(line_totals, Decimal("0.00")))
    discount = clean_money(header_discount or 0, field="discount_amount")
    if discount > subtotal:
        raise BusinessRuleError({"discount_amount": "تخفیف نمی‌تواند از جمع جزء سند بیشتر باشد."})
    taxable = quantize_money(subtotal - discount)
    rate = clean_percent(tax_rate, field="tax_rate")
    tax = quantize_money(taxable * rate / HUNDRED)
    total = quantize_money(taxable + tax)
    if total > MAX_MONEY:
        raise BusinessRuleError({"total_amount": "مبلغ کل سند بیش از حد مجاز است."})
    return subtotal, discount, rate, tax, total


def display_rial(value):
    """The whole-rial figure the panel shows for an amount.

    The same rule as `money()` in the panel script and the `money` template
    filter: drop the fraction by rounding **up**. Kept here so the arithmetic
    below works in the units the reader actually sees.
    """
    return int(Decimal(value or 0).to_integral_value(rounding=ROUND_CEILING))


def _apportion(total, weights):
    """Split a whole number across weights so the parts sum to it exactly.

    Rounds the *running* total rather than each part, then takes differences.
    The last cumulative value is the total itself, so the parts always add up —
    which rounding each part independently does not guarantee, and that is the
    whole reason this exists.
    """
    count = len(weights)
    if count == 0:
        return []
    total_weight = sum(weights)
    if total_weight <= 0:
        # Nothing to weigh by: give it all to the first line rather than
        # dropping it, so the column still sums to the footer.
        return [total] + [0] * (count - 1)

    parts = []
    running_weight = Decimal(0)
    carried = 0
    for index, weight in enumerate(weights):
        running_weight += Decimal(weight)
        if index == count - 1:
            cumulative = total
        else:
            cumulative = int(
                (Decimal(total) * running_weight / Decimal(total_weight)).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            )
        parts.append(cumulative - carried)
        carried = cumulative
    return parts


def printed_line_breakdown(*, items, header_discount, tax_rate, tax_amount):
    """Per-line columns and their totals for the printed document, in whole rial.

    The sample official invoice the product owner supplied prints tax **on each
    line**. The stored document has no such column: tax is one header figure
    computed on the discounted subtotal, which is the only form that can be
    checked against `total_amount`. So the columns are derived, and the one rule
    that matters is that **they add up to the footer beneath them**. A tax
    document whose columns disagree with its own total is worse than one with no
    columns at all.

    Everything here is computed in **whole rial**, not in stored decimals, and
    that is the point. An earlier version apportioned the exact decimal amounts
    so the stored values summed perfectly — and then the page rounded each line
    up for display, because the panel shows no fractions. Rounding up is not
    additive: two lines each ending in a fraction each gained a rial, and the
    printed column came to one more than the printed total. Working in the units
    the reader sees is the only way the two can agree.

    Returns `(rows, totals)`. The template prints both, so the footer cannot
    drift from the columns: they are the same numbers.
    """
    items = list(items)
    header_discount = Decimal(header_discount or 0)
    tax_amount = Decimal(tax_amount or 0)

    line_totals = [Decimal(item.line_total) for item in items]
    line_discounts = [Decimal(item.discount_amount or 0) for item in items]
    subtotal = sum(line_totals, Decimal("0.00"))

    # Each column's exact total, then the whole-rial figure printed for it.
    gross_total = display_rial(subtotal + sum(line_discounts, Decimal("0.00")))
    discount_total = display_rial(sum(line_discounts, Decimal("0.00")) + header_discount)
    net_total = display_rial(subtotal - header_discount)
    tax_total = display_rial(tax_amount)

    # Weighted by each line's share of the subtotal, which is what the header
    # discount and the tax were computed from in the first place.
    weights = [int(value) for value in line_totals]
    gross_parts = _apportion(gross_total, [int(a + b) for a, b in zip(line_totals, line_discounts)])
    discount_parts = _apportion(discount_total, weights) if discount_total else [0] * len(items)
    net_parts = _apportion(net_total, weights)
    tax_parts = _apportion(tax_total, weights)

    rows = []
    for index, item in enumerate(items):
        net = net_parts[index]
        tax = tax_parts[index]
        rows.append({
            "item": item,
            # مبلغ کل — before any discount, which is what the sample shows.
            "gross": gross_parts[index],
            # مبلغ تخفیف — the line's own discount plus its share of the header.
            "discount": discount_parts[index],
            # مبلغ کل پس از تخفیف
            "net": net,
            # جمع مالیات و عوارض
            "tax": tax,
            # جمع مبلغ کل بعلاوه جمع مالیات و عوارض
            "total": net + tax,
        })

    totals = {
        "gross": gross_total,
        "discount": discount_total,
        "net": net_total,
        "tax": tax_total,
        # Taken from the rows rather than rounded separately, so the last column
        # sums to its own footer too.
        "total": sum(row["total"] for row in rows),
    }
    return rows, totals
