from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("obras", "0005_fvs"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fvs",
            name="ambientes",
            field=models.ManyToManyField(related_name="fvs", to="obras.ambientefichatecnica", verbose_name="Ambientes"),
        ),
    ]
