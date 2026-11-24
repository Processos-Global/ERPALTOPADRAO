from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import F, Prefetch
from django.utils import timezone

from compras.services.comercial import frete_das_adjudicacoes
from compras.services.valores import calcular_total_proposta
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


def _moeda_br(valor, *, casas=2):
    if valor is None:
        return "—"
    texto = f"{_decimal(valor):,.{casas}f}"
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
    return calcular_total_proposta(
        subtotal=sum((item.valor_total_cotado for item in itens), Decimal("0")),
        desconto=cotacao.desconto_proposta,
        frete=cotacao.frete,
    )


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
        and negociacao.prazo_entrega_dias_negociado
        != item.cotacao.prazo_entrega_dias
    ):
        return True

    pagamento_negociado = (
        negociacao.condicao_pagamento_negociada or ""
    ).strip()

    pagamento_original = (
        item.cotacao.condicao_pagamento or ""
    ).strip()

    if pagamento_negociado and pagamento_negociado != pagamento_original:
        return True

    return False


def _valor_negociado(cotacao):
    itens = list(cotacao.itens.all())

    if not itens:
        return None, None

    negociacoes_reais = []

    for item in itens:
        negociacao = getattr(item, "negociacao", None)

        if _negociacao_tem_alteracao(item, negociacao):
            negociacoes_reais.append((item, negociacao))

    # Se nenhuma condição comercial foi efetivamente alterada, não existe
    # "valor negociado" a exibir. O preço permanece apenas como valor cotado.
    if not negociacoes_reais:
        return None, None

    total = Decimal("0")

    for item in itens:
        negociacao = getattr(item, "negociacao", None)

        negociacao_real = _negociacao_tem_alteracao(
            item,
            negociacao,
        )

        tem_preco_negociado = bool(
            negociacao_real
            and negociacao.valor_unitario_negociado is not None
        )

        unitario = (
            negociacao.valor_unitario_negociado
            if tem_preco_negociado
            else item.valor_unitario_cotado
        )

        desconto = (
            Decimal("0")
            if tem_preco_negociado
            else _decimal(item.desconto_cotado)
        )

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
        frete_mais_recente = max(
            fretes_informados,
            key=lambda n: (n.atualizado_em, n.id),
        )
        frete = frete_mais_recente.frete_negociado
    else:
        frete = cotacao.frete

    return calcular_total_proposta(subtotal=total, desconto=cotacao.desconto_proposta, frete=frete), frete


def _status_compatibilizacao(cotacao):
    itens = list(cotacao.itens.all())
    item_cronograma = getattr(cotacao.processo, "item_cronograma", None)
    if item_cronograma is not None and not item_cronograma.exige_compatibilizacao:
        return {"label": "Não aplicável", "classe": "muted", "estado": "NAO_APLICAVEL"}

    if itens and not cotacao.enviada_compatibilizacao_em:
        return {
            "label": "Não enviada",
            "classe": "muted",
            "estado": "NAO_ENVIADA",
        }

    if not itens:
        return {
            "label": "—",
            "classe": "muted",
            "estado": "SEM_PROPOSTA",
        }

    resultados = []
    pendentes = 0

    for item in itens:
        ultimo = _ultimo_resultado_compat(item)

        if ultimo is None:
            pendentes += 1
        else:
            resultados.append(ultimo.resultado)

    aprovados = {
        "APROVADO",
        "APROVADO_COM_RESSALVA",
    }

    # Nenhum item desta proposta foi analisado ainda.
    if not resultados:
        return {
            "label": "Pendente",
            "classe": "muted",
            "estado": "PENDENTE",
        }

    # Já existem análises, mas ainda há itens sem decisão técnica.
    if pendentes > 0:
        return {
            "label": "Em análise",
            "classe": "warning",
            "estado": "PARCIAL",
        }

    # Todos os itens foram analisados e todos foram tecnicamente reprovados.
    if all(resultado == "REPROVADO" for resultado in resultados):
        return {
            "label": "Reprovado técnico",
            "classe": "danger",
            "estado": "REPROVADO",
        }

    # Todos os itens foram analisados e existe pelo menos um item tecnicamente
    # aprovado. Os demais podem ter sido reprovados sem deixar a proposta
    # eternamente como "Em análise".
    if any(resultado in aprovados for resultado in resultados):
        return {
            "label": "Compatibilizado",
            "classe": "success",
            "estado": "APROVADO",
        }

    # Fallback de segurança para eventual novo status técnico futuro.
    return {
        "label": "Compatibilizado",
        "classe": "success",
        "estado": "APROVADO",
    }


def _status_negociacao(cotacao, compat):
    itens = list(cotacao.itens.all())

    if not itens or compat["estado"] in {"SEM_PROPOSTA", "NAO_ENVIADA", "REPROVADO", "PENDENTE"}:
        return {
            "label": "—",
            "classe": "muted",
            "estado": "NAO_APLICAVEL",
        }

    if not cotacao.enviada_negociacao_em:
        return {"label": "Pendente", "classe": "warning", "estado": "PENDENTE"}

    # Se a proposta já foi enviada ao gestor, a etapa comercial de negociação
    # já foi concluída para este fornecedor. Os campos de negociação registram
    # alterações comerciais, mas uma negociação também pode ser concluída sem
    # mudança de preço/prazo/frete. Portanto, enviada_aprovacao_em prevalece
    # sobre a leitura dos campos alterados abaixo.
    if cotacao.enviada_aprovacao_em:
        return {
            "label": "Negociado",
            "classe": "success",
            "estado": "CONCLUIDO",
        }

    elegiveis = []
    if compat["estado"] == "NAO_APLICAVEL":
        elegiveis = itens
    else:
        for item in itens:
            ultimo = _ultimo_resultado_compat(item)
            if ultimo and ultimo.resultado in {"APROVADO", "APROVADO_COM_RESSALVA"}:
                elegiveis.append(item)

    if not elegiveis:
        return {
            "label": "—",
            "classe": "muted",
            "estado": "NAO_APLICAVEL",
        }

    negociados = sum(
        1
        for item in elegiveis
        if _negociacao_tem_alteracao(
            item,
            getattr(item, "negociacao", None),
        )
    )

    if negociados == len(elegiveis):
        return {
            "label": "Negociado",
            "classe": "success",
            "estado": "CONCLUIDO",
        }

    if negociados:
        return {
            "label": "Em negociação",
            "classe": "warning",
            "estado": "PARCIAL",
        }

    return {
        "label": "Pendente",
        "classe": "warning",
        "estado": "PENDENTE",
    }


def _dados_pedido(pedido):
    from compras.services.sla import indicador_pedido

    itens = []
    for item in pedido.itens.all():
        itens.append({
            "id": item.pk,
            "descricao": item.descricao,
            "unidade": item.unidade,
            "quantidade": item.quantidade,
            "quantidade_formatada": _quantidade_br(item.quantidade),
            "quantidade_recebida": item.quantidade_recebida,
            "quantidade_recebida_formatada": _quantidade_br(item.quantidade_recebida),
            "quantidade_pendente": item.saldo_receber,
            "quantidade_pendente_formatada": _quantidade_br(item.saldo_receber),
            "valor_unitario_formatado": _moeda_br(item.valor_unitario, casas=4),
            "desconto_formatado": _moeda_br(item.desconto),
            "valor_total": item.valor_total,
            "valor_total_formatado": _moeda_br(item.valor_total),
            "recebimentos": [
                {"quantidade": _quantidade_br(linha.quantidade), "registro": linha.recebimento}
                for linha in item.recebimentos.all()
            ],
        })

    return {
        "numero": pedido.numero,
        "quantidade_itens": len(itens),
        "itens": itens,
        "previsao_entrega": pedido.previsao_entrega_atual or pedido.previsao_entrega_original,
        "pedido": pedido,
        "prazo": indicador_pedido(pedido),
        "subtotal": _moeda_br(pedido.subtotal),
        "descontos": _moeda_br(pedido.descontos),
        "frete": _moeda_br(pedido.frete),
        "total": _moeda_br(pedido.valor_total),
    }


def _dados_pedidos_fornecedor(pedidos, *, detalhar):
    ativos = [pedido for pedido in pedidos if pedido.status != pedido.Status.CANCELADO]
    valor_pedido = sum((pedido.valor_total for pedido in ativos), Decimal("0")) if ativos else None
    detalhes = [_dados_pedido(pedido) for pedido in pedidos] if detalhar else []
    return {
        "valor_pedido": valor_pedido,
        "valor_pedido_formatado": _moeda_br(valor_pedido),
        "pedido_numeros": ", ".join(p.numero for p in ativos) or "—",
        "pedidos_detalhes": detalhes,
        "quantidade_itens_pedidos": sum(detalhe["quantidade_itens"] for detalhe in detalhes),
    }


def _dados_proposta(cotacao, itens, frete_negociado):
    return {
        "cotacao": cotacao,
        "frete_cotado": _moeda_br(cotacao.frete),
        "frete_negociado": _moeda_br(frete_negociado),
        "desconto_proposta": _moeda_br(cotacao.desconto_proposta),
        "itens": [{
            "item": item,
            "quantidade": _quantidade_br(item.quantidade),
            "unitario_cotado": _moeda_br(item.valor_unitario_cotado, casas=4),
            "desconto_cotado": _moeda_br(item.desconto_cotado),
            "total_cotado": _moeda_br(item.valor_total_cotado),
            "negociacao": getattr(item, "negociacao", None),
            "compatibilizacao": _ultimo_resultado_compat(item),
        } for item in itens],
    }


def _montar_linha_fornecedor(cotacao, processo, solicitacao, pedidos, *, detalhar):
    itens = list(cotacao.itens.all())
    proposta_recebida = bool(itens)

    compat = _status_compatibilizacao(cotacao)
    negociacao = _status_negociacao(cotacao, compat)

    adjudicacoes = [
        a
        for a in cotacao.adjudicacoes.all()
        if not a.cancelada
    ]

    pedidos_ativos = [
        pedido
        for pedido in pedidos
        if pedido.status != "CANCELADO"
    ]

    # A compatibilização técnica e a aprovação do gestor são etapas distintas.
    # Se o processo foi reprovado pelo gestor, uma proposta tecnicamente aceita
    # não pode aparecer como "Aprovado" apenas porque existe adjudicação residual.
    if (
        processo.status == "REPROVADO"
        and compat["estado"] == "APROVADO"
    ):
        aprovacao = {
            "label": "Reprovado pelo gestor",
            "classe": "danger",
            "estado": "REPROVADO_GESTOR",
        }

    elif adjudicacoes:
        aprovacao = {
            "label": "Aprovado",
            "classe": "success",
            "estado": "APROVADO",
        }

    elif (
        processo.status
        in {
            "APROVADO",
            "EM_CONTRATACAO",
            "CONTRATADO",
        }
        and proposta_recebida
    ):
        # O processo já teve decisão do gestor e este fornecedor não possui
        # adjudicação ativa. Portanto ele não está mais aguardando aprovação:
        # foi uma proposta considerada, mas não selecionada.
        aprovacao = {
            "label": "Não selecionado",
            "classe": "muted",
            "estado": "NAO_SELECIONADO",
        }

    elif (
        cotacao.enviada_aprovacao_em
        and compat["estado"] in {"APROVADO", "NAO_APLICAVEL"}
    ):
        aprovacao = {
            "label": "Aguardando gestor",
            "classe": "warning",
            "estado": "AGUARDANDO",
        }

    else:
        aprovacao = {
            "label": "—",
            "classe": "muted",
            "estado": "NAO_APLICAVEL",
        }

    valor_aprovado = frete_aprovado = None
    if aprovacao["estado"] == "APROVADO":
        frete_aprovado = frete_das_adjudicacoes(adjudicacoes)
        valor_aprovado = calcular_total_proposta(
            subtotal=sum((a.valor_total for a in adjudicacoes), Decimal("0")),
            desconto=cotacao.desconto_proposta,
            frete=frete_aprovado,
        )

    # O status final do processo precisa prevalecer sobre adjudicações/pedidos
    # residuais quando o gestor reprovou a compra. Mantemos a reprovação técnica
    # específica para fornecedores que nem chegaram elegíveis à aprovação.
    if compat["estado"] == "REPROVADO":
        status_atual = {
            "label": "Reprovado tecnicamente",
            "classe": "danger",
        }

    elif aprovacao["estado"] == "REPROVADO_GESTOR":
        status_atual = {
            "label": "Reprovado pelo gestor",
            "classe": "danger",
        }

    elif pedidos_ativos:
        pedido_atual = max(
            pedidos_ativos,
            key=lambda p: (
                p.atualizado_em,
                p.id,
            ),
        )

        status_atual = {
            "label": pedido_atual.get_status_display(),
            "classe": STATUS_PEDIDO_CLASSE.get(
                pedido_atual.status,
                "info",
            ),
        }

    elif adjudicacoes:
        status_atual = {
            "label": "Aprovado",
            "classe": "success",
        }

    elif aprovacao["estado"] == "AGUARDANDO":
        status_atual = {
            "label": "Em aprovação",
            "classe": "warning",
        }

    elif aprovacao["estado"] == "NAO_SELECIONADO":
        status_atual = {
            "label": "Não selecionado",
            "classe": "muted",
        }

    elif not proposta_recebida:
        status_atual = {
            "label": "Aguardando fornecedor",
            "classe": "muted",
        }

    elif compat["estado"] == "NAO_ENVIADA":
        status_atual = {"label": "Cotação recebida", "classe": "info"}

    elif compat["estado"] == "NAO_APLICAVEL" and not cotacao.enviada_negociacao_em:
        status_atual = {"label": "Cotação recebida", "classe": "info"}

    elif compat["estado"] in {
        "PENDENTE",
        "PARCIAL",
    }:
        status_atual = {
            "label": "Em compatibilização",
            "classe": "warning",
        }

    elif negociacao["estado"] != "CONCLUIDO":
        status_atual = {
            "label": "Em negociação",
            "classe": "info",
        }

    else:
        status_atual = {
            "label": "Negociado",
            "classe": "info",
        }

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

    datas_adjudicacao = [
        a.selecionado_em
        for a in adjudicacoes
    ]

    datas_pedidos = [
        p.atualizado_em
        for p in pedidos
    ]

    ultima_atualizacao = _mais_recente(
        cotacao.atualizado_em,
        *[item.atualizado_em for item in itens],
        *datas_compat,
        *datas_negociacao,
        *datas_adjudicacao,
        *datas_pedidos,
    )

    if solicitacao is not None:
        solicitacao_status = {
            "label": solicitacao.get_status_display(),
            "classe": (
                "success" if solicitacao.status == "RESPONDIDA"
                else "info" if solicitacao.status == "ENVIADA"
                else "warning" if solicitacao.status == "PENDENTE_ENVIO"
                else "muted"
            ),
            "codigo": solicitacao.status,
            "enviada_em": solicitacao.enviada_em,
            "meio_envio": solicitacao.get_meio_envio_display() if solicitacao.meio_envio else "",
        }
    else:
        solicitacao_status = {
            "label": "Proposta recebida",
            "classe": "success",
            "codigo": "RESPONDIDA",
            "enviada_em": None,
            "meio_envio": "",
        }

    valor_cotado = _valor_cotado(cotacao)
    valor_negociado, frete_negociado = _valor_negociado(cotacao)
    return {
        "cotacao_id": cotacao.id,
        "processo_id": processo.id,
        "processo_numero": processo.numero,
        "fornecedor_id": cotacao.fornecedor_id,
        "fornecedor_nome": cotacao.fornecedor.nome,
        "solicitacao": solicitacao_status,
        "proposta": {
            "label": (
                "Proposta recebida"
                if proposta_recebida
                else "Não recebida"
            ),
            "classe": (
                "success"
                if proposta_recebida
                else "muted"
            ),
        },
        "valor_cotado": valor_cotado,
        "valor_cotado_formatado": _moeda_br(valor_cotado),
        "valor_negociado": valor_negociado,
        "valor_negociado_formatado": _moeda_br(valor_negociado),
        "valor_aprovado": valor_aprovado,
        "valor_aprovado_formatado": _moeda_br(
            valor_aprovado
        ),
        "frete_aprovado": _moeda_br(frete_aprovado),
        "adjudicacoes": adjudicacoes if valor_aprovado is not None else [],
        "solicitacao_registro": solicitacao,
        "proposta_detalhe": _dados_proposta(cotacao, itens, frete_negociado) if detalhar and itens else None,
        "compatibilizacao": compat,
        "negociacao": negociacao,
        "aprovacao": aprovacao,
        **_dados_pedidos_fornecedor(pedidos, detalhar=detalhar),
        "status_atual": status_atual,
        "ultima_atualizacao": ultima_atualizacao,
    }


def _montar_linha_fornecedor_indicado(fornecedor, processo, solicitacao, pedidos, *, detalhar):
    """Fornecedor com solicitação ou pedido, sem proposta vinculada."""
    if solicitacao is None:
        solicitacao_status = {
            "label": "—",
            "classe": "muted",
            "codigo": "",
            "enviada_em": None,
            "meio_envio": "",
        }
    else:
        solicitacao_status = {
            "label": solicitacao.get_status_display(),
            "classe": (
                "success" if solicitacao.status == "RESPONDIDA"
                else "info" if solicitacao.status == "ENVIADA"
                else "warning" if solicitacao.status == "PENDENTE_ENVIO"
                else "muted"
            ),
            "codigo": solicitacao.status,
            "enviada_em": solicitacao.enviada_em,
            "meio_envio": solicitacao.get_meio_envio_display() if solicitacao.meio_envio else "",
        }

    status_atual = {
        "label": solicitacao_status["label"],
        "classe": solicitacao_status["classe"],
    }
    pedido_atual = max(
        pedidos,
        key=lambda pedido: (pedido.status != pedido.Status.CANCELADO, pedido.atualizado_em, pedido.pk),
        default=None,
    )
    if pedido_atual is not None:
        status_atual = {
            "label": pedido_atual.get_status_display(),
            "classe": STATUS_PEDIDO_CLASSE.get(pedido_atual.status, "info"),
        }

    return {
        "cotacao_id": None,
        "processo_id": processo.id,
        "processo_numero": processo.numero,
        "fornecedor_id": fornecedor.id,
        "fornecedor_nome": fornecedor.nome,
        "solicitacao": solicitacao_status,
        "solicitacao_registro": solicitacao,
        "proposta": {"label": "Não recebida", "classe": "muted"},
        "valor_cotado": None,
        "valor_cotado_formatado": "—",
        "valor_negociado": None,
        "valor_negociado_formatado": "—",
        "valor_aprovado": None,
        "valor_aprovado_formatado": "—",
        "compatibilizacao": {"label": "—", "classe": "muted", "estado": "NAO_APLICAVEL"},
        "negociacao": {"label": "—", "classe": "muted", "estado": "NAO_APLICAVEL"},
        "aprovacao": {"label": "—", "classe": "muted", "estado": "NAO_APLICAVEL"},
        **_dados_pedidos_fornecedor(pedidos, detalhar=detalhar),
        "status_atual": status_atual,
        "ultima_atualizacao": _mais_recente(
            processo.atualizado_em, solicitacao.atualizado_em if solicitacao else None,
            *(pedido.atualizado_em for pedido in pedidos),
        ),
        "origem_fornecedor": "INDICADO",
    }


def _anexar_acompanhamento_compras(itens, *, detalhar=True):
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
        PedidoCompraItem,
        ProcessoCompra,
        RecebimentoPedidoItem,
        SolicitacaoCotacaoFornecedor,
    )

    ids = [
        item.id
        for item in itens
    ]

    compat_qs = (
        CompatibilizacaoItem.objects
        .select_related("responsavel")
        .order_by("-data", "-id")
    )

    negociacao_qs = (
        NegociacaoItem.objects
        .select_related("atualizado_por")
    )

    item_cotado_qs = (
        CotacaoFornecedorItem.objects
        .select_related("necessidade")
        .prefetch_related(
            Prefetch(
                "compatibilizacoes",
                queryset=compat_qs,
            ),
            Prefetch(
                "negociacao",
                queryset=negociacao_qs,
            ),
        )
        .order_by("id")
    )

    adjudicacao_qs = (
        AdjudicacaoCompra.objects
        .filter(cancelada=False)
        .select_related("item_cotado__negociacao", "necessidade", "selecionado_por")
        .order_by("id")
    )

    cotacao_qs = (
        CotacaoFornecedor.objects
        .select_related("fornecedor", "criado_por")
        .prefetch_related(
            Prefetch(
                "itens",
                queryset=item_cotado_qs,
            ),
            Prefetch(
                "adjudicacoes",
                queryset=adjudicacao_qs,
            ),
        )
        .order_by("fornecedor__nome", "id")
    )

    pedido_qs = (
        PedidoCompra.objects
        .filter(obra_id=F("processo__obra_id"))
        .select_related("fornecedor")
        .order_by("criado_em", "id")
    )
    if detalhar:
        recebimentos_qs = RecebimentoPedidoItem.objects.select_related("recebimento__usuario").order_by(
            "-recebimento__criado_em", "-pk",
        )
        itens_pedido_qs = PedidoCompraItem.objects.prefetch_related(Prefetch("recebimentos", queryset=recebimentos_qs))
        pedido_qs = pedido_qs.select_related("responsavel", "recebido_por", "prazo_sla").prefetch_related(
            Prefetch("itens", queryset=itens_pedido_qs),
        )


    solicitacao_qs = (
        SolicitacaoCotacaoFornecedor.objects
        .select_related("fornecedor", "enviada_por")
        .order_by("fornecedor__nome", "id")
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
        .filter(obra_id=F("item_cronograma__cronograma_obra__obra_id"))
        .select_related("item_cronograma__cronograma_obra", "comprador")
        .prefetch_related(
            Prefetch(
                "cotacoes",
                queryset=cotacao_qs,
            ),
            Prefetch(
                "pedidos",
                queryset=pedido_qs,
            ),
            Prefetch(
                "necessidades",
                queryset=necessidade_qs,
            ),
            Prefetch(
                "solicitacoes_cotacao",
                queryset=solicitacao_qs,
            ),
            "vinculos_atividades__atividade",
        )
        .order_by("criado_em", "id")
    )

    por_item = {
        item_id: []
        for item_id in ids
    }

    for processo in processos:
        por_item.setdefault(
            processo.item_cronograma_id,
            [],
        ).append(processo)

    for item in itens:
        linhas = []

        processos_item = por_item.get(
            item.id,
            [],
        )

        # O Cronograma representa o SUPRIMENTO, e um mesmo suprimento pode ter
        # vários processos simultâneos. A visão principal, portanto, é
        # consolidada; nenhum processo mais novo "substitui" o anterior.
        status_finais = {
            ProcessoCompra.Status.CONTRATADO,
            ProcessoCompra.Status.REPROVADO,
            ProcessoCompra.Status.CANCELADO,
        }
        processos_ativos = [
            processo
            for processo in processos_item
            if processo.status not in status_finais
        ]
        processos_finalizados = [
            processo
            for processo in processos_item
            if processo.status in status_finais
        ]
        processos_contratados = [
            processo
            for processo in processos_item
            if processo.status == ProcessoCompra.Status.CONTRATADO
        ]

        item.acompanhamento_processos_ativos = processos_ativos
        item.acompanhamento_processos_finalizados = processos_finalizados
        item.acompanhamento_qtd_processos = len(processos_item)
        item.acompanhamento_qtd_processos_ativos = len(processos_ativos)
        item.acompanhamento_qtd_processos_finalizados = len(processos_finalizados)
        item.acompanhamento_qtd_processos_contratados = len(processos_contratados)

        processo_referencia = (
            processos_ativos[-1]
            if processos_ativos
            else (processos_item[-1] if processos_item else None)
        )

        mapa_status = {
            "RASCUNHO": ("RASCUNHO", "Rascunho", "muted"),
            "PEDIDO_ENVIADO": ("PEDIDO_ENVIADO", "Solicitação enviada", "info"),
            "SOLICITACAO_COTACAO": ("SOLICITACAO_COTACAO", "Aguardando fornecedor", "warning"),
            "AGUARDANDO_COTACAO": ("SOLICITACAO_COTACAO", "Aguardando fornecedor", "warning"),
            "EM_COTACAO": ("COTACAO", "Proposta recebida", "info"),
            "AGUARDANDO_COMPATIBILIZACAO": ("COMPATIBILIZACAO", "Compatibilização", "warning"),
            "EM_COMPATIBILIZACAO": ("COMPATIBILIZACAO", "Compatibilização", "warning"),
            "EM_NEGOCIACAO": ("NEGOCIACAO", "Negociação", "info"),
            "AGUARDANDO_APROVACAO": ("APROVACAO", "Aguardando aprovação", "warning"),
            "AJUSTE_SOLICITADO": ("AJUSTE", "Ajuste solicitado", "warning"),
            "APROVADO": ("APROVADO", "Aprovado", "success"),
            "EM_CONTRATACAO": ("CONTRATACAO", "Contratação", "info"),
            "CONTRATADO": ("CONTRATADO", "Contratado", "success"),
            "REPROVADO": ("REPROVADO", "Reprovado", "danger"),
            "CANCELADO": ("CANCELADO", "Cancelado", "danger"),
        }

        if not processos_item:
            item.status_compras_codigo = "AGUARDANDO_PEDIDO"
            item.status_compras_label = "Aguardando pedido"
            item.status_compras_classe = "muted"
        elif len(processos_ativos) > 1:
            item.status_compras_codigo = "MULTIPLOS_PROCESSOS"
            item.status_compras_label = f"{len(processos_ativos)} processos ativos"
            item.status_compras_classe = "info"
        elif len(processos_ativos) == 1:
            status = processos_ativos[0].status
            codigo, label, classe = mapa_status.get(
                status,
                (status, processos_ativos[0].get_status_display(), "muted"),
            )
            item.status_compras_codigo = codigo
            item.status_compras_label = label
            item.status_compras_classe = classe
        elif processos_contratados:
            item.status_compras_codigo = "CONTRATADO"
            item.status_compras_label = (
                "Contratado"
                if len(processos_contratados) == 1
                else f"{len(processos_contratados)} compras contratadas"
            )
            item.status_compras_classe = "success"
        else:
            status = processo_referencia.status
            codigo, label, classe = mapa_status.get(
                status,
                (status, processo_referencia.get_status_display(), "muted"),
            )
            item.status_compras_codigo = codigo
            item.status_compras_label = label
            item.status_compras_classe = classe

        # Fornecedores apresentados no resumo vêm de todos os processos do
        # suprimento, e não somente do último processo criado.
        nomes_fornecedores = []
        nomes_fornecedores_vistos = set()
        for processo in processos_item:
            for solicitacao in processo.solicitacoes_cotacao.all():
                nome = solicitacao.fornecedor.nome
                chave = nome.casefold()
                if chave in nomes_fornecedores_vistos:
                    continue
                nomes_fornecedores_vistos.add(chave)
                nomes_fornecedores.append(nome)

        item.fornecedor_pedido_nome = ", ".join(nomes_fornecedores)

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

        pedidos_pendentes = [
            p
            for p in pedidos_do_item
            if p.status != "ENTREGUE"
        ]

        previsoes_pendentes = [
            p.previsao_entrega_atual
            or p.previsao_entrega_original
            for p in pedidos_pendentes
            if (
                p.previsao_entrega_atual
                or p.previsao_entrega_original
            )
        ]

        previsoes_todas = [
            p.previsao_entrega_atual
            or p.previsao_entrega_original
            for p in pedidos_do_item
            if (
                p.previsao_entrega_atual
                or p.previsao_entrega_original
            )
        ]

        item.previsao_entrega_compra = (
            min(previsoes_pendentes)
            if previsoes_pendentes
            else (
                max(previsoes_todas)
                if previsoes_todas
                else None
            )
        )

        item.previsao_entrega_atrasada = bool(
            previsoes_pendentes
            and item.previsao_entrega_compra
            and item.previsao_entrega_compra
            < timezone.localdate()
        )

        item.previsao_entrega_dias_atraso = (
            (
                timezone.localdate()
                - item.previsao_entrega_compra
            ).days
            if item.previsao_entrega_atrasada
            else 0
        )

        item.previsao_entrega_qtd_pedidos = len(
            pedidos_do_item
        )

        for processo in processos_item:
            pedidos_por_fornecedor = defaultdict(list)
            for pedido in processo.pedidos.all():
                pedidos_por_fornecedor[pedido.fornecedor_id].append(pedido)
            solicitacoes_por_fornecedor = {
                solicitacao.fornecedor_id: solicitacao
                for solicitacao in processo.solicitacoes_cotacao.all()
            }
            vistos = set()
            for cotacao in processo.cotacoes.all():
                vistos.add(cotacao.fornecedor_id)
                linha = _montar_linha_fornecedor(
                    cotacao,
                    processo,
                    solicitacoes_por_fornecedor.get(cotacao.fornecedor_id),
                    pedidos_por_fornecedor[cotacao.fornecedor_id],
                    detalhar=detalhar,
                )
                linha["origem_fornecedor"] = "COTACAO"
                linhas.append(linha)

            # Mantém visíveis também os fornecedores que ainda não responderam,
            # mesmo quando outro fornecedor do mesmo processo já enviou proposta.
            for solicitacao in processo.solicitacoes_cotacao.all():
                if solicitacao.fornecedor_id in vistos:
                    continue
                vistos.add(solicitacao.fornecedor_id)
                linhas.append(
                    _montar_linha_fornecedor_indicado(
                        solicitacao.fornecedor,
                        processo,
                        solicitacao,
                        pedidos_por_fornecedor[solicitacao.fornecedor_id],
                        detalhar=detalhar,
                    )
                )
            for fornecedor_id, pedidos in pedidos_por_fornecedor.items():
                if fornecedor_id not in vistos:
                    linhas.append(_montar_linha_fornecedor_indicado(
                        pedidos[0].fornecedor, processo, None, pedidos, detalhar=detalhar,
                    ))

        linhas.sort(
            key=lambda x: (
                x["fornecedor_nome"].casefold(),
                x["processo_numero"],
            )
        )

        valores_cotados = [
            x["valor_cotado"]
            for x in linhas
            if x["valor_cotado"] is not None
        ]

        valores_negociados = [
            x["valor_negociado"]
            for x in linhas
            if x["valor_negociado"] is not None
        ]

        valores_aprovados = [
            x["valor_aprovado"]
            for x in linhas
            if x["valor_aprovado"] is not None
        ]

        valores_pedidos = [
            x["valor_pedido"]
            for x in linhas
            if x["valor_pedido"] is not None
        ]

        # Contexto do suprimento: atividades vinculadas ao(s) processo(s).
        # A quantidade de itens é mostrada por pedido de compra na planilha
        # de fornecedores, e não como quantidade de pedidos/necessidades.
        atividades_por_id = {}

        for processo in processos_item:
            necessidades = list(
                processo.necessidades.all()
            )

            for vinculo in processo.vinculos_atividades.all():
                atividade = vinculo.atividade

                atividades_por_id[
                    atividade.id
                ] = atividade

            # Também considera a atividade de origem do item, quando houver,
            # para cobrir processos antigos ou itens vinculados individualmente.
            for necessidade in necessidades:
                atividade = necessidade.atividade_origem

                if atividade is not None:
                    atividades_por_id[
                        atividade.id
                    ] = atividade

        atividades = sorted(
            atividades_por_id.values(),
            key=lambda atividade: (
                atividade.nome_tarefa or ""
            ).casefold(),
        )

        atividades_nomes = [
            (
                atividade.nome_tarefa
                or str(atividade)
            ).strip()
            for atividade in atividades
        ]

        item.acompanhamento_fornecedores = linhas
        item.acompanhamento_fornecedores_resumo = linhas[:3]
        item.acompanhamento_fornecedores_extras = max(len(linhas) - 3, 0)
        item.acompanhamento_processos = processos_item
        item.acompanhamento_tem_compras = bool(
            processos_item
        )
        item.acompanhamento_atividades = atividades
        item.acompanhamento_atividades_nomes = (
            atividades_nomes
        )
        item.acompanhamento_atividades_texto = (
            " • ".join(atividades_nomes)
            or "—"
        )

        ultimas_atualizacoes = [
            x["ultima_atualizacao"]
            for x in linhas
            if x.get("ultima_atualizacao") is not None
        ]

        ultima_atualizacao_geral = (
            max(ultimas_atualizacoes)
            if ultimas_atualizacoes
            else None
        )

        item.acompanhamento_resumo = {
            "processos": len(processos_item),
            "processos_ativos": len(processos_ativos),
            "processos_finalizados": len(processos_finalizados),
            "processos_contratados": len(processos_contratados),
            "fornecedores": len(linhas),

            "solicitacoes_enviadas": sum(
                1
                for x in linhas
                if x.get("solicitacao", {}).get("codigo") in {"ENVIADA", "RESPONDIDA"}
            ),

            "pendentes_envio": sum(
                1
                for x in linhas
                if x.get("solicitacao", {}).get("codigo") == "PENDENTE_ENVIO"
            ),

            "propostas_recebidas": sum(
                1
                for x in linhas
                if x["proposta"]["classe"] == "success"
            ),

            "compatibilizados": sum(
                1
                for x in linhas
                if x["compatibilizacao"]["estado"] == "APROVADO"
            ),

            "aguardando_proposta": sum(
                1
                for x in linhas
                if x["proposta"]["classe"] != "success"
            ),

            "menor_valor": (
                min(valores_cotados)
                if valores_cotados
                else None
            ),

            "menor_valor_formatado": (
                _moeda_br(
                    min(valores_cotados)
                )
                if valores_cotados
                else "—"
            ),

            "menor_negociado": (
                min(valores_negociados)
                if valores_negociados
                else None
            ),

            "menor_negociado_formatado": (
                _moeda_br(
                    min(valores_negociados)
                )
                if valores_negociados
                else "—"
            ),

            "valor_aprovado": (
                sum(
                    valores_aprovados,
                    Decimal("0"),
                )
                if valores_aprovados
                else None
            ),

            "valor_aprovado_formatado": (
                _moeda_br(
                    sum(
                        valores_aprovados,
                        Decimal("0"),
                    )
                )
                if valores_aprovados
                else "—"
            ),

            "valor_pedidos": (
                sum(
                    valores_pedidos,
                    Decimal("0"),
                )
                if valores_pedidos
                else None
            ),

            "valor_pedidos_formatado": (
                _moeda_br(
                    sum(
                        valores_pedidos,
                        Decimal("0"),
                    )
                )
                if valores_pedidos
                else "—"
            ),

            "ultima_atualizacao": (
                ultima_atualizacao_geral
            ),
        }

        item.acompanhamento_busca = " ".join(
            [
                *(
                    x["fornecedor_nome"]
                    for x in linhas
                ),
                *(
                    x["processo_numero"]
                    for x in linhas
                ),
                *(
                    x["status_atual"]["label"]
                    for x in linhas
                ),
                *(
                    x.get("solicitacao", {}).get("label", "")
                    for x in linhas
                ),
                *atividades_nomes,
            ]
        ).casefold()


def carregar_detalhe_comercial(item):
    _anexar_acompanhamento_compras([item])


def _anexar_previsoes_entrega(itens, hoje):
    from compras.models import PedidoCompra
    from django.db.models import Count, Max, Min, Q
    from django.db.models.functions import Coalesce

    previsao = Coalesce("previsao_entrega_atual", "previsao_entrega_original")
    pedidos = (
        PedidoCompra.objects.filter(
            processo__item_cronograma_id__in=[item.pk for item in itens],
            obra_id=F("processo__obra_id"),
            processo__obra_id=F("processo__item_cronograma__cronograma_obra__obra_id"),
        )
        .exclude(status=PedidoCompra.Status.CANCELADO)
        .order_by()
        .values("processo__item_cronograma_id")
        .annotate(
            proxima=Min(previsao, filter=~Q(status=PedidoCompra.Status.ENTREGUE)),
            ultima=Max(previsao),
            total=Count("pk"),
        )
    )
    previsoes = {pedido["processo__item_cronograma_id"]: pedido for pedido in pedidos}
    for item in itens:
        dados = previsoes.get(item.pk)
        if not dados:
            continue
        proxima = dados["proxima"]
        item.previsao_entrega_compra = proxima or dados["ultima"]
        item.previsao_entrega_atrasada = bool(proxima and proxima < hoje)
        item.previsao_entrega_dias_atraso = (hoje - proxima).days if item.previsao_entrega_atrasada else 0
        item.previsao_entrega_qtd_pedidos = dados["total"]


def _resumir_itens(itens):
    total = len(itens)
    return {
        "total": total,
        "concluidos": sum(item.etapa_atual == ItemCronogramaSuprimento.Etapa.CONCLUIDO for item in itens),
        "nao_iniciados": sum(item.percentual_andamento == 0 for item in itens),
        "em_andamento": sum(0 < item.percentual_andamento < 100 for item in itens),
        "atrasados": sum(item.atrasado_calculado for item in itens),
        "percentual_medio": round(sum(item.percentual_andamento for item in itens) / total) if total else 0,
    }


def montar_painel_cronograma_suprimentos(
    *,
    obra_id=None,
    categoria: str = "",
    etapa: str = "",
    situacao: str = "",
    busca: str = "",
    suprimento: str = "",
    incluir_acompanhamento=True,
):
    etapa = etapa or situacao

    importacao = (
        ImportacaoCronogramaSuprimentos.objects
        .filter(
            ativa=True,
            status=ImportacaoCronogramaSuprimentos.Status.CONCLUIDA,
        )
        .select_related("executado_por")
        .first()
    )

    vazio = {
        "importacao_ativa": None,
        "obras": [],
        "cronograma_obra": None,
        "categorias": [],
        "categorias_filtro": [],
        "suprimentos_filtro": [],
        "etapas_filtro": ETAPAS_FILTRO,
        "resumo": {**_resumir_itens([]), "filtrados": 0},
        "resumo_filtrado": _resumir_itens([]),
        "filtros": {
            "categoria": categoria,
            "etapa": etapa,
            "busca": busca,
            "suprimento": suprimento,
        },
    }

    if not importacao:
        return vazio

    obras = list(
        importacao.obras_importadas
        .select_related("obra")
        .order_by(
            "ordem_aba",
            "nome_aba",
        )
    )

    selecionado = None
    if obra_id:
        selecionado = next((x for x in obras if str(x.obra_id) == str(obra_id)), None)
    if selecionado is None and obras and not suprimento:
        selecionado = obras[0]

    grupos = []
    categorias_filtro = []
    # Uma consulta para todas as abas da importação, preservando as opções
    # globais mesmo quando uma obra ou um suprimento estiver selecionado.
    suprimentos_filtro = sorted({
        nome
        for nome in ItemCronogramaSuprimento.objects.filter(
            cronograma_obra_id__in=[cron.id for cron in obras]
        ).order_by().values_list("item", flat=True)
        if nome
    }, key=str.casefold)
    resumo = vazio["resumo"].copy()
    resumo_filtrado = vazio["resumo_filtrado"]
    hoje = timezone.localdate()

    cronogramas_origem = obras if suprimento else ([selecionado] if selecionado else [])
    todos_itens = []
    if cronogramas_origem:
        qs = ItemCronogramaSuprimento.objects.filter(
            cronograma_obra_id__in=[cron.id for cron in cronogramas_origem]
        ).order_by("ordem", "id")
        if suprimento:
            qs = qs.filter(item=suprimento)
        itens_por_cronograma = {cron.id: [] for cron in cronogramas_origem}
        for item in qs:
            itens_por_cronograma[item.cronograma_obra_id].append(item)

    for cron in cronogramas_origem:
        for item in itens_por_cronograma[cron.id]:
            item = _decorar_item(item, hoje)
            item.obra_exibicao = cron.nome_aba
            todos_itens.append(item)

    if todos_itens:
        categorias_filtro = sorted({x.categoria for x in todos_itens if x.categoria}, key=str.casefold)
        resumo.update(_resumir_itens(todos_itens))
        itens = todos_itens
        if categoria:
            itens = [x for x in itens if x.categoria == categoria]
        if etapa:
            itens = _filtrar_por_etapa(itens, etapa)
        if incluir_acompanhamento:
            _anexar_acompanhamento_compras(itens)
        if busca:
            termo = busca.casefold()
            locais = {
                item.pk for item in itens
                if any(
                    termo in (valor or "").casefold()
                    for valor in (item.item, item.local, item.contratada_responsavel, item.obra_exibicao)
                )
            }
            if not incluir_acompanhamento:
                # Os estados comerciais pesquisáveis são calculados pelas regras de Compras.
                _anexar_acompanhamento_compras([item for item in itens if item.pk not in locais], detalhar=False)
            itens = [
                item for item in itens
                if item.pk in locais or termo in getattr(item, "acompanhamento_busca", "")
            ]
        if not incluir_acompanhamento:
            _anexar_previsoes_entrega(itens, hoje)
        resumo["filtrados"] = len(itens)
        resumo_filtrado = resumo if itens is todos_itens else _resumir_itens(itens)
        mapa = {}
        for item in itens:
            nome_categoria = item.categoria or "SEM CATEGORIA"
            mapa.setdefault(nome_categoria, []).append(item)
        grupos = [{"nome": nome, "itens": itens_categoria} for nome, itens_categoria in mapa.items()]

    return {
        "importacao_ativa": importacao,
        "obras": obras,
        "cronograma_obra": selecionado,
        "categorias": grupos,
        "categorias_filtro": categorias_filtro,
        "suprimentos_filtro": suprimentos_filtro,
        "etapas_filtro": ETAPAS_FILTRO,
        "resumo": resumo,
        "resumo_filtrado": resumo_filtrado,
        "filtros": {
            "categoria": categoria,
            "etapa": etapa,
            "busca": busca,
            "suprimento": suprimento,
        },
    }
