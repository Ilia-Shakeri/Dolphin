"""Add target-audience members in bulk from a filled spreadsheet export.

The same round trip as `sales.customer_imports` and `sales.imports`, and
deliberately the same shape: the marketer exports the campaign's current
audience, writes new rows on that file, and uploads it back, so columns are
matched by **header name** rather than by position.

A campaign has no SKU and no national ID, so identity here is the same thing
`sales.services.add_target_audience_member` already uses — the phone number.
That identity is **global, not per campaign**: `TargetAudienceMember` carries a
database-level uniqueness constraint on the normalized phone across the whole
audience, not just the one campaign a row is uploaded into, because the same
person chased by two campaigns is still one person. Two rows in one file, or a
row and any existing member anywhere, are the same identity when their
normalized phone numbers match; nothing is overwritten, only skipped and
counted.

Every row goes through `add_target_audience_member`, the same service the
dialog uses, so an imported identity gets the same validation, the same scope
check and the same derived-status pass as one typed by hand.
"""

from dataclasses import dataclass, field

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from openpyxl import load_workbook

from common.exceptions import BusinessConflictError, BusinessRuleError
from common.phones import normalize_customer_phone
from reports.xlsx import TARGET_AUDIENCE_HEADERS
from sales.models import TargetAudienceMember
from sales.services import add_target_audience_member


#: A row is not an identity without a name and a phone number.
REQUIRED_COLUMNS = ("full_name", "raw_phone")
MAX_IMPORT_ROWS = 5000


@dataclass
class TargetAudienceImportResult:
    created: int = 0
    duplicates: int = 0
    invalid: int = 0
    #: Bounded so an unreadable file cannot return a megabyte of complaints.
    errors: list = field(default_factory=list)

    def note_error(self, row_number, message):
        self.invalid += 1
        if len(self.errors) < 20:
            self.errors.append({"row": row_number, "detail": message})


def _header_index(sheet):
    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
    if header_row is None:
        raise BusinessRuleError({"file": "فایل اکسل خالی است."})
    index = {}
    for position, value in enumerate(header_row):
        name = str(value or "").strip().lower()
        if name in TARGET_AUDIENCE_HEADERS:
            index[name] = position
    missing = [name for name in REQUIRED_COLUMNS if name not in index]
    if missing:
        raise BusinessRuleError({
            "file": (
                f"ستون‌های {', '.join(missing)} در فایل وجود ندارد. "
                "ابتدا جامعه هدف را خروجی بگیرید و روی همان فایل بنویسید."
            )
        })
    return index


def _cell(row, index, name):
    position = index.get(name)
    if position is None or position >= len(row):
        return ""
    value = row[position]
    if value is None:
        return ""
    # openpyxl reads a phone typed as digits as a float; str() on that would
    # produce `9121234567.0`.
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


@transaction.atomic
def import_target_audience_from_workbook(*, actor, lead, stream):
    """Read an uploaded workbook and add every identity it describes to `lead`.

    One transaction for the whole file: a run that fails halfway leaves no
    half-imported audience behind. Rows that are skipped as duplicate or
    invalid do not fail the run — they are reported.
    """
    try:
        workbook = load_workbook(stream, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl raises several unrelated types
        raise BusinessRuleError({"file": "فایل به‌عنوان اکسل قابل خواندن نبود."}) from exc

    sheet = workbook.active
    index = _header_index(sheet)
    result = TargetAudienceImportResult()

    # Existing identities across the whole audience, read once — not scoped to
    # `lead`, because `uniq_target_member_phone` isn't either. Phones are
    # compared in their normalized form, the form that constraint is written
    # over, so this check and the database agree about what a duplicate is.
    existing_phones = set(
        TargetAudienceMember.objects.values_list("normalized_phone", flat=True)
    )
    seen_phones = set()

    for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if row_number - 1 > MAX_IMPORT_ROWS:
            raise BusinessRuleError({"file": f"هر بارگذاری حداکثر می‌تواند {MAX_IMPORT_ROWS} ردیف داشته باشد."})
        if row is None or all(value in (None, "") for value in row):
            continue

        full_name = _cell(row, index, "full_name")
        raw_phone = _cell(row, index, "raw_phone")
        if not full_name or not raw_phone:
            result.note_error(row_number, "درج نام و تلفن الزامی است.")
            continue

        try:
            normalized = normalize_customer_phone(raw_phone)
        except DjangoValidationError:
            result.note_error(row_number, f"شماره تلفن ایرانی معتبر نیست: {raw_phone}")
            continue

        if normalized in existing_phones or normalized in seen_phones:
            result.duplicates += 1
            continue

        notes = _cell(row, index, "notes")

        try:
            add_target_audience_member(
                actor=actor, lead=lead, full_name=full_name, raw_phone=raw_phone, notes=notes,
            )
        except BusinessConflictError:
            # Another row in this same file, or another session, claimed this
            # number between the read above and now. Still a duplicate.
            result.duplicates += 1
            continue
        except BusinessRuleError as exc:
            result.note_error(row_number, str(exc.detail))
            continue

        seen_phones.add(normalized)
        result.created += 1

    return result
