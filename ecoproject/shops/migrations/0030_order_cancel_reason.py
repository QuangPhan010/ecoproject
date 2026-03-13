from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0029_category_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="cancel_reason",
            field=models.TextField(blank=True),
        ),
    ]
