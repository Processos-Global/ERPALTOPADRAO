from django.db import migrations, models


def limpar_fluxo_antigo(apps, schema_editor):
    """
    Os dados atuais são de teste e dependem do antigo SuprimentoAtividade.
    Limpamos o fluxo transacional antes de remover as FKs legadas.
    Cadastros de fornecedores e alçadas são preservados.
    """
    ordem = [
        "HistoricoPrevisaoPedido",
        "ParcelaPrevistaPedido",
        "PedidoCompraItem",
        "PedidoCompra",
        "ContratacaoCompra",
        "AprovacaoCompra",
        "AdjudicacaoCompra",
        "HistoricoNegociacaoItem",
        "NegociacaoItem",
        "CompatibilizacaoItem",
        "CotacaoFornecedorItem",
        "CotacaoFornecedor",
        "HistoricoProcessoCompra",
        "NecessidadeCompra",
        "ProcessoCompraAtividade",
        "ProcessoCompra",
    ]
    for nome in ordem:
        model = apps.get_model("compras", nome)
        model.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0009_itemcronogramasuprimento_datas_realizadas"),
        ("compras", "0003_cotacao_item_unico"),
    ]

    operations = [
        migrations.RunPython(limpar_fluxo_antigo, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="necessidadecompra",
            name="suprimento_origem",
        ),
        migrations.RemoveField(
            model_name="necessidadecompra",
            name="insumo",
        ),
        migrations.AddField(
            model_name="necessidadecompra",
            name="especificacao",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="necessidadecompra",
            name="unidade",
            field=models.CharField(
                choices=[
                    ("UN", "Unidade"), ("M", "Metro"), ("M2", "Metro quadrado"),
                    ("M3", "Metro cúbico"), ("KG", "Quilograma"), ("T", "Tonelada"),
                    ("L", "Litro"), ("SC", "Saco"), ("CX", "Caixa"), ("PC", "Peça"),
                    ("GL", "Galão"), ("RL", "Rolo"), ("PT", "Pacote"), ("VB", "Verba"),
                ],
                max_length=10,
            ),
        ),
        migrations.RemoveField(
            model_name="pedidocompraitem",
            name="insumo",
        ),
        migrations.AddField(
            model_name="pedidocompraitem",
            name="especificacao",
            field=models.TextField(blank=True),
        ),
    ]
