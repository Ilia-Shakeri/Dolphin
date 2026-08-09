from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from common.phones import normalize_customer_phone


class PhoneNormalizationTests(SimpleTestCase):
    def test_normalizes_supported_iranian_forms(self):
        expected = "+989121234567"
        for value in ["09121234567", "+98 912 123 4567", "0098-912-123-4567", "۹۱۲۱۲۳۴۵۶۷"]:
            with self.subTest(value=value):
                self.assertEqual(normalize_customer_phone(value), expected)

    def test_rejects_invalid_number(self):
        with self.assertRaises(ValidationError):
            normalize_customer_phone("123")

