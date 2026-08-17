from planejamento.models import RegistroCronograma


def data_inicio_planejada_atividade(atividade):
    if atividade is None:
        return None

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


def _datas_inicio_processo(processo):
    """
    Datas das atividades vinculadas ao processo.

    É o fallback utilizado para itens criados pela nova abertura de compra,
    em que a atividade é selecionada uma única vez no nível do processo e
    não é repetida em cada item.
    """
    datas = []
    vinculos = (
        processo.vinculos_atividades
        .select_related("atividade")
        .all()
    )
    for vinculo in vinculos:
        data = data_inicio_planejada_atividade(vinculo.atividade)
        if data:
            datas.append(data)
    return datas


def risco_pedido(pedido):
    previsao = pedido.previsao_entrega_atual or pedido.previsao_entrega_original
    if not previsao:
        return {"nivel": "SEM_PREVISAO", "margem_dias": None, "label": "Sem previsão"}

    datas = []
    precisa_fallback_processo = False

    for item in pedido.itens.select_related("necessidade__atividade_origem"):
        atividade = item.necessidade.atividade_origem
        if atividade is None:
            precisa_fallback_processo = True
            continue

        data = data_inicio_planejada_atividade(atividade)
        if data:
            datas.append(data)

    if precisa_fallback_processo or not datas:
        datas.extend(_datas_inicio_processo(pedido.processo))

    # Remove duplicidades sem perder objetos date.
    datas = list(dict.fromkeys(datas))

    if not datas:
        return {
            "nivel": "SEM_DATA_ATIVIDADE",
            "margem_dias": None,
            "label": "Sem data das atividades",
        }

    inicio = min(datas)
    margem = (inicio - previsao).days

    if margem < 0:
        return {
            "nivel": "RISCO",
            "margem_dias": margem,
            "label": f"Impacto potencial de {abs(margem)} dia(s)",
        }
    if margem <= 7:
        return {
            "nivel": "ATENCAO",
            "margem_dias": margem,
            "label": f"Margem de {margem} dia(s)",
        }
    return {
        "nivel": "OK",
        "margem_dias": margem,
        "label": f"Margem de {margem} dia(s)",
    }
