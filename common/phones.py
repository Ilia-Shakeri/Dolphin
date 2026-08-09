import re

from django.core.exceptions import ValidationError


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_customer_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value).translate(_DIGITS))
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits.startswith("0"):
        raise ValidationError("Enter a valid Iranian phone number.")
    return f"+98{digits}"

