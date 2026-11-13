from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0034_rateio_gf_fornecedor_vencimento"),
        ("financeiro", "0005_especificacao_pagamento"),
    ]

    operations = [
        migrations.AddField(
            model_name="processocompra",
            name="apropriacao",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="processos_compra",
                to="financeiro.planofinanceiro",
                help_text="Apropriação financeira definida na abertura da compra.",
            ),
        ),
        migrations.AddField(
            model_name="rateioparcelagrandefornecedor",
            name="forma_pagamento",
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
