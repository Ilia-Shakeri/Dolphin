"""The edge and the application must accept the same largest document.

`BILLING_MAX_DOCUMENT_ITEMS` lines each carrying a full-length Persian
description is the biggest request the API advertises as valid. When the body
limit sat below that, the rule the service layer enforces and the rule the
transport enforces disagreed, and the user met a 413 quoting neither.
"""

import pathlib
import re

from django.conf import settings
from django.test import SimpleTestCase

from billing.models import LINE_DESCRIPTION_MAX_LENGTH


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
NGINX_CONF = REPOSITORY_ROOT / "nginx" / "default.conf"
#: JSON field names and punctuation around one line, measured from the shape
#: `DocumentLineInputSerializer` accepts.
LINE_ENVELOPE_BYTES = 110
#: Persian text is two bytes per character in UTF-8.
PERSIAN_BYTES_PER_CHARACTER = 2


def largest_document_bytes():
    per_line = LINE_ENVELOPE_BYTES + LINE_DESCRIPTION_MAX_LENGTH * PERSIAN_BYTES_PER_CHARACTER
    return settings.BILLING_MAX_DOCUMENT_ITEMS * per_line


class RequestSizeLimitTests(SimpleTestCase):
    def test_django_accepts_the_largest_document_the_api_allows(self):
        self.assertGreaterEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, largest_document_bytes())

    def test_nginx_accepts_at_least_what_django_does(self):
        conf = NGINX_CONF.read_text(encoding="utf-8")
        match = re.search(r"client_max_body_size\s+(\d+)([kKmM]?);", conf)
        self.assertIsNotNone(match, "nginx no longer sets client_max_body_size")
        value = int(match.group(1))
        unit = match.group(2).lower()
        limit = value * {"": 1, "k": 1024, "m": 1024 * 1024}[unit]
        self.assertGreaterEqual(limit, settings.DATA_UPLOAD_MAX_MEMORY_SIZE)

    def test_the_limit_is_still_a_limit(self):
        """Bounded, not merely large: an unbounded body is a memory exhaustion."""
        self.assertLessEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 1024 * 1024)
