from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models
from django.db.models import Q


def validate_product_prices(apps, schema_editor):
    Product = apps.get_model("sales", "Product")
    if Product.objects.filter(current_price__lte=0).exists():
        raise RuntimeError("Existing Product rows have non-positive prices.")


class Migration(migrations.Migration):
    dependencies = [("sales", "0006_global_active_phone_identity")]

    operations = [
        migrations.RunPython(validate_product_prices, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="product",
            name="product_price_non_negative",
        ),
        migrations.AlterField(
            model_name="product",
            name="current_price",
            field=models.DecimalField(
                max_digits=18,
                decimal_places=2,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(
                condition=Q(current_price__gt=0),
                name="product_price_positive",
            ),
        ),
    ]
