from django.db import migrations, models


VALID_DIRECTIONS = {"inbound", "outbound"}


def reject_invalid_interactions(apps, schema_editor):
    Interaction = apps.get_model("sales", "Interaction")
    invalid_ids = []
    rows = Interaction.objects.values_list(
        "pk",
        "direction",
        "outcome",
    ).iterator(chunk_size=1000)
    for row_id, direction, outcome in rows:
        if direction not in VALID_DIRECTIONS or not isinstance(outcome, str) or not outcome.strip():
            invalid_ids.append(row_id)
            if len(invalid_ids) == 21:
                break
    if invalid_ids:
        shown = invalid_ids[:20]
        suffix = " and more" if len(invalid_ids) > 20 else ""
        raise RuntimeError(
            "sales.Interaction direction or outcome breaks the approved contract "
            f"for row IDs {shown}{suffix}. Fix reviewed data before retrying."
        )


class Migration(migrations.Migration):
    dependencies = [("sales", "0009_bounded_free_text")]

    operations = [
        migrations.RunPython(reject_invalid_interactions, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="interaction",
            name="direction",
            field=models.CharField(
                choices=[("inbound", "Inbound"), ("outbound", "Outbound")],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="interaction",
            name="outcome",
            field=models.CharField(db_index=True, max_length=80),
        ),
        migrations.AddConstraint(
            model_name="interaction",
            constraint=models.CheckConstraint(
                condition=models.Q(direction__in=["inbound", "outbound"]),
                name="interaction_direction_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="interaction",
            constraint=models.CheckConstraint(
                condition=models.Q(outcome__regex=r"\S"),
                name="interaction_outcome_nonblank",
            ),
        ),
    ]
