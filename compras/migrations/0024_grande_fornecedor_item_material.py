from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cadastros", "0003_remover_atividade_subatividade_material"),
        ("compras", "0023_grande_fornecedor_aprovacao_por_item"),
    ]

    operations = [
        migrations.AddField(
            model_name="grandefornecedoritem",
            name="material",
            field=models.ForeignKey(
                blank=True,
                help_text="Material selecionado do catálogo central. Obrigatório para novos itens.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="itens_grande_fornecedor",
                to="cadastros.material",
            ),
        ),
    ]
