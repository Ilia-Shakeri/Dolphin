from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auditlog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="activitylog",
            name="actor_role_snapshot",
            field=models.CharField(blank=True, db_index=True, max_length=32),
        ),
        migrations.AddField(
            model_name="activitylog",
            name="object_role_snapshot",
            field=models.CharField(blank=True, db_index=True, max_length=32),
        ),
    ]
