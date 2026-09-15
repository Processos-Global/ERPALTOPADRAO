from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0025_corrigir_processos_grande_fornecedor_legados"),
    ]

    operations = [
        migrations.AddField(
            model_name="grandefornecedoritem",
            name="previsao_entrega",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="grandefornecedoritem",
            name="status",
            field=models.CharField(
                choices=[
                    ("AGUARDANDO", "Pedido gerado"),
                    ("CONFIRMADO", "Confirmado"),
                    ("PRODUCAO", "Em produção"),
                    ("PRONTO", "Pronto para expedição"),
                    ("TRANSPORTE", "Em transporte"),
                    ("PARCIAL", "Entrega parcial"),
                    ("ENTREGUE", "Entregue"),
                    ("CANCELADO", "Cancelado"),
                ],
                db_index=True,
                default="AGUARDANDO",
                max_length=20,
            ),
        ),
    ]
