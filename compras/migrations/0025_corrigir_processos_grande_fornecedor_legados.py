from django.db import migrations


def corrigir_processos(apps, schema_editor):
    Processo = apps.get_model("compras", "ProcessoCompra")

    # Corrige apenas processos ainda no começo do fluxo normal e sem cotação/pedido.
    # Processos que já avançaram permanecem intocados para não alterar histórico.
    candidatos = (
        Processo.objects
        .filter(
            fluxo_grande_fornecedor=False,
            item_cronograma__tipo_fluxo_compra="GRANDE_FORNECEDOR",
            status__in=[
                "RASCUNHO",
                "PEDIDO_ENVIADO",
                "SOLICITACAO_COTACAO",
                "AGUARDANDO_COTACAO",
            ],
        )
        .exclude(cotacoes__isnull=False)
        .exclude(pedidos__isnull=False)
        .distinct()
    )
    candidatos.update(
        fluxo_grande_fornecedor=True,
        etapa_atual="COMPATIBILIZACAO",
        status="EM_COMPATIBILIZACAO",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("planejamento", "0014_reclassificar_fluxo_compra_por_categoria"),
        ("compras", "0024_grande_fornecedor_item_material"),
    ]

    operations = [
        migrations.RunPython(corrigir_processos, migrations.RunPython.noop),
    ]
