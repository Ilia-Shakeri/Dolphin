"""Seed the case types, stages and deadlines, and place older cases (2.40.60, BIZ-008).

* seven types, seven default stages, and the three priorities' deadlines;
* every existing case keeps its `status` words and its history; it gets the
  nearest new stage from those words (a closed case: «بسته‌شده», with no
  final result — that is not guessed), priority «عادی», and no type (none
  was recorded);
* deadlines are not written for older cases: they were made under no rule.

The reverse leaves the seeded rows (0003's reverse drops them).
"""

import unicodedata

from django.db import migrations

TYPES = (
    ("complaint", "شکایت"), ("repair", "تعمیر"), ("warranty", "گارانتی"), ("question", "پرسش"),
    ("return", "مرجوعی"), ("shipping", "پیگیری ارسال"), ("other", "سایر"),
)
STAGES = (
    ("registered", "ثبت‌شده", "open"),
    ("reviewing", "در حال بررسی", "open"),
    ("waiting_customer", "منتظر مشتری یا اطلاعات تکمیلی", "open"),
    ("waiting_parts", "منتظر قطعه یا تأمین‌کننده", "open"),
    ("in_progress", "در حال انجام", "open"),
    ("ready", "آماده تحویل یا اعلام نتیجه", "open"),
    ("closed", "بسته‌شده", "closed"),
)
SLA = (
    ("normal", 1, "day", None, "hour", 5, "day"),
    ("urgent", 4, "hour", None, "hour", 2, "day"),
    ("critical", 1, "hour", 4, "hour", None, "day"),
)
WORDS = (
    (("قطعه", "تأمین", "تامین"), "waiting_parts"),
    (("منتظر مشتری", "اطلاعات", "منتظر پاسخ"), "waiting_customer"),
    (("آماده", "تحویل", "اعلام نتیجه"), "ready"),
    (("انجام", "تعمیر", "پیگیری"), "in_progress"),
    (("بررسی",), "reviewing"),
    (("ثبت", "جدید", "باز"), "registered"),
)


def nearest(text, closed):
    if closed:
        return "closed"
    words = " ".join(unicodedata.normalize("NFKC", str(text or "")).replace("ي", "ی").replace("ك", "ک").split())
    if "بسته" in words or "مختومه" in words:
        return "reviewing"  # still open: the words are older than the closing
    for needles, key in WORDS:
        if any(needle in words for needle in needles):
            return key
    return "reviewing"


def forward(apps, schema_editor):
    CaseType = apps.get_model("aftersales", "CaseType")
    CaseStage = apps.get_model("aftersales", "CaseStage")
    SlaPolicy = apps.get_model("aftersales", "SlaPolicy")
    Request = apps.get_model("aftersales", "AfterSalesRequest")
    for position, (key, label) in enumerate(TYPES, start=1):
        CaseType.objects.get_or_create(key=key, defaults={"label": label, "position": position, "is_system": True})
    for position, (key, label, kind) in enumerate(STAGES, start=1):
        CaseStage.objects.get_or_create(
            case_type=None, key=key, defaults={"label": label, "kind": kind, "position": position, "is_system": True},
        )
    for priority, rv, ru, pv, pu, sv, su in SLA:
        SlaPolicy.objects.get_or_create(
            priority=priority, case_type=None,
            defaults={"response_value": rv, "response_unit": ru, "plan_value": pv, "plan_unit": pu,
                      "resolution_value": sv, "resolution_unit": su},
        )
    Request.objects.filter(closed_at__isnull=False).update(stage="closed")
    open_cases = Request.objects.filter(closed_at__isnull=True)
    for status in open_cases.values_list("status", flat=True).distinct():
        open_cases.filter(status=status).update(stage=nearest(status, False))


class Migration(migrations.Migration):

    dependencies = [
        ("aftersales", "0003_case_workflow"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
