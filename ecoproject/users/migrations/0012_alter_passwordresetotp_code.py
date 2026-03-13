from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_passwordresetotp"),
    ]

    operations = [
        migrations.AlterField(
            model_name="passwordresetotp",
            name="code",
            field=models.CharField(max_length=128),
        ),
    ]
