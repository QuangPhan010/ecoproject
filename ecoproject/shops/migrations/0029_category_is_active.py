from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0028_order_shops_order_user_id_f946a3_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
