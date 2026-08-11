from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("planejamento", "0008_itemcronogramasuprimento_datas_manuais"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="data_real_cotacao",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="data_real_compatibilizacao",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="itemcronogramasuprimento",
            name="data_real_negociacao",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
    ]
