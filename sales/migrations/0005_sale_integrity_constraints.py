from django.db import migrations, models
from django.db.models import F, Q


def validate_existing_sales(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    bad_pair = Sale.objects.filter(
        Q(product__isnull=True, unit_price_snapshot__isnull=False)
        | Q(product__isnull=False, unit_price_snapshot__isnull=True)
    )
    bad_total = Sale.objects.filter(product__isnull=False).exclude(
        total_amount=F("unit_price_snapshot") * F("quantity")
    )
    if bad_pair.exists() or bad_total.exists():
        raise RuntimeError("Existing sale rows break product snapshot rules.")


class Migration(migrations.Migration):
    dependencies = [("sales", "0004_lead_lead_assignment_fields_consistent")]

    operations = [
        migrations.RunPython(validate_existing_sales, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="sale",
            name="sale_product_has_price_snapshot",
        ),
        migrations.AddConstraint(
            model_name="sale",
            constraint=models.CheckConstraint(
                condition=(
                    Q(product__isnull=True, unit_price_snapshot__isnull=True)
                    | Q(product__isnull=False, unit_price_snapshot__isnull=False)
                ),
                name="sale_product_snapshot_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="sale",
            constraint=models.CheckConstraint(
                condition=Q(product__isnull=True) | Q(total_amount=F("unit_price_snapshot") * F("quantity")),
                name="sale_product_total_matches_snapshot",
            ),
        ),
    ]
