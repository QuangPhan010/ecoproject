from django.db import migrations, models
import random


def fill_tracking_code(apps, schema_editor):
    Order = apps.get_model('shops', 'Order')
    for order in Order.objects.filter(tracking_code=''):
        order.tracking_code = f"QSHOP{random.randint(1000, 9999)}"
        order.save(update_fields=['tracking_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0018_couponusage'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='tracking_code',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.RunPython(fill_tracking_code, migrations.RunPython.noop),
    ]
