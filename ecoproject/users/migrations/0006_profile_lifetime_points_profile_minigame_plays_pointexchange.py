from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def init_lifetime_points(apps, schema_editor):
    Profile = apps.get_model("users", "Profile")
    for profile in Profile.objects.all().iterator():
        profile.lifetime_points = profile.points
        profile.save(update_fields=["lifetime_points"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_profile_points_alter_profile_rank"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="lifetime_points",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="profile",
            name="minigame_plays",
            field=models.IntegerField(default=0),
        ),
        migrations.CreateModel(
            name="PointExchange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("exchange_type", models.CharField(choices=[("VOUCHER", "Doi voucher"), ("MINIGAME", "Doi luot choi minigame")], max_length=20)),
                ("points_spent", models.PositiveIntegerField()),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="point_exchanges", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.RunPython(init_lifetime_points, migrations.RunPython.noop),
    ]
