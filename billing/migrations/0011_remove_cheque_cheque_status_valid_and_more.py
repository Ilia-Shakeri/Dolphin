"""Split the cheque's single seven-value status into حالت + وضعیت.

The product owner's staff never thought of a cheque as being in one of seven
states. They thought of two questions with separate answers — *has it been
registered?* and *what happened to it?* — and the old enum kept forcing those
into one column, which is why `registered` and `deposited` were really the same
answer to the first question and no answer at all to the second.

**Nothing is discarded.** Every row's original value is copied verbatim into
`legacy_status` before its status is rewritten, and the reverse migration
restores it exactly. The mapping below is therefore re-derivable if any part of
it is later judged wrong.

The mapping:

===============  ==============  ==========  ====================================
old status       is_registered   status      why
===============  ==============  ==========  ====================================
registered       False           pending     In hand, not yet handed to the bank.
deposited        True            pending     With the bank, outcome not yet known.
cleared          True            cleared     Banked and paid.
bounced          True            bounced     Banked and refused.
spent            False           spent       Endorsed onward; never went to a bank.
returned         False           pending     See the caveat below.
cancelled        False           pending     See the caveat below.
===============  ==============  ==========  ====================================

**Caveat, and the one assumption in this file.** `returned` (عودت به مشتری) and
`cancelled` (لغوشده) have no home among the four values the product owner
specified — both mean *this instrument is finished and no money came through
it*, which the new وضعیت axis does not express. They are mapped to the neutral
`pending` rather than to `bounced`, because calling them bounced would assert a
bank refusal that never happened.

That mapping does **not** resurrect them as live money: the `Payment` beneath
each was already moved to `cancelled` by the old transition rules, and every
figure in the product is computed from payment status, not from cheque status.
So the effect is confined to how such a row is labelled in the cheque list.

If the product owner wants a distinct label for them, `legacy_status` still
holds the truth and a follow-up migration can act on it without any loss.
"""

from django.db import migrations, models


#: old value -> (is_registered, new status)
FORWARD = {
    "registered": (False, "pending"),
    "deposited": (True, "pending"),
    "cleared": (True, "cleared"),
    "bounced": (True, "bounced"),
    "spent": (False, "spent"),
    "returned": (False, "pending"),
    "cancelled": (False, "pending"),
}


def split_status_into_two_axes(apps, schema_editor):
    Cheque = apps.get_model("billing", "Cheque")
    for old_value, (registered, new_value) in FORWARD.items():
        # `legacy_status` is written from the column being replaced, so the
        # original survives even for the two values whose mapping is a
        # judgement call.
        Cheque.objects.filter(status=old_value).update(
            legacy_status=old_value,
            is_registered=registered,
            status=new_value,
        )


def restore_single_status(apps, schema_editor):
    """Put back exactly what was there, from the preserved column."""
    Cheque = apps.get_model("billing", "Cheque")
    for old_value in FORWARD:
        Cheque.objects.filter(legacy_status=old_value).update(
            status=old_value, legacy_status=""
        )
    # A cheque created after this migration has no legacy value to go back to.
    # `registered` is the pre-1.3.0 default and the only honest destination.
    Cheque.objects.filter(legacy_status="").update(status="registered")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0010_remove_cheque_cheque_status_valid_and_more"),
    ]

    operations = [
        # The old constraint has to go first: while it stands, no row may hold
        # one of the four new values.
        migrations.RemoveConstraint(model_name="cheque", name="cheque_status_valid"),
        migrations.AddField(
            model_name="cheque",
            name="is_registered",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="cheque",
            name="legacy_status",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.AddField(
            model_name="cheque",
            name="registered_on",
            field=models.DateField(blank=True, null=True),
        ),
        # Data before the new constraint, or every existing row would violate it.
        migrations.RunPython(split_status_into_two_axes, restore_single_status),
        migrations.AlterField(
            model_name="cheque",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "در انتظار"),
                    ("cleared", "وصول شده"),
                    ("bounced", "برگشت"),
                    ("spent", "خرج شده"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="cheque",
            constraint=models.CheckConstraint(
                condition=models.Q(("status__in", ["pending", "cleared", "bounced", "spent"])),
                name="cheque_status_valid",
            ),
        ),
    ]
