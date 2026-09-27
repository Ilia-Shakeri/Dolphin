from django.db import migrations, models


class Migration(migrations.Migration):
    """Six bundled Persian typefaces join the panel font choices (2.18.7).

    Choices only: every value saved before this is still a valid choice.
    """

    dependencies = [
        ("common", "0007_panel_font_scale_three_steps"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userpreference",
            name="font_family",
            field=models.CharField(
                choices=[
                    ("iransans", "ایران‌سنس (پیش‌فرض)"),
                    ("vazirmatn", "وزیرمتن"),
                    ("estedad", "استعداد"),
                    ("sahel", "ساحل"),
                    ("shabnam", "شبنم"),
                    ("samim", "صمیم"),
                    ("parastoo", "پرستو"),
                    ("tahoma", "تاهوما"),
                    ("nazanin", "بی‌نازنین"),
                    ("mitra", "بی‌میترا"),
                    ("system", "قلم سیستم"),
                ],
                default="iransans",
                max_length=16,
            ),
        ),
    ]
