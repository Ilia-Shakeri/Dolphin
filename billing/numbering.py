"""Gap-free document numbering.

The counter row is locked with `select_for_update` before it is read, so two
concurrent issues take two different numbers. The database unique constraint on
each document's `number` is the second, independent guarantee: even a bug here
cannot produce two documents sharing a number, it can only fail the write.
"""

import re

from django.conf import settings
from django.db import transaction

from billing.models import DocumentSequence
from common.exceptions import BusinessRuleError


KINDS = ("quotation", "order", "invoice", "official_invoice", "payment")
DEFAULT_FORMATS = {
    "quotation": "QT-{sequence:06d}",
    "order": "SO-{sequence:06d}",
    "invoice": "INV-{sequence:06d}",
    # The official series is separate from `invoice` by product-owner decision.
    # An invoice therefore carries up to two numbers: the internal one every
    # document gets at creation, and this one, taken only when it is issued as
    # an official document. They cannot share a counter — an internal number
    # spent on a draft that is never issued would leave a hole in the official
    # series, and that series has to be gapless.
    "official_invoice": "OINV-{sequence:06d}",
    "payment": "PY-{sequence:06d}",
}
# A number goes onto paperwork a customer keeps, so it stays printable ASCII
# with no separators that would break a filename or a CSV cell.
_NUMBER_SHAPE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9/._-]{0,63}\Z")


def _format_for(kind):
    configured = getattr(settings, "BILLING_NUMBER_FORMATS", None) or {}
    template = configured.get(kind) or DEFAULT_FORMATS[kind]
    if "{sequence" not in template:
        # A format without the counter would hand every document the same
        # number and fail at the unique constraint on the second one. Refuse it
        # where the operator can still see why.
        raise BusinessRuleError({"number": "Document number format must include {sequence}."})
    return template


def format_number(kind, sequence):
    try:
        number = _format_for(kind).format(sequence=sequence)
    except (IndexError, KeyError, ValueError) as exc:
        raise BusinessRuleError({"number": "Document number format is invalid."}) from exc
    if not _NUMBER_SHAPE.fullmatch(number):
        raise BusinessRuleError({"number": "Document number format produces an unusable number."})
    return number


@transaction.atomic
def next_document_number(kind):
    if kind not in KINDS:
        raise BusinessRuleError({"number": "Unknown document kind."})
    row = DocumentSequence.objects.select_for_update().filter(kind=kind).first()
    if row is None:
        DocumentSequence.objects.get_or_create(kind=kind)
        row = DocumentSequence.objects.select_for_update().get(kind=kind)
    sequence = row.next_value
    row.next_value = sequence + 1
    row.save(update_fields=["next_value", "updated_at"])
    return format_number(kind, sequence)
