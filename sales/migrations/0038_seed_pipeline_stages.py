"""Seed the stage workflows and lost reasons, and move existing leads onto them
(2.40.57, BIZ-002).

* the lead workflow's eight stages, the campaign workflow's five (the keys
  campaign people already carry) and the seven lost reasons;
* each existing lead gets the stage its status meant: «در انتظار تکمیل» →
  «جدید», or «تماس اولیه» when a call is already recorded against it;
  «تکمیل» → «برنده»; «کنسل شده» → «بازنده» with the reason «سایر» and a
  note saying where it came from. No history row is written for this: a
  history row protects its lead from deletion, and the move changes nothing
  anyone did — the record itself says where a cancelled lead came from;
* a campaign person already lost keeps their written reason as the note
  beside «سایر».

`status` is not touched, so going back to 0037 loses nothing a previous
release reads; the reverse leaves the seeded rows alone (0037's own reverse
drops them).
"""

from django.db import migrations

LEAD_STAGES = (
    ("new", "جدید", "open", False, True),
    ("first_contact", "تماس اولیه", "open", False, True),
    ("needs_analysis", "نیازسنجی", "open", False, True),
    ("qualified", "واجد شرایط", "open", True, True),
    ("quote_sent", "ارسال پیش‌فاکتور", "open", True, True),
    ("negotiation", "مذاکره", "open", True, True),
    ("won", "برنده", "won", True, True),
    ("lost", "بازنده", "lost", False, True),
)
CAMPAIGN_STAGES = (
    ("new", "جدید", "open", False, True),
    ("contacted", "تماس گرفته‌شده", "open", False, True),
    ("engaged", "در تعامل", "open", False, True),
    ("converted", "تبدیل‌شده", "won", True, False),
    ("lost", "ازدست‌رفته", "lost", False, True),
)
LOST_REASONS = (
    ("price", "قیمت نامناسب", False),
    ("competitor", "خرید از رقیب", False),
    ("no_need", "عدم نیاز", False),
    ("unresponsive", "عدم پاسخ‌گویی پس از پیگیری‌های لازم", False),
    ("invalid_data", "نامعتبر بودن اطلاعات", False),
    ("purchase_cancelled", "لغو خرید", False),
    ("other", "سایر", True),
)
CANCELLED_NOTE = "کنسل‌شده پیش از نسخهٔ ۲.۴۰.۵۷"
BATCH = 500


def forward(apps, schema_editor):
    PipelineStage = apps.get_model("sales", "PipelineStage")
    LostReason = apps.get_model("sales", "LostReason")
    Lead = apps.get_model("sales", "Lead")
    Interaction = apps.get_model("sales", "Interaction")
    TargetAudienceMember = apps.get_model("sales", "TargetAudienceMember")

    for pipeline, rows in (("lead", LEAD_STAGES), ("campaign", CAMPAIGN_STAGES)):
        for position, (key, label, kind, qualifies, manual) in enumerate(rows, start=1):
            PipelineStage.objects.get_or_create(
                pipeline=pipeline, key=key,
                defaults={"label": label, "kind": kind, "position": position, "qualifies": qualifies,
                          "manual": manual, "is_system": True, "is_active": True},
            )
    for position, (key, label, needs_note) in enumerate(LOST_REASONS, start=1):
        LostReason.objects.get_or_create(
            key=key, defaults={"label": label, "needs_note": needs_note, "position": position, "is_system": True},
        )
    called = set(Interaction.objects.values_list("lead_id", flat=True).distinct())
    pending = Lead.objects.filter(status__in=["pending", ""]).values_list("pk", flat=True)
    contacted = [pk for pk in pending if pk in called]
    for start in range(0, len(contacted), BATCH):
        Lead.objects.filter(pk__in=contacted[start:start + BATCH]).update(stage="first_contact")
    Lead.objects.filter(status="completed").update(stage="won")
    Lead.objects.filter(status="cancelled").update(stage="lost", lost_reason_key="other", lost_reason=CANCELLED_NOTE)

    TargetAudienceMember.objects.filter(stage="lost", lost_reason_key="").update(lost_reason_key="other")


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0037_pipeline_stages"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
