"""Fill `owner` and `category_ref` for existing customers.

Expand-only: the free-text `category` and `created_by` are never changed, so
nothing is lost by redeploying the previous version (see
`sales/customer_backfill.py` for the rollback effect on a marketer's scope).
"""

from django.db import migrations

from sales.customer_backfill import run_backfill


def forwards(apps, schema_editor):
    run_backfill(apps.get_model("sales", "Customer"), apps.get_model("sales", "CustomerCategory"), apply=True)


class Migration(migrations.Migration):

    dependencies = [("sales", "0026_customer_owner_and_categories")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
