"""Fill `User.normalized_phone` for accounts that already had a phone.

Idempotent: a row is written only when its stored value differs from what the
phone normalises to now, so running it twice — or after `User.save()` has
already kept a row current — changes nothing. A phone that is not an Iranian
number (an internal extension, a foreign number) stays blank, exactly as
`User.save()` would leave it. Reverse is a no-op: the column itself is dropped
by reversing 0007, and blanking it here would only lose information.
"""

from django.db import migrations

from common.phones import normalized_or_blank


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    pending = []
    for row in User.objects.exclude(phone="").only("pk", "phone", "normalized_phone").iterator(chunk_size=500):
        value = normalized_or_blank(row.phone)
        if value != row.normalized_phone:
            row.normalized_phone = value
            pending.append(row)
        if len(pending) >= 500:
            User.objects.bulk_update(pending, ["normalized_phone"])
            pending = []
    if pending:
        User.objects.bulk_update(pending, ["normalized_phone"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_person_profile_fields"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
