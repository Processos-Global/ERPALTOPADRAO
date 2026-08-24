from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0011_fluxo_proposta_individual_e_avaliacao_fornecedor"),
    ]

    operations = [
        migrations.AddField(
            model_name="processocompra",
            name="fornecedor_sugerido",
            field=models.ForeignKey(
                blank=True,
                help_text="Fornecedor indicado no pedido inicial para orientar o Suprimentos.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="processos_compra_sugeridos",
                to="compras.fornecedorcompra",
            ),
        ),
    ]
