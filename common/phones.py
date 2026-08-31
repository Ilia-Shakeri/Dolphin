import re

from django.core.exceptions import ValidationError


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_PHONE_TEXT = re.compile(r"[0-9+() \t\r\n-]+", flags=re.ASCII)


def normalize_customer_phone(value: str) -> str:
    translated = str(value).translate(_DIGITS)
    if not _PHONE_TEXT.fullmatch(translated):
        raise ValidationError("شماره تلفن ایرانی معتبر وارد کنید.")
    digits = re.sub(r"[^0-9]", "", translated)
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits.startswith("0"):
        raise ValidationError("شماره تلفن ایرانی معتبر وارد کنید.")
    return f"+98{digits}"
