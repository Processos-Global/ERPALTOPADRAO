from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("financeiro", "0004_financeiro_v2_contas_parcelas")]
    operations = [
        migrations.AddField(
            model_name="titulopagar",
            name="especificacao_pagamento",
            field=models.TextField(blank=True, help_text="Detalhamento do que está sendo pago: itens, especificações, parcela e origem."),
        ),
    ]
