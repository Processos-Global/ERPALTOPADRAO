from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0032_status_operacionais_grande_fornecedor"),
    ]

    operations = [
        migrations.AlterField(
            model_name="processocompra",
            name="item_cronograma",
            field=models.ForeignKey(
                blank=True,
                help_text="Suprimento de origem. Fica vazio nas compras avulsas.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="processos_compra",
                to="planejamento.itemcronogramasuprimento",
            ),
        ),
    ]
