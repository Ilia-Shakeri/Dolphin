# Generated for Dolphin 2026-09-22: installment plans gain an optional
# down payment, an optional extra discount, and an optional annual profit
# rate. `total_amount` now means "the amount actually divided across
# installments" (principal + interest) rather than always equalling the
# invoice total; `principal_amount` is backfilled from the existing
# `total_amount` for every plan created before this migration, which leaves
# those plans' arithmetic — and their installments — completely unchanged.

from decimal import Decimal

from django.db import migrations, models


def backfill_principal_amount(apps, schema_editor):
    InstallmentPlan = apps.get_model("billing", "InstallmentPlan")
    InstallmentPlan.objects.filter(principal_amount__isnull=True).update(
        principal_amount=models.F("total_amount")
    )


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0013_invoice_document_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='installmentplan',
            name='down_payment_percent',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name='installmentplan',
            name='down_payment_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True),
        ),
        migrations.AddField(
            model_name='installmentplan',
            name='extra_discount_percent',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=5),
        ),
        migrations.AddField(
            model_name='installmentplan',
            name='annual_profit_rate',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=6),
        ),
        migrations.AddField(
            model_name='installmentplan',
            name='interest_amount',
            field=models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=18),
        ),
        migrations.AddField(
            model_name='installmentplan',
            name='principal_amount',
            field=models.DecimalField(decimal_places=2, max_digits=18, null=True),
        ),
        migrations.RunPython(backfill_principal_amount, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='installmentplan',
            name='principal_amount',
            field=models.DecimalField(decimal_places=2, max_digits=18),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=models.Q(('principal_amount__gt', 0)),
                name='installment_plan_principal_positive',
            ),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=models.Q(('interest_amount__gte', 0)),
                name='installment_plan_interest_non_negative',
            ),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=models.Q(('total_amount', models.F('principal_amount') + models.F('interest_amount'))),
                name='installment_plan_total_equals_principal_plus_interest',
            ),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=models.Q(('extra_discount_percent__gte', 0)) & models.Q(('extra_discount_percent__lte', 100)),
                name='installment_plan_discount_percent_bounded',
            ),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=models.Q(('annual_profit_rate__gte', 0)),
                name='installment_plan_profit_rate_non_negative',
            ),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=models.Q(('down_payment_percent__isnull', True)) | models.Q(('down_payment_amount__isnull', True)),
                name='installment_plan_down_payment_percent_xor_amount',
            ),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(('down_payment_percent__isnull', True))
                    | (models.Q(('down_payment_percent__gte', 0)) & models.Q(('down_payment_percent__lt', 100)))
                ),
                name='installment_plan_down_payment_percent_bounded',
            ),
        ),
        migrations.AddConstraint(
            model_name='installmentplan',
            constraint=models.CheckConstraint(
                condition=models.Q(('down_payment_amount__isnull', True)) | models.Q(('down_payment_amount__gte', 0)),
                name='installment_plan_down_payment_amount_non_negative',
            ),
        ),
    ]
