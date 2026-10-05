"""2.40.0: one allocation per submission row, enforced by the database.

2.39.18 stored the same `request_key` on every row of one submission. From
2.40.0 each row carries `<key>:<n>` and (payment, request_key) is unique for
non-empty keys. The backfill rewrites the older shared keys first, in id
order, and is idempotent: a key that already ends in `:<n>` is left alone.
Reversing drops the constraint and leaves the rewritten keys (2.39.x reads
them only for equality, so a rolled-back release simply treats them as new
keys).
"""

import re

from django.conf import settings
from django.db import migrations, models

SUFFIXED = re.compile(r":\d+$")


def split_shared_keys(apps, schema_editor):
    PaymentAllocation = apps.get_model("billing", "PaymentAllocation")
    groups = {}
    for row in PaymentAllocation.objects.exclude(request_key="").order_by("id").only("id", "payment_id", "request_key"):
        if SUFFIXED.search(row.request_key):
            continue
        groups.setdefault((row.payment_id, row.request_key), []).append(row.pk)
    for (_payment, key), ids in groups.items():
        for index, pk in enumerate(ids):
            PaymentAllocation.objects.filter(pk=pk).update(request_key=f"{key[:56]}:{index}")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0021_invoice_campaign"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(split_shared_keys, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="paymentallocation",
            constraint=models.UniqueConstraint(
                condition=models.Q(("request_key", ""), _negated=True),
                fields=("payment", "request_key"),
                name="uniq_allocation_request_key",
            ),
        ),
    ]
