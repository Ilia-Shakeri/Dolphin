"""Seed the twelve standard call outcomes and match older calls only where
certain (2.40.58, BIZ-003).

An older call keeps its words in `outcome`. It gets a `result` here only when
those words are an outcome's name or key, letters and spacing unified — never
from similar words. Everything else waits for the manager's matching in
Settings → «نتیجهٔ تماس». A call matched to «عدم تماس مجدد» puts its number
on the do-not-contact list, as recording it today would.

The reverse leaves the seeded rows and the matches (0039's own reverse drops
the columns and tables).
"""

import unicodedata

from django.db import migrations

STANDARD = (
    ("no_answer", "پاسخ نداد"),
    ("busy", "خط اشغال بود"),
    ("wrong_number", "شماره اشتباه یا نامعتبر"),
    ("connected", "تماس برقرار شد"),
    ("interested", "علاقه‌مند"),
    ("needs_follow_up", "نیازمند پیگیری"),
    ("quote_requested", "درخواست پیش‌فاکتور"),
    ("purchased", "خرید انجام شد"),
    ("not_interested", "عدم تمایل به خرید"),
    ("call_later", "تماس در زمان دیگری"),
    ("do_not_call", "عدم تماس مجدد"),
    ("other", "سایر"),
)
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
_INVISIBLE = str.maketrans({"‌": " ", "‏": "", "‎": ""})


def _norm(value):
    text = unicodedata.normalize("NFKC", str(value or "")).translate(_LETTERS).translate(_INVISIBLE)
    return " ".join(text.split()).casefold()


def forward(apps, schema_editor):
    CallOutcome = apps.get_model("sales", "CallOutcome")
    Interaction = apps.get_model("sales", "Interaction")
    DoNotContact = apps.get_model("sales", "DoNotContact")
    for position, (key, label) in enumerate(STANDARD, start=1):
        CallOutcome.objects.get_or_create(
            key=key, defaults={"label": label, "standard_key": key, "position": position, "is_system": True},
        )
    known = {}
    for key, label in STANDARD:
        known[_norm(label)] = key
        known[_norm(key)] = key
    for text in Interaction.objects.filter(result="").values_list("outcome", flat=True).distinct():
        key = known.get(_norm(text))
        if key is None:
            continue
        Interaction.objects.filter(result="", outcome=text).update(result=key, result_standard=key)
        if key == "do_not_call":
            for call in Interaction.objects.filter(result="do_not_call", outcome=text).order_by("occurred_at", "pk"):
                phone = call.normalized_phone
                if phone and not DoNotContact.objects.filter(normalized_phone=phone, lifted_at__isnull=True).exists():
                    DoNotContact.objects.create(
                        normalized_phone=phone, interaction_id=call.pk, note=(call.notes or "")[:300],
                        created_by_id=call.agent_id,
                    )


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0039_call_outcomes"),
    ]

    operations = [
        migrations.RunPython(forward, migrations.RunPython.noop),
    ]
