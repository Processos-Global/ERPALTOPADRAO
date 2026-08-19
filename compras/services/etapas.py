from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compras.models import (
    AprovacaoCompra,
    AdjudicacaoCompra,
    CotacaoFornecedorItem,
    NegociacaoItem,
    ProcessoCompra,
)

from .alcadas import resolver_alcada_aprovacao
from .auditoria import registrar_evento
from .comercial import (
    calcular_desconto_adjudicacao,
    item_tecnicamente_aprovado,
    queryset_itens_tecnicamente_aprovados,
    total_aprovacao_processo,
)
from .integracao_planejamento import sincronizar_data_real


@transaction.atomic
def concluir_cotacao(processo, usuario):
    """Inicia a análise técnica sem fechar o mapa de cotação."""
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual != p.Etapa.COTACAO:
        raise ValidationError("A análise técnica já foi iniciada para este mapa.")
    if p.status in {p.Status.CANCELADO, p.Status.REPROVADO, p.Status.CONTRATADO}:
        raise ValidationError("Este processo não pode mais ser alterado.")

    necessidades = p.necessidades.filter(situacao="ATIVA")
    if not necessidades.exists():
        raise ValidationError("Inclua ao menos uma necessidade antes de iniciar a análise técnica.")
    if not p.cotacoes.filter(itens__isnull=False).exists():
        raise ValidationError("Inclua ao menos uma proposta com item cotado.")

    p.data_cotacao_concluida = timezone.now()
    p.etapa_atual = p.Etapa.COMPATIBILIZACAO
    p.status = p.Status.EM_COMPATIBILIZACAO
    p.save(update_fields=["data_cotacao_concluida", "etapa_atual", "status", "atualizado_em"])
    sincronizar_data_real(p, "COTACAO", usuario)
    registrar_evento(
        p,
        "ANALISE_TECNICA_INICIADA",
        usuario,
        "Análise técnica iniciada. O mapa comercial permanece aberto para novas propostas.",
    )
    return p


@transaction.atomic
def concluir_compatibilizacao(processo, usuario):
    """Libera negociação após a primeira oferta tecnicamente válida, sem fechar o mapa."""
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual not in {p.Etapa.COMPATIBILIZACAO, p.Etapa.NEGOCIACAO}:
        raise ValidationError("O mapa não está aberto para análise técnica/negociação.")
    if p.status in {p.Status.CANCELADO, p.Status.REPROVADO, p.Status.CONTRATADO}:
        raise ValidationError("Este processo não pode mais ser alterado.")

    itens_aprovados = queryset_itens_tecnicamente_aprovados(
        CotacaoFornecedorItem.objects.filter(cotacao__processo=p, necessidade__situacao="ATIVA")
    )
    if not itens_aprovados.exists():
        raise ValidationError("Ainda não existe oferta tecnicamente aprovada para liberar a negociação.")

    if p.etapa_atual == p.Etapa.NEGOCIACAO:
        return p

    p.data_compatibilizacao_concluida = timezone.now()
    p.etapa_atual = p.Etapa.NEGOCIACAO
    p.status = p.Status.EM_NEGOCIACAO
    p.save(update_fields=["data_compatibilizacao_concluida", "etapa_atual", "status", "atualizado_em"])
    sincronizar_data_real(p, "COMPATIBILIZACAO", usuario)
    registrar_evento(
        p,
        "NEGOCIACAO_LIBERADA",
        usuario,
        "Primeira oferta tecnicamente válida liberada para negociação. O mapa permanece aberto.",
    )
    return p


@transaction.atomic
def concluir_negociacao(processo, usuario):
    """
    Fecha o mapa comercial e envia TODAS as alternativas tecnicamente aprovadas ao gestor.

    O comprador não escolhe fornecedor nesta etapa. Cada necessidade precisa ter
    ao menos uma alternativa técnica válida; a escolha final acontece na aprovação.
    """
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual not in {p.Etapa.COMPATIBILIZACAO, p.Etapa.NEGOCIACAO}:
        raise ValidationError("O mapa comercial não está aberto para conclusão.")
    if p.status in {p.Status.CANCELADO, p.Status.REPROVADO, p.Status.CONTRATADO}:
        raise ValidationError("Este processo não pode mais ser alterado.")

    pendencias = []
    for necessidade in p.necessidades.filter(situacao="ATIVA"):
        possui_opcao = queryset_itens_tecnicamente_aprovados(
            CotacaoFornecedorItem.objects.filter(cotacao__processo=p, necessidade=necessidade)
        ).exists()
        if not possui_opcao:
            pendencias.append(necessidade.descricao)

    if pendencias:
        raise ValidationError(
            "Não é possível enviar para aprovação. Não existe proposta tecnicamente aprovada para: "
            + ", ".join(pendencias)
            + "."
        )

    # Qualquer adjudicação antiga/legada não representa mais escolha do comprador.
    # Ela é cancelada antes do envio ao gestor; a adjudicação válida será criada
    # somente a partir da decisão do gestor.
    agora = timezone.now()
    p.adjudicacoes.filter(cancelada=False).update(
        cancelada=True,
        cancelada_por=usuario,
        cancelada_em=agora,
        motivo_cancelamento="Seleção comercial antiga cancelada: a escolha final passa a ser do gestor.",
    )

    p.data_negociacao_concluida = agora
    p.etapa_atual = p.Etapa.APROVACAO
    p.status = p.Status.AGUARDANDO_APROVACAO
    p.save(update_fields=["data_negociacao_concluida", "etapa_atual", "status", "atualizado_em"])
    sincronizar_data_real(p, "NEGOCIACAO", usuario)
    registrar_evento(
        p,
        "MAPA_COMERCIAL_FECHADO",
        usuario,
        "Mapa comercial fechado. Alternativas tecnicamente aprovadas enviadas ao gestor para escolha.",
    )
    return p


def _criar_adjudicacoes_da_aprovacao(*, processo, usuario, selecoes):
    """Converte a escolha do gestor em adjudicações internas."""
    selecoes = list(selecoes or [])
    if not selecoes:
        raise ValidationError("Selecione ao menos uma proposta para aprovar.")

    # Garante que a soma aprovada cubra exatamente cada necessidade ativa.
    totais = {}
    for selecao in selecoes:
        item = selecao["item_cotado"]
        quantidade = Decimal(str(selecao["quantidade"] or 0))
        if item.cotacao.processo_id != processo.pk:
            raise ValidationError("Uma das propostas selecionadas não pertence a este processo.")
        if not item_tecnicamente_aprovado(item):
            raise ValidationError(
                f"A proposta de {item.cotacao.fornecedor.nome} para {item.necessidade.descricao} não possui aprovação técnica válida."
            )
        if quantidade <= 0:
            continue
        if quantidade > item.quantidade:
            raise ValidationError(
                f"A quantidade aprovada para {item.cotacao.fornecedor.nome} excede a quantidade ofertada."
            )
        totais[item.necessidade_id] = totais.get(item.necessidade_id, Decimal("0")) + quantidade

    for necessidade in processo.necessidades.filter(situacao="ATIVA"):
        esperado = necessidade.quantidade_incluida or Decimal("0")
        total = totais.get(necessidade.pk, Decimal("0"))
        if total != esperado:
            raise ValidationError(
                f"{necessidade.descricao}: aprove exatamente {esperado} {necessidade.unidade}. Total selecionado: {total}."
            )

    agora = timezone.now()
    processo.adjudicacoes.filter(cancelada=False).update(
        cancelada=True,
        cancelada_por=usuario,
        cancelada_em=agora,
        motivo_cancelamento="Substituída pela decisão atual do gestor.",
    )

    criadas = []
    for selecao in selecoes:
        item = CotacaoFornecedorItem.objects.select_related(
            "cotacao__fornecedor", "cotacao__processo", "necessidade", "negociacao"
        ).get(pk=selecao["item_cotado"].pk)
        quantidade = Decimal(str(selecao["quantidade"] or 0))
        if quantidade <= 0:
            continue

        negociacao = getattr(item, "negociacao", None)
        valor = negociacao.valor_final_unitario if negociacao else item.valor_unitario_cotado
        prazo = (
            negociacao.prazo_entrega_dias_negociado
            if negociacao and negociacao.prazo_entrega_dias_negociado is not None
            else item.cotacao.prazo_entrega_dias
        )
        pagamento = (
            negociacao.condicao_pagamento_negociada
            if negociacao and (negociacao.condicao_pagamento_negociada or "").strip()
            else item.cotacao.condicao_pagamento
        )
        desconto = calcular_desconto_adjudicacao(item, quantidade, valor)

        adj = AdjudicacaoCompra.objects.create(
            processo=processo,
            necessidade=item.necessidade,
            cotacao=item.cotacao,
            item_cotado=item,
            quantidade=quantidade,
            valor_unitario_final=valor,
            desconto_final=desconto,
            prazo_entrega_dias_final=prazo,
            condicao_pagamento_final=pagamento,
            selecionado_por=usuario,
        )
        criadas.append(adj)
        registrar_evento(
            processo,
            "PROPOSTA_APROVADA_GESTOR",
            usuario,
            f"Gestor aprovou {quantidade} {item.necessidade.unidade} de {item.necessidade.descricao} com {item.cotacao.fornecedor.nome}.",
            {"adjudicacao_id": adj.pk, "item_cotado_id": item.pk},
        )
    return criadas


@transaction.atomic
def decidir_aprovacao(processo, usuario, decisao, observacao="", selecoes=None):
    """
    Registra a decisão do gestor.

    APROVADO: o gestor escolhe as propostas; o sistema cria adjudicações internas,
    gera pedidos automaticamente e finaliza o mapa.
    AJUSTE_SOLICITADO: retorna para Cotação.
    REPROVADO: encerra sem gerar pedido.
    """
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual != p.Etapa.APROVACAO:
        raise ValidationError("O processo não está aguardando aprovação.")
    if decisao not in AprovacaoCompra.Decisao.values:
        raise ValidationError("Decisão de aprovação inválida.")

    observacao = (observacao or "").strip()
    if decisao in {AprovacaoCompra.Decisao.AJUSTE_SOLICITADO, AprovacaoCompra.Decisao.REPROVADO} and not observacao:
        raise ValidationError("Informe o motivo da decisão.")

    ciclo = (p.aprovacoes.order_by("-ciclo").values_list("ciclo", flat=True).first() or 0) + 1

    if decisao == AprovacaoCompra.Decisao.AJUSTE_SOLICITADO:
        aprovacao = AprovacaoCompra.objects.create(
            processo=p, ciclo=ciclo, alcada=None, usuario=usuario, decisao=decisao, observacao=observacao
        )
        agora = timezone.now()
        AdjudicacaoCompra.objects.filter(processo=p, cancelada=False).update(
            cancelada=True,
            cancelada_por=usuario,
            cancelada_em=agora,
            motivo_cancelamento=f"Seleção cancelada automaticamente no ciclo {ciclo}: gestor solicitou ajuste.",
        )
        NegociacaoItem.objects.filter(item_cotado__cotacao__processo=p).delete()
        p.status = p.Status.AJUSTE_SOLICITADO
        p.etapa_atual = p.Etapa.COTACAO
        p.data_cotacao_concluida = None
        p.data_compatibilizacao_concluida = None
        p.data_negociacao_concluida = None
        p.save(update_fields=[
            "status", "etapa_atual", "data_cotacao_concluida",
            "data_compatibilizacao_concluida", "data_negociacao_concluida", "atualizado_em",
        ])
        registrar_evento(
            p, "AJUSTE_SOLICITADO_GESTOR", usuario,
            "Gestor solicitou ajuste. Processo retornou para Cotação.",
            {"ciclo": ciclo, "observacao": observacao},
        )
        return aprovacao

    if decisao == AprovacaoCompra.Decisao.REPROVADO:
        aprovacao = AprovacaoCompra.objects.create(
            processo=p, ciclo=ciclo, alcada=None, usuario=usuario, decisao=decisao, observacao=observacao
        )
        p.status = p.Status.REPROVADO
        p.etapa_atual = p.Etapa.APROVACAO
        p.save(update_fields=["status", "etapa_atual", "atualizado_em"])
        registrar_evento(p, "PROCESSO_REPROVADO", usuario, "Compra reprovada e processo encerrado.", {"ciclo": ciclo})
        return aprovacao

    _criar_adjudicacoes_da_aprovacao(processo=p, usuario=usuario, selecoes=selecoes)
    total = total_aprovacao_processo(p)
    alcada = resolver_alcada_aprovacao(p, usuario, total)
    aprovacao = AprovacaoCompra.objects.create(
        processo=p,
        ciclo=ciclo,
        alcada=alcada,
        usuario=usuario,
        decisao=decisao,
        observacao=observacao,
    )

    p.status = p.Status.APROVADO
    p.save(update_fields=["status", "atualizado_em"])
    registrar_evento(
        p,
        "APROVACAO",
        usuario,
        f"Propostas escolhidas e aprovadas pelo gestor no valor de R$ {total:,.2f}.",
        {"ciclo": ciclo, "alcada_id": getattr(alcada, "pk", None), "valor": str(total)},
    )

    from .pedidos import gerar_pedidos

    pedidos = gerar_pedidos(p, usuario)
    registrar_evento(
        p,
        "PEDIDOS_GERADOS_APROVACAO",
        usuario,
        f"{len(pedidos)} pedido(s) gerado(s) automaticamente. Mapa finalizado.",
    )
    return aprovacao
