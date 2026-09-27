from django.db import migrations, models


def fold_extra_large_into_large(apps, schema_editor):
    """`xl` («خیلی بزرگ») left the choices in 2.18.6; a reader who had it
    keeps the largest size that is still on offer rather than silently
    dropping back to the default."""
    UserPreference = apps.get_model("common", "UserPreference")
    UserPreference.objects.filter(font_scale="xl").update(font_scale="lg")


class Migration(migrations.Migration):
    """Panel font scale: four steps become three (2.18.6).

    A display preference, not business data. The reverse is a no-op on the
    rows — which readers had `xl` rather than `lg` is not recoverable, and
    both render readably — and only the choices list is restored.
    """

    dependencies = [
        ("common", "0006_userdashboardlayout_widget_heights"),
    ]

    operations = [
        migrations.RunPython(fold_extra_large_into_large, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userpreference",
            name="font_scale",
            field=models.CharField(
                choices=[("sm", "کوچک"), ("md", "متوسط"), ("lg", "بزرگ")],
                default="md",
                max_length=2,
            ),
        ),
    ]
