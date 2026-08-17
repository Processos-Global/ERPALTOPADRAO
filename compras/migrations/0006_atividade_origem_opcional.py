from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0005_correcao_fluxo_pedidos_recebimentos"),
    ]

    operations = [
        migrations.AlterField(
            model_name="necessidadecompra",
            name="atividade_origem",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Opcional. Quando vazio, o item atende ao conjunto de "
                    "atividades vinculadas ao processo de compra."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="necessidades_compra",
                to="planejamento.atividadeplanejamento",
            ),
        ),
        migrations.AlterModelOptions(
            name="necessidadecompra",
            options={"ordering": ("descricao", "id")},
        ),
    ]
