from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planejamento", "0006_cronograma_suprimentos_real"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="data_real_contratacao",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
    ]
