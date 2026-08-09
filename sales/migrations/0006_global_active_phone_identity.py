from django.db import migrations, models
from django.db.models import Count, Q


def validate_active_phone_identities(apps, schema_editor):
    CustomerPhone = apps.get_model("sales", "CustomerPhone")
    duplicates = (
        CustomerPhone.objects.filter(is_active=True)
        .values("normalized_phone")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError("Active phone identities conflict across Customers.")


class Migration(migrations.Migration):
    dependencies = [("sales", "0005_sale_integrity_constraints")]

    operations = [
        migrations.RunPython(validate_active_phone_identities, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="customerphone",
            name="uniq_active_phone_per_customer",
        ),
        migrations.AddConstraint(
            model_name="customerphone",
            constraint=models.UniqueConstraint(
                fields=("normalized_phone",),
                condition=Q(is_active=True),
                name="uniq_active_normalized_phone",
            ),
        ),
    ]
