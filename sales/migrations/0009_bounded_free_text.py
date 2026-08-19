from django.db import migrations, models
from django.db.models.functions import Length


TEXT_LIMITS = (
    ("Customer", "address", 2000),
    ("Customer", "notes", 4000),
    ("Product", "description", 4000),
    ("Lead", "notes", 4000),
    ("Interaction", "notes", 4000),
    ("Sale", "notes", 4000),
)


def reject_oversized_text(apps, schema_editor):
    for model_name, field_name, limit in TEXT_LIMITS:
        model = apps.get_model("sales", model_name)
        row_ids = list(
            model.objects.annotate(_frooshbin_text_length=Length(field_name))
            .filter(_frooshbin_text_length__gt=limit)
            .order_by("pk")
            .values_list("pk", flat=True)[:21]
        )
        if row_ids:
            shown = row_ids[:20]
            suffix = " and more" if len(row_ids) > 20 else ""
            raise RuntimeError(
                f"sales.{model_name}.{field_name} exceeds {limit} characters "
                f"for row IDs {shown}{suffix}. Fix reviewed data before retrying."
            )


class Migration(migrations.Migration):
    dependencies = [("sales", "0008_customer_phone_normalized_shape")]

    operations = [
        migrations.RunPython(reject_oversized_text, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="customer",
            name="address",
            field=models.CharField(blank=True, max_length=2000),
        ),
        migrations.AlterField(
            model_name="customer",
            name="notes",
            field=models.CharField(blank=True, max_length=4000),
        ),
        migrations.AlterField(
            model_name="product",
            name="description",
            field=models.CharField(blank=True, max_length=4000),
        ),
        migrations.AlterField(
            model_name="lead",
            name="notes",
            field=models.CharField(blank=True, max_length=4000),
        ),
        migrations.AlterField(
            model_name="interaction",
            name="notes",
            field=models.CharField(blank=True, max_length=4000),
        ),
        migrations.AlterField(
            model_name="sale",
            name="notes",
            field=models.CharField(blank=True, max_length=4000),
        ),
    ]
