from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_mysteryboxrewardoption_box_tier"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="premium_voucher_pity",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile",
            name="standard_voucher_pity",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
