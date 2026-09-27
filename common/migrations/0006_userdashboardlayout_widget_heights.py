from django.db import migrations, models


class Migration(migrations.Migration):
    """Per-widget minimum height for the dashboard editor (2.18.4).

    Additive only: an empty map means "every box at its content's own
    height", which is exactly how every existing layout already renders.
    """

    dependencies = [
        ("common", "0005_backupjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="userdashboardlayout",
            name="widget_heights",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
