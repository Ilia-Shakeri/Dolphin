from django.db import migrations, models


def fill_channels(apps, schema_editor):
    Campaign = apps.get_model("sales", "Campaign")
    for campaign in Campaign.objects.filter(channels=[]).iterator():
        campaign.channels = [campaign.channel]
        campaign.save(update_fields=["channels"])


class Migration(migrations.Migration):
    """Expand-only: `channel` stays (rollback to 2.38.x reads it); idempotent backfill."""

    dependencies = [("sales", "0029_campaigns")]

    operations = [
        migrations.AddField("campaign", "channels", models.JSONField(blank=True, default=list)),
        migrations.RunPython(fill_channels, migrations.RunPython.noop),
    ]
