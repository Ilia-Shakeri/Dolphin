"""Fill `Interaction.normalized_phone` for calls logged before 2.21.0.

Idempotent: a row is written only when its stored value differs from what its
phone normalises to now, so a second run changes nothing. A number that is not
Iranian stays blank, exactly as `Interaction.save()` leaves it. Reverse is a
no-op — reversing 0023 drops the column itself.

Interactions are append-only for the application role (no UPDATE grant); this
runs as the migration role, which is the one that may rewrite them.
"""

from django.db import migrations

from common.phones import normalized_or_blank


def backfill(apps, schema_editor):
    Interaction = apps.get_model("sales", "Interaction")
    pending = []
    for row in Interaction.objects.only("pk", "phone", "normalized_phone").iterator(chunk_size=500):
        value = normalized_or_blank(row.phone)
        if value != row.normalized_phone:
            row.normalized_phone = value
            pending.append(row)
        if len(pending) >= 500:
            Interaction.objects.bulk_update(pending, ["normalized_phone"])
            pending = []
    if pending:
        Interaction.objects.bulk_update(pending, ["normalized_phone"])


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0023_interaction_normalized_phone"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
