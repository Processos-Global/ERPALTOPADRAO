from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("financeiro", "0012_classificacao_avulsa")]
    operations = [
        migrations.AddField(
            model_name="titulopagar", name="meio_pagamento",
            field=models.CharField(max_length=20, blank=True, choices=[
                ("BOLETO", "Boleto"), ("PIX", "PIX"),
                ("TRANSFERENCIA", "Transferência"), ("DEPOSITO", "Depósito"),
                ("OUTRO", "Outro"),
            ], help_text="Meio previsto; pode ser confirmado na emissão do malote."),
        ),
    ]
