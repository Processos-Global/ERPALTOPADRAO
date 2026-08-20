from __future__ import annotations

from decimal import Decimal

from django.db.models import Prefetch
from django.utils import timezone

from planejamento.models.cronograma_suprimentos import (
    ImportacaoCronogramaSuprimentos,
    ItemCronogramaSuprimento,
)


ETAPAS_FILTRO = [
    (ItemCronogramaSuprimento.Etapa.COTACAO, "Cotação"),
    (ItemCronogramaSuprimento.Etapa.COMPATIBILIZACAO, "Compatibilização"),
    (ItemCronogramaSuprimento.Etapa.NEGOCIACAO, "Negociação"),
    (ItemCronogramaSuprimento.Etapa.CONTRATACAO, "Contratação"),
    (ItemCronogramaSuprimento.Etapa.CONCLUIDO, "Concluído"),
]


STATUS_PEDIDO_CLASSE = {
    "PEDIDO_EMITIDO": "info",
    "CONFIRMADO": "info",
    "EM_PRODUCAO": "info",
    "PRONTO_EXPEDICAO": "info",
    "EM_TRANSPORTE": "info",
    "ENTREGA_PARCIAL": "warning",
    "ENTREGUE": "success",
    "CANCELADO": "danger",
}


def _filtrar_por_etapa(itens, etapa: str):
    if not etapa:
        return itens
    return [item for item in itens if item.etapa_atual == etapa]


def _decorar_desvio(item, atributo: str, desvio):
    """Prepara valor, classe visual e texto do desvio Planejado x Realizado."""
    setattr(item, f"{atributo}_desvio_dias", desvio)

    if desvio is None:
        setattr(item, f"{atributo}_desvio_classe", "")
        setattr(item, f"{atributo}_desvio_label", "")
        return

    if desvio > 0:
        classe = "late"
        label = f"+{desvio} dia{'s' if desvio != 1 else ''}"
    elif desvio < 0:
        dias = abs(desvio)
        classe = "early"
        label = f"-{dias} dia{'s' if dias != 1 else ''}"
    else:
        classe = "ontime"
        label = "No prazo"

    setattr(item, f"{atributo}_desvio_classe", classe)
    setattr(item, f"{atributo}_desvio_label", label)


def _decorar_item(item, hoje):
    item.percentual_calculado = item.percentual_andamento
    item.etapas_concluidas = item.percentual_andamento // 25
    item.etapa_calculada = item.etapa_atual
    item.etapa_calculada_label = item.etapa_atual_label
    item.prazo_etapa_atual = item.data_planejada_etapa_atual
    item.dias_atraso_calculado = item.dias_atraso_etapa_atual
    item.atrasado_calculado = item.etapa_atual_atrasada

    item.cotacao_atrasada = bool(
        not item.data_real_cotacao and item.data_cotacao and item.data_cotacao < hoje
    )
    item.compatibilizacao_atrasada = bool(
        not item.data_real_compatibilizacao
        and item.data_compatibilizacao
        and item.data_compatibilizacao < hoje
    )
    item.negociacao_atrasada = bool(
        not item.data_real_negociacao
        and item.data_negociacao
        and item.data_negociacao < hoje
    )
    item.contratacao_atrasada = bool(
        not item.data_real_contratacao
        and item.prazo_limite_contratacao
        and item.prazo_limite_contratacao < hoje
    )

    _decorar_desvio(item, "cotacao", item.desvio_cotacao_dias)
    _decorar_desvio(item, "compatibilizacao", item.desvio_compatibilizacao_dias)
    _decorar_desvio(item, "negociacao", item.desvio_negociacao_dias)
    _decorar_desvio(item, "contratacao", item.desvio_contratacao_dias)
    return item


def _decimal(valor):
    return valor if isinstance(valor, Decimal) else Decimal(valor or 0)


def _moeda_br(valor):
    if valor is None:
        return "—"
    valor = _decimal(valor).quantize(Decimal("0.01"))
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _quantidade_br(valor):
    if valor is None:
        return "—"
    numero = _decimal(valor)
    # Mantém até 4 casas decimais, removendo zeros desnecessários.
    texto = f"{numero:.4f}".rstrip("0").rstrip(".")
    inteiro, sep, decimais = texto.partition(".")
    inteiro_br = f"{int(inteiro):,}".replace(",", ".")
    return inteiro_br + (("," + decimais) if sep else "")


def _mais_recente(*datas):
    validas = [data for data in datas if data]
    return max(validas) if validas else None


def _ultimo_resultado_compat(item_cotado):
    historico = list(item_cotado.compatibilizacoes.all())
    return historico[0] if historico else None


def _valor_cotado(cotacao):
    itens = list(cotacao.itens.all())
    if not itens:
        return None
    return sum((_decimal(item.valor_total_cotado) for item in itens), Decimal("0")) + _decimal(cotacao.frete)


def _negociacao_tem_alteracao(item, negociacao):
    """
    Retorna True somente quando existe alguma condição comercial realmente
    alterada em relação à proposta original.

    Isso também corrige registros antigos criados apenas porque prazo/pagamento
    originais foram enviados automaticamente pelo formulário de negociação.
    """
    if negociacao is None:
        return False

    if negociacao.valor_unitario_negociado is not None:
        return True
    if negociacao.frete_negociado is not None:
        return True
    if (negociacao.observacoes or "").strip():
        return True

    if (
        negociacao.prazo_entrega_dias_negociado is not None
        and negociacao.prazo_entrega_dias_negociado != item.cotacao.prazo_entrega_dias
    ):
        return True

    pagamento_negociado = (negociacao.condicao_pagamento_negociada or "").strip()
    pagamento_original = (item.cotacao.condicao_pagamento or "").strip()
    if pagamento_negociado and pagamento_negociado != pagamento_original:
        return True

    return False


def _valor_negociado(cotacao):
    itens = list(cotacao.itens.all())
    if not itens:
        return None

    negociacoes_reais = []
    for item in itens:
        negociacao = getattr(item, "negociacao", None)
        if _negociacao_tem_alteracao(item, negociacao):
            negociacoes_reais.append((item, negociacao))

    # Se nenhuma condição comercial foi efetivamente alterada, não existe
    # "valor negociado" a exibir. O preço permanece apenas como valor cotado.
    if not negociacoes_reais:
        return None

    total = Decimal("0")
    for item in itens:
        negociacao = getattr(item, "negociacao", None)
        negociacao_real = _negociacao_tem_alteracao(item, negociacao)
        tem_preco_negociado = bool(
            negociacao_real and negociacao.valor_unitario_negociado is not None
        )
        unitario = (
            negociacao.valor_unitario_negociado
            if tem_preco_negociado
            else item.valor_unitario_cotado
        )
        desconto = Decimal("0") if tem_preco_negociado else _decimal(item.desconto_cotado)
        total += max(
            _decimal(item.quantidade) * _decimal(unitario) - desconto,
            Decimal("0"),
        )

    fretes_informados = [
        negociacao
        for item, negociacao in negociacoes_reais
        if negociacao.frete_negociado is not None
    ]
    if fretes_informados:
        frete_mais_recente = max(fretes_informados, key=lambda n: (n.atualizado_em, n.id))
        frete = frete_mais_recente.frete_negociado
    else:
        frete = cotacao.frete

    total += _decimal(frete)
    return total


def _status_compatibilizacao(cotacao):
    itens = list(cotacao.itens.all())
    if not itens:
        return {"label": "—", "classe": "muted", "estado": "SEM_PROPOSTA"}

    resultados = []
    pendentes = 0
    for item in itens:
        ultimo = _ultimo_resultado_compat(item)
        if ultimo is None:
            pendentes += 1
        else:
            resultados.append(ultimo.resultado)

    aprovados = {"APROVADO", "APROVADO_COM_RESSALVA"}
    if resultados and all(resultado == "REPROVADO" for resultado in resultados) and not pendentes:
        return {"label": "Reprovado técnico", "classe": "danger", "estado": "REPROVADO"}
    if not pendentes and resultados and all(resultado in aprovados for resultado in resultados):
        return {"label": "Compatibilizado", "classe": "success", "estado": "APROVADO"}
    if resultados:
        return {"label": "Em análise", "classe": "warning", "estado": "PARCIAL"}
    return {"label": "Pendente", "classe": "muted", "estado": "PENDENTE"}


def _status_negociacao(cotacao, compat):
    itens = list(cotacao.itens.all())
    if not itens or compat["estado"] in {"SEM_PROPOSTA", "REPROVADO", "PENDENTE"}:
        return {"label": "—", "classe": "muted", "estado": "NAO_APLICAVEL"}

    elegiveis = []
    for item in itens:
        ultimo = _ultimo_resultado_compat(item)
        if ultimo and ultimo.resultado in {"APROVADO", "APROVADO_COM_RESSALVA"}:
            elegiveis.append(item)

    if not elegiveis:
        return {"label": "—", "classe": "muted", "estado": "NAO_APLICAVEL"}

    negociados = sum(
        1
        for item in elegiveis
        if _negociacao_tem_alteracao(item, getattr(item, "negociacao", None))
    )
    if negociados == len(elegiveis):
        return {"label": "Negociado", "classe": "success", "estado": "CONCLUIDO"}
    if negociados:
        return {"label": "Em negociação", "classe": "warning", "estado": "PARCIAL"}
    return {"label": "Pendente", "classe": "warning", "estado": "PENDENTE"}


def _montar_linha_fornecedor(cotacao, processo):
    itens = list(cotacao.itens.all())
    proposta_recebida = bool(itens)
    compat = _status_compatibilizacao(cotacao)
    negociacao = _status_negociacao(cotacao, compat)

    adjudicacoes = [a for a in cotacao.adjudicacoes.all() if not a.cancelada]
    pedidos = [
        pedido
        for pedido in processo.pedidos.all()
        if pedido.fornecedor_id == cotacao.fornecedor_id
    ]
    pedidos_ativos = [pedido for pedido in pedidos if pedido.status != "CANCELADO"]

    # A compatibilização técnica e a aprovação do gestor são etapas distintas.
    # Se o processo foi reprovado pelo gestor, uma proposta tecnicamente aceita
    # não pode aparecer como "Aprovado" apenas porque existe adjudicação residual.
    if processo.status == "REPROVADO" and compat["estado"] == "APROVADO":
        aprovacao = {
            "label": "Reprovado pelo gestor",
            "classe": "danger",
            "estado": "REPROVADO_GESTOR",
        }
    elif adjudicacoes:
        aprovacao = {"label": "Aprovado", "classe": "success", "estado": "APROVADO"}
    elif processo.status == "AGUARDANDO_APROVACAO" and compat["estado"] == "APROVADO":
        aprovacao = {"label": "Aguardando gestor", "classe": "warning", "estado": "AGUARDANDO"}
    elif processo.status in {"APROVADO", "EM_CONTRATACAO", "CONTRATADO"} and proposta_recebida:
        aprovacao = {"label": "Não selecionado", "classe": "muted", "estado": "NAO_SELECIONADO"}
    else:
        aprovacao = {"label": "—", "classe": "muted", "estado": "NAO_APLICAVEL"}

    valor_aprovado = (
        sum((_decimal(a.valor_total) for a in adjudicacoes), Decimal("0"))
        if adjudicacoes
        else None
    )
    valor_pedido = (
        sum((_decimal(p.valor_total) for p in pedidos_ativos), Decimal("0"))
        if pedidos_ativos
        else None
    )

    # Detalha os ITENS existentes dentro de cada Pedido de Compra.
    # Aqui "quantidade" é a quantidade comprada daquele item (ex.: 12 UN, 35,5 M²),
    # e não a quantidade de pedidos de compra.
    pedidos_detalhes = []
    for pedido in pedidos_ativos:
        itens_pedido = []
        for item_pedido in pedido.itens.all():
            itens_pedido.append(
                {
                    "id": item_pedido.id,
                    "descricao": item_pedido.descricao,
                    "unidade": item_pedido.unidade,
                    "quantidade": item_pedido.quantidade,
                    "quantidade_formatada": _quantidade_br(item_pedido.quantidade),
                    "quantidade_recebida": item_pedido.quantidade_recebida,
                    "quantidade_recebida_formatada": _quantidade_br(item_pedido.quantidade_recebida),
                    "valor_total": item_pedido.valor_total,
                    "valor_total_formatado": _moeda_br(item_pedido.valor_total),
                }
            )

        previsao_pedido = pedido.previsao_entrega_atual or pedido.previsao_entrega_original
        pedidos_detalhes.append(
            {
                "numero": pedido.numero,
                "quantidade_itens": len(itens_pedido),
                "itens": itens_pedido,
                "previsao_entrega": previsao_pedido,
            }
        )

    quantidade_itens_pedidos = sum(
        detalhe["quantidade_itens"] for detalhe in pedidos_detalhes
    )

    # O status final do processo precisa prevalecer sobre adjudicações/pedidos
    # residuais quando o gestor reprovou a compra. Mantemos a reprovação técnica
    # específica para fornecedores que nem chegaram elegíveis à aprovação.
    if compat["estado"] == "REPROVADO":
        status_atual = {"label": "Reprovado tecnicamente", "classe": "danger"}
    elif aprovacao["estado"] == "REPROVADO_GESTOR":
        status_atual = {"label": "Reprovado pelo gestor", "classe": "danger"}
    elif pedidos_ativos:
        pedido_atual = max(pedidos_ativos, key=lambda p: (p.atualizado_em, p.id))
        status_atual = {
            "label": pedido_atual.get_status_display(),
            "classe": STATUS_PEDIDO_CLASSE.get(pedido_atual.status, "info"),
        }
    elif adjudicacoes:
        status_atual = {"label": "Aprovado", "classe": "success"}
    elif aprovacao["estado"] == "AGUARDANDO":
        status_atual = {"label": "Em aprovação", "classe": "warning"}
    elif aprovacao["estado"] == "NAO_SELECIONADO":
        status_atual = {"label": "Não selecionado", "classe": "muted"}
    elif not proposta_recebida:
        status_atual = {"label": "Aguardando proposta", "classe": "muted"}
    elif compat["estado"] in {"PENDENTE", "PARCIAL"}:
        status_atual = {"label": "Em compatibilização", "classe": "warning"}
    elif negociacao["estado"] != "CONCLUIDO":
        status_atual = {"label": "Em negociação", "classe": "info"}
    else:
        status_atual = {"label": "Negociado", "classe": "info"}

    datas_compat = [
        registro.data
        for item in itens
        for registro in item.compatibilizacoes.all()
    ]
    datas_negociacao = [
        item.negociacao.atualizado_em
        for item in itens
        if getattr(item, "negociacao", None) is not None
    ]
    datas_adjudicacao = [a.selecionado_em for a in adjudicacoes]
    datas_pedidos = [p.atualizado_em for p in pedidos]
    ultima_atualizacao = _mais_recente(
        cotacao.atualizado_em,
        *[item.atualizado_em for item in itens],
        *datas_compat,
        *datas_negociacao,
        *datas_adjudicacao,
        *datas_pedidos,
    )

    return {
        "cotacao_id": cotacao.id,
        "processo_id": processo.id,
        "processo_numero": processo.numero,
        "fornecedor_id": cotacao.fornecedor_id,
        "fornecedor_nome": cotacao.fornecedor.nome,
        "proposta": {
            "label": "Proposta recebida" if proposta_recebida else "Não recebida",
            "classe": "success" if proposta_recebida else "muted",
        },
        "valor_cotado": _valor_cotado(cotacao),
        "valor_cotado_formatado": _moeda_br(_valor_cotado(cotacao)),
        "valor_negociado": _valor_negociado(cotacao),
        "valor_negociado_formatado": _moeda_br(_valor_negociado(cotacao)),
        "valor_aprovado": valor_aprovado,
        "valor_aprovado_formatado": _moeda_br(valor_aprovado),
        "valor_pedido": valor_pedido,
        "valor_pedido_formatado": _moeda_br(valor_pedido),
        "compatibilizacao": compat,
        "negociacao": negociacao,
        "aprovacao": aprovacao,
        "pedido_numeros": ", ".join(p.numero for p in pedidos_ativos) or "—",
        "pedidos_detalhes": pedidos_detalhes,
        "quantidade_itens_pedidos": quantidade_itens_pedidos,
        "status_atual": status_atual,
        "ultima_atualizacao": ultima_atualizacao,
    }


def _anexar_acompanhamento_compras(itens):
    """
    Anexa ao ItemCronogramaSuprimento uma visão somente-leitura do andamento
    comercial. Nenhum dado é duplicado no Planejamento: tudo vem de Compras.
    """
    if not itens:
        return

    from compras.models import (
        AdjudicacaoCompra,
        CompatibilizacaoItem,
        CotacaoFornecedor,
        CotacaoFornecedorItem,
        NegociacaoItem,
        NecessidadeCompra,
        PedidoCompra,
        ProcessoCompra,
    )

    ids = [item.id for item in itens]

    compat_qs = CompatibilizacaoItem.objects.select_related("responsavel").order_by("-data", "-id")
    negociacao_qs = NegociacaoItem.objects.select_related("atualizado_por")
    item_cotado_qs = (
        CotacaoFornecedorItem.objects
        .select_related("necessidade")
        .prefetch_related(
            Prefetch("compatibilizacoes", queryset=compat_qs),
            Prefetch("negociacao", queryset=negociacao_qs),
        )
        .order_by("id")
    )
    adjudicacao_qs = AdjudicacaoCompra.objects.filter(cancelada=False).order_by("id")
    cotacao_qs = (
        CotacaoFornecedor.objects
        .select_related("fornecedor")
        .prefetch_related(
            Prefetch("itens", queryset=item_cotado_qs),
            Prefetch("adjudicacoes", queryset=adjudicacao_qs),
        )
        .order_by("fornecedor__nome", "id")
    )
    pedido_qs = (
        PedidoCompra.objects
        .select_related("fornecedor")
        .prefetch_related("itens")
        .order_by("criado_em", "id")
    )
    necessidade_qs = (
        NecessidadeCompra.objects
        .exclude(situacao="CANCELADA")
        .select_related("atividade_origem")
        .order_by("id")
    )

    processos = (
        ProcessoCompra.objects
        .filter(item_cronograma_id__in=ids)
        .select_related("item_cronograma")
        .prefetch_related(
            Prefetch("cotacoes", queryset=cotacao_qs),
            Prefetch("pedidos", queryset=pedido_qs),
            Prefetch("necessidades", queryset=necessidade_qs),
            "vinculos_atividades__atividade",
        )
        .order_by("criado_em", "id")
    )

    por_item = {item_id: [] for item_id in ids}
    for processo in processos:
        por_item.setdefault(processo.item_cronograma_id, []).append(processo)

    for item in itens:
        linhas = []
        processos_item = por_item.get(item.id, [])

        # Previsão de entrega do suprimento: usa a previsão ATUAL do pedido
        # (com fallback para a original). Havendo vários pedidos, mostra a
        # próxima entrega pendente; quando todos já foram entregues, mantém a
        # última previsão conhecida apenas como referência histórica.
        pedidos_do_item = [
            pedido
            for processo in processos_item
            for pedido in processo.pedidos.all()
            if pedido.status != "CANCELADO"
        ]
        pedidos_pendentes = [p for p in pedidos_do_item if p.status != "ENTREGUE"]
        previsoes_pendentes = [
            p.previsao_entrega_atual or p.previsao_entrega_original
            for p in pedidos_pendentes
            if (p.previsao_entrega_atual or p.previsao_entrega_original)
        ]
        previsoes_todas = [
            p.previsao_entrega_atual or p.previsao_entrega_original
            for p in pedidos_do_item
            if (p.previsao_entrega_atual or p.previsao_entrega_original)
        ]
        item.previsao_entrega_compra = (
            min(previsoes_pendentes)
            if previsoes_pendentes
            else (max(previsoes_todas) if previsoes_todas else None)
        )
        item.previsao_entrega_atrasada = bool(
            previsoes_pendentes
            and item.previsao_entrega_compra
            and item.previsao_entrega_compra < timezone.localdate()
        )
        item.previsao_entrega_dias_atraso = (
            (timezone.localdate() - item.previsao_entrega_compra).days
            if item.previsao_entrega_atrasada
            else 0
        )
        item.previsao_entrega_qtd_pedidos = len(pedidos_do_item)

        for processo in processos_item:
            for cotacao in processo.cotacoes.all():
                linhas.append(_montar_linha_fornecedor(cotacao, processo))

        linhas.sort(key=lambda x: (x["fornecedor_nome"].casefold(), x["processo_numero"]))

        valores_cotados = [x["valor_cotado"] for x in linhas if x["valor_cotado"] is not None]
        valores_negociados = [x["valor_negociado"] for x in linhas if x["valor_negociado"] is not None]
        valores_aprovados = [x["valor_aprovado"] for x in linhas if x["valor_aprovado"] is not None]
        valores_pedidos = [x["valor_pedido"] for x in linhas if x["valor_pedido"] is not None]

        # Contexto do suprimento: atividades vinculadas ao(s) processo(s).
        # A quantidade de itens é mostrada por pedido de compra na planilha
        # de fornecedores, e não como quantidade de pedidos/necessidades.
        atividades_por_id = {}
        for processo in processos_item:
            necessidades = list(processo.necessidades.all())

            for vinculo in processo.vinculos_atividades.all():
                atividade = vinculo.atividade
                atividades_por_id[atividade.id] = atividade

            # Também considera a atividade de origem do item, quando houver,
            # para cobrir processos antigos ou itens vinculados individualmente.
            for necessidade in necessidades:
                atividade = necessidade.atividade_origem
                if atividade is not None:
                    atividades_por_id[atividade.id] = atividade

        atividades = sorted(
            atividades_por_id.values(),
            key=lambda atividade: (atividade.nome_tarefa or "").casefold(),
        )
        atividades_nomes = [
            (atividade.nome_tarefa or str(atividade)).strip()
            for atividade in atividades
        ]

        item.acompanhamento_fornecedores = linhas
        item.acompanhamento_processos = processos_item
        item.acompanhamento_tem_compras = bool(processos_item)
        item.acompanhamento_atividades = atividades
        item.acompanhamento_atividades_nomes = atividades_nomes
        item.acompanhamento_atividades_texto = " • ".join(atividades_nomes) or "—"
        ultimas_atualizacoes = [
            x["ultima_atualizacao"]
            for x in linhas
            if x.get("ultima_atualizacao") is not None
        ]
        ultima_atualizacao_geral = max(ultimas_atualizacoes) if ultimas_atualizacoes else None

        item.acompanhamento_resumo = {
            "fornecedores": len(linhas),
            "propostas_recebidas": sum(1 for x in linhas if x["proposta"]["classe"] == "success"),
            "compatibilizados": sum(1 for x in linhas if x["compatibilizacao"]["estado"] == "APROVADO"),
            "aguardando_proposta": sum(1 for x in linhas if x["proposta"]["classe"] != "success"),
            "menor_valor": min(valores_cotados) if valores_cotados else None,
            "menor_valor_formatado": _moeda_br(min(valores_cotados)) if valores_cotados else "—",
            "menor_negociado": min(valores_negociados) if valores_negociados else None,
            "menor_negociado_formatado": _moeda_br(min(valores_negociados)) if valores_negociados else "—",
            "valor_aprovado": sum(valores_aprovados, Decimal("0")) if valores_aprovados else None,
            "valor_aprovado_formatado": _moeda_br(sum(valores_aprovados, Decimal("0"))) if valores_aprovados else "—",
            "valor_pedidos": sum(valores_pedidos, Decimal("0")) if valores_pedidos else None,
            "valor_pedidos_formatado": _moeda_br(sum(valores_pedidos, Decimal("0"))) if valores_pedidos else "—",
            "ultima_atualizacao": ultima_atualizacao_geral,
        }
        item.acompanhamento_busca = " ".join(
            [
                *(x["fornecedor_nome"] for x in linhas),
                *(x["processo_numero"] for x in linhas),
                *(x["status_atual"]["label"] for x in linhas),
                *atividades_nomes,
            ]
        ).casefold()


def montar_painel_cronograma_suprimentos(
    *,
    obra_id=None,
    categoria: str = "",
    etapa: str = "",
    situacao: str = "",
    busca: str = "",
):
    etapa = etapa or situacao
    importacao = (
        ImportacaoCronogramaSuprimentos.objects
        .filter(ativa=True, status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA)
        .select_related("executado_por")
        .first()
    )

    vazio = {
        "importacao_ativa": None,
        "obras": [],
        "cronograma_obra": None,
        "categorias": [],
        "categorias_filtro": [],
        "etapas_filtro": ETAPAS_FILTRO,
        "resumo": {
            "total": 0,
            "concluidos": 0,
            "em_andamento": 0,
            "nao_iniciados": 0,
            "atrasados": 0,
            "filtrados": 0,
            "percentual_medio": 0,
        },
        "filtros": {"categoria": categoria, "etapa": etapa, "busca": busca},
    }
    if not importacao:
        return vazio

    obras = list(
        importacao.obras_importadas.select_related("obra").order_by("ordem_aba", "nome_aba")
    )

    selecionado = None
    if obra_id:
        selecionado = next((x for x in obras if str(x.obra_id) == str(obra_id)), None)
    if selecionado is None and obras:
        selecionado = obras[0]

    grupos = []
    categorias_filtro = []
    resumo = vazio["resumo"].copy()

    if selecionado:
        hoje = timezone.localdate()
        todos_itens = [
            _decorar_item(item, hoje)
            for item in selecionado.itens.all().order_by("ordem", "id")
        ]

        # Consulta Compras uma única vez e anexa a visão comercial a cada item.
        _anexar_acompanhamento_compras(todos_itens)

        categorias_filtro = sorted(
            {x.categoria for x in todos_itens if x.categoria}, key=str.casefold
        )

        resumo["total"] = len(todos_itens)
        resumo["concluidos"] = sum(
            1 for x in todos_itens if x.etapa_atual == ItemCronogramaSuprimento.Etapa.CONCLUIDO
        )
        resumo["nao_iniciados"] = sum(1 for x in todos_itens if x.percentual_andamento == 0)
        resumo["em_andamento"] = sum(1 for x in todos_itens if 0 < x.percentual_andamento < 100)
        resumo["atrasados"] = sum(1 for x in todos_itens if x.atrasado_calculado)
        if todos_itens:
            resumo["percentual_medio"] = round(
                sum(x.percentual_andamento for x in todos_itens) / len(todos_itens)
            )

        itens = todos_itens
        if categoria:
            itens = [x for x in itens if x.categoria == categoria]
        if etapa:
            itens = _filtrar_por_etapa(itens, etapa)
        if busca:
            termo = busca.casefold()
            itens = [
                x for x in itens
                if termo in (x.item or "").casefold()
                or termo in (x.local or "").casefold()
                or termo in (x.contratada_responsavel or "").casefold()
                or termo in getattr(x, "acompanhamento_busca", "")
            ]

        resumo["filtrados"] = len(itens)

        mapa = {}
        for item in itens:
            nome_categoria = item.categoria or "SEM CATEGORIA"
            mapa.setdefault(nome_categoria, []).append(item)

        grupos = [
            {"nome": nome, "itens": itens_categoria}
            for nome, itens_categoria in mapa.items()
        ]

    return {
        "importacao_ativa": importacao,
        "obras": obras,
        "cronograma_obra": selecionado,
        "categorias": grupos,
        "categorias_filtro": categorias_filtro,
        "etapas_filtro": ETAPAS_FILTRO,
        "resumo": resumo,
        "filtros": {"categoria": categoria, "etapa": etapa, "busca": busca},
    }
