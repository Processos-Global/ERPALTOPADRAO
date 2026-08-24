from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compras", "0013_processo_fornecedores_sugeridos"),
    ]

    operations = [
        migrations.AlterField(
            model_name="processocompra",
            name="status",
            field=models.CharField(
                choices=[
                    ("RASCUNHO", "Rascunho"),
                    ("PEDIDO_ENVIADO", "Solicitação enviada"),
                    ("SOLICITACAO_COTACAO", "Aguardando fornecedor"),
                    ("AGUARDANDO_COTACAO", "Aguardando fornecedor"),
                    ("EM_COTACAO", "Proposta recebida"),
                    ("AGUARDANDO_COMPATIBILIZACAO", "Aguardando análise técnica"),
                    ("EM_COMPATIBILIZACAO", "Em análise técnica"),
                    ("EM_NEGOCIACAO", "Em negociação"),
                    ("AGUARDANDO_APROVACAO", "Aguardando aprovação"),
                    ("AJUSTE_SOLICITADO", "Ajuste solicitado"),
                    ("APROVADO", "Aprovado"),
                    ("EM_CONTRATACAO", "Em contratação"),
                    ("CONTRATADO", "Contratado"),
                    ("REPROVADO", "Reprovado"),
                    ("CANCELADO", "Cancelado"),
                ],
                db_index=True,
                default="RASCUNHO",
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="pedidocompra",
            name="status",
            field=models.CharField(
                choices=[
                    ("PEDIDO_EMITIDO", "Aguardando fornecedor"),
                    ("CONFIRMADO", "Confirmado"),
                    ("EM_PRODUCAO", "Em produção"),
                    ("PRONTO_EXPEDICAO", "Pronto para expedição"),
                    ("EM_TRANSPORTE", "Em transporte"),
                    ("ENTREGA_PARCIAL", "Entrega parcial"),
                    ("ENTREGUE", "Entregue"),
                    ("CANCELADO", "Cancelado"),
                ],
                db_index=True,
                default="PEDIDO_EMITIDO",
                max_length=30,
            ),
        ),
    ]
