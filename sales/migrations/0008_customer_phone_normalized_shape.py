import re

from django.db import migrations, models


NORMALIZED_PHONE = re.compile(r"\A\+98[1-9][0-9]{9}\Z")


def validate_normalized_phone_shape(apps, schema_editor):
    CustomerPhone = apps.get_model("sales", "CustomerPhone")
    invalid_ids = []
    rows = CustomerPhone.objects.values_list("id", "normalized_phone").iterator(chunk_size=1000)
    for row_id, normalized_phone in rows:
        if not NORMALIZED_PHONE.fullmatch(normalized_phone):
            invalid_ids.append(row_id)
            if len(invalid_ids) == 20:
                break
    if invalid_ids:
        joined_ids = ", ".join(str(row_id) for row_id in invalid_ids)
        raise RuntimeError(
            "CustomerPhone normalized identity has invalid shape. "
            f"Review row IDs before migration: {joined_ids}."
        )


class Migration(migrations.Migration):
    dependencies = [("sales", "0007_product_price_positive")]

    operations = [
        migrations.RunPython(validate_normalized_phone_shape, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="customerphone",
            constraint=models.CheckConstraint(
                condition=models.Q(normalized_phone__regex=r"\A\+98[1-9][0-9]{9}\Z"),
                name="customer_phone_normalized_shape",
            ),
        ),
    ]
