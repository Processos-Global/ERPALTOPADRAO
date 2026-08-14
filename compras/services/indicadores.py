from datetime import timedelta

from planejamento.models import RegistroCronograma


def data_inicio_planejada_atividade(atividade):
    return (
        RegistroCronograma.objects.filter(
            atividade_planejamento=atividade,
            importacao__ativa=True,
            importacao__status="CONCLUIDA",
            inicio_base__isnull=False,
        )
        .order_by("-data_atualizacao", "-semana", "-id")
        .values_list("inicio_base", flat=True)
        .first()
    )


def risco_pedido(pedido):
    previsao = pedido.previsao_entrega_atual or pedido.previsao_entrega_original
    if not previsao:
        return {"nivel": "SEM_PREVISAO", "margem_dias": None, "label": "Sem previsão"}

    datas = []
    for item in pedido.itens.select_related("necessidade__atividade_origem"):
        data = data_inicio_planejada_atividade(item.necessidade.atividade_origem)
        if data:
            datas.append(data)
    if not datas:
        return {"nivel": "SEM_DATA_ATIVIDADE", "margem_dias": None, "label": "Sem data da atividade"}

    inicio = min(datas)
    margem = (inicio - previsao).days
    if margem < 0:
        return {"nivel": "RISCO", "margem_dias": margem, "label": f"Impacto potencial de {abs(margem)} dia(s)"}
    if margem <= 7:
        return {"nivel": "ATENCAO", "margem_dias": margem, "label": f"Margem de {margem} dia(s)"}
    return {"nivel": "OK", "margem_dias": margem, "label": f"Margem de {margem} dia(s)"}
