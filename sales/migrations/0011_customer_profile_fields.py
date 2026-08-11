from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sales", "0010_interaction_contract")]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="category",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="customer",
            name="postal_code",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
