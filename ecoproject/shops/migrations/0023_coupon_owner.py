from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0022_coupon_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="coupon",
            name="owner",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="owned_coupons", to=settings.AUTH_USER_MODEL),
        ),
    ]
