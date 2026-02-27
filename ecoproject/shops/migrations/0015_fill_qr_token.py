from django.db import migrations
import uuid

def fill_qr_tokens(apps, schema_editor):
    Order = apps.get_model('shops', 'Order')
    for order in Order.objects.filter(qr_token__isnull=True):
        order.qr_token = uuid.uuid4()
        order.save(update_fields=['qr_token'])

class Migration(migrations.Migration):

    dependencies = [
        ('shops', '0014_order_qr_token'),
    ]

    operations = [
        migrations.RunPython(fill_qr_tokens),
    ]
