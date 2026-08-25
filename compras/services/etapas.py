from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compras.models import (
    AprovacaoCompra, AdjudicacaoCompra, CotacaoFornecedor, CotacaoFornecedorItem,
    NegociacaoItem, ProcessoCompra,
)
from .alcadas import resolver_alcada_aprovacao
from .auditoria import registrar_evento
from .comercial import (
    calcular_desconto_adjudicacao, cotacao_elegivel_para_negociacao,
    item_tecnicamente_aprovado, processo_exige_compatibilizacao,
    queryset_itens_elegiveis_comercial, total_aprovacao_processo,
)
from .integracao_planejamento import sincronizar_data_real


def _processo_bloqueado(p):
    return p.status in {p.Status.CANCELADO, p.Status.REPROVADO, p.Status.CONTRATADO}


@transaction.atomic
def enviar_cotacao_para_negociacao(cotacao, usuario):
    c = (CotacaoFornecedor.objects.select_for_update().select_related("processo", "fornecedor", "processo__item_cronograma").get(pk=cotacao.pk))
    p = ProcessoCompra.objects.select_for_update().select_related("item_cronograma").get(pk=c.processo_id)
    if _processo_bloqueado(p):
        raise ValidationError("Este processo não pode mais ser alterado.")
    if c.enviada_aprovacao_em:
        raise ValidationError("Esta proposta já está com o gestor.")
    if not c.itens.exists():
        raise ValidationError("A proposta precisa possuir ao menos um item cotado.")
    if processo_exige_compatibilizacao(p) and not cotacao_elegivel_para_negociacao(c):
        raise ValidationError("Todos os itens desta proposta precisam estar tecnicamente aprovados antes da negociação.")
    agora = timezone.now()
    if not c.enviada_negociacao_em:
        c.enviada_negociacao_em = agora
        c.enviada_negociacao_por = usuario
        c.save(update_fields=["enviada_negociacao_em", "enviada_negociacao_por", "atualizado_em"])
    if p.etapa_atual in {p.Etapa.COTACAO, p.Etapa.COMPATIBILIZACAO}:
        p.data_cotacao_concluida = p.data_cotacao_concluida or agora
        if processo_exige_compatibilizacao(p):
            p.data_compatibilizacao_concluida = p.data_compatibilizacao_concluida or agora
        p.etapa_atual = p.Etapa.NEGOCIACAO
        p.status = p.Status.EM_NEGOCIACAO
        p.save(update_fields=["data_cotacao_concluida", "data_compatibilizacao_concluida", "etapa_atual", "status", "atualizado_em"])
        sincronizar_data_real(p, "COTACAO", usuario)
        if processo_exige_compatibilizacao(p):
            sincronizar_data_real(p, "COMPATIBILIZACAO", usuario)
    registrar_evento(p, "PROPOSTA_ENVIADA_NEGOCIACAO", usuario, f"Proposta de {c.fornecedor.nome} liberada individualmente para negociação.")
    return c


@transaction.atomic
def enviar_cotacao_para_compatibilizacao(cotacao, usuario):
    c = (CotacaoFornecedor.objects.select_for_update().select_related("processo", "fornecedor", "processo__item_cronograma").get(pk=cotacao.pk))
    p = ProcessoCompra.objects.select_for_update().select_related("item_cronograma").get(pk=c.processo_id)
    if not processo_exige_compatibilizacao(p):
        return enviar_cotacao_para_negociacao(c, usuario)
    if p.etapa_atual not in {p.Etapa.COTACAO, p.Etapa.COMPATIBILIZACAO, p.Etapa.NEGOCIACAO, p.Etapa.APROVACAO}:
        raise ValidationError("O processo já não aceita novos envios para compatibilização.")
    if _processo_bloqueado(p):
        raise ValidationError("Este processo não pode mais ser alterado.")
    if c.enviada_aprovacao_em:
        raise ValidationError("Esta proposta já está com o gestor.")
    if not c.itens.exists():
        raise ValidationError("A proposta precisa possuir ao menos um item cotado antes do envio.")
    if c.enviada_compatibilizacao_em:
        return c
    agora = timezone.now()
    c.enviada_compatibilizacao_em = agora
    c.enviada_compatibilizacao_por = usuario
    c.save(update_fields=["enviada_compatibilizacao_em", "enviada_compatibilizacao_por", "atualizado_em"])
    if p.etapa_atual == p.Etapa.COTACAO:
        p.data_cotacao_concluida = p.data_cotacao_concluida or agora
        p.etapa_atual = p.Etapa.COMPATIBILIZACAO
        p.status = p.Status.EM_COMPATIBILIZACAO
        p.save(update_fields=["data_cotacao_concluida", "etapa_atual", "status", "atualizado_em"])
        sincronizar_data_real(p, "COTACAO", usuario)
    registrar_evento(p, "PROPOSTA_ENVIADA_COMPATIBILIZACAO", usuario, f"Proposta de {c.fornecedor.nome} enviada individualmente para compatibilização técnica.")
    return c


@transaction.atomic
def concluir_compatibilizacao(processo, usuario):
    p = ProcessoCompra.objects.select_for_update().select_related("item_cronograma").get(pk=processo.pk)
    if not processo_exige_compatibilizacao(p):
        raise ValidationError("Materiais variados não passam por compatibilização.")
    cotacoes = list(p.cotacoes.filter(enviada_compatibilizacao_em__isnull=False, enviada_aprovacao_em__isnull=True).prefetch_related("itens__compatibilizacoes"))
    liberadas = 0
    for cotacao in cotacoes:
        if cotacao_elegivel_para_negociacao(cotacao) and not cotacao.enviada_negociacao_em:
            enviar_cotacao_para_negociacao(cotacao, usuario)
            liberadas += 1
    if not any(c.enviada_negociacao_em or cotacao_elegivel_para_negociacao(c) for c in cotacoes):
        raise ValidationError("Ainda não existe proposta tecnicamente aprovada para liberar a negociação.")
    return ProcessoCompra.objects.get(pk=p.pk)


@transaction.atomic
def enviar_cotacao_para_aprovacao(cotacao, usuario):
    c = (CotacaoFornecedor.objects.select_for_update().select_related("processo", "fornecedor", "processo__item_cronograma").get(pk=cotacao.pk))
    p = ProcessoCompra.objects.select_for_update().select_related("item_cronograma").get(pk=c.processo_id)
    if _processo_bloqueado(p):
        raise ValidationError("Este processo não pode mais ser alterado.")
    if not c.enviada_negociacao_em:
        raise ValidationError("Envie esta proposta para negociação antes de encaminhá-la ao gestor.")
    if not cotacao_elegivel_para_negociacao(c):
        raise ValidationError("A proposta ainda não está elegível para aprovação.")
    agora = timezone.now()
    c.enviada_aprovacao_em = agora
    c.enviada_aprovacao_por = usuario
    c.save(update_fields=["enviada_aprovacao_em", "enviada_aprovacao_por", "atualizado_em"])
    p.data_negociacao_concluida = p.data_negociacao_concluida or agora
    p.etapa_atual = p.Etapa.APROVACAO
    p.status = p.Status.AGUARDANDO_APROVACAO
    p.save(update_fields=["data_negociacao_concluida", "etapa_atual", "status", "atualizado_em"])
    sincronizar_data_real(p, "NEGOCIACAO", usuario)
    registrar_evento(p, "PROPOSTA_ENVIADA_APROVACAO", usuario, f"Proposta de {c.fornecedor.nome} enviada individualmente ao gestor.")
    return c


@transaction.atomic
def devolver_cotacao_para_negociacao(cotacao, usuario):
    c = CotacaoFornecedor.objects.select_for_update().select_related("processo", "fornecedor").get(pk=cotacao.pk)
    p = ProcessoCompra.objects.select_for_update().get(pk=c.processo_id)
    if not c.enviada_aprovacao_em:
        raise ValidationError("Esta proposta não está em aprovação.")
    c.enviada_aprovacao_em = None
    c.enviada_aprovacao_por = None
    if not c.enviada_negociacao_em:
        c.enviada_negociacao_em = timezone.now()
        c.enviada_negociacao_por = usuario
    c.save(update_fields=["enviada_aprovacao_em", "enviada_aprovacao_por", "enviada_negociacao_em", "enviada_negociacao_por", "atualizado_em"])
    if not p.cotacoes.filter(enviada_aprovacao_em__isnull=False).exists():
        p.etapa_atual = p.Etapa.NEGOCIACAO
        p.status = p.Status.EM_NEGOCIACAO
        p.save(update_fields=["etapa_atual", "status", "atualizado_em"])
    registrar_evento(p, "PROPOSTA_DEVOLVIDA_NEGOCIACAO", usuario, f"Gestor devolveu a proposta de {c.fornecedor.nome} para negociação.")
    return c


@transaction.atomic
def retornar_processo_etapa_anterior(processo, usuario, gestor=False):
    p = ProcessoCompra.objects.select_for_update().select_related("item_cronograma").get(pk=processo.pk)
    if _processo_bloqueado(p):
        raise ValidationError("Este processo não pode mais retornar de etapa.")
    if p.etapa_atual == p.Etapa.APROVACAO:
        if not gestor:
            raise ValidationError("Após o envio para aprovação, somente o gestor pode retornar o processo.")
        p.cotacoes.filter(enviada_aprovacao_em__isnull=False).update(enviada_aprovacao_em=None, enviada_aprovacao_por=None)
        p.etapa_atual = p.Etapa.NEGOCIACAO
        p.status = p.Status.EM_NEGOCIACAO
        mensagem = "Gestor retornou o processo da aprovação para negociação."
    elif p.etapa_atual == p.Etapa.NEGOCIACAO:
        p.cotacoes.update(enviada_negociacao_em=None, enviada_negociacao_por=None, enviada_aprovacao_em=None, enviada_aprovacao_por=None)
        if processo_exige_compatibilizacao(p):
            p.etapa_atual = p.Etapa.COMPATIBILIZACAO
            p.status = p.Status.EM_COMPATIBILIZACAO
            mensagem = "Processo retornado da negociação para compatibilização."
        else:
            p.etapa_atual = p.Etapa.COTACAO
            p.status = p.Status.EM_COTACAO
            mensagem = "Processo retornado da negociação para cotação."
    elif p.etapa_atual == p.Etapa.COMPATIBILIZACAO:
        p.cotacoes.update(enviada_compatibilizacao_em=None, enviada_compatibilizacao_por=None, enviada_negociacao_em=None, enviada_negociacao_por=None, enviada_aprovacao_em=None, enviada_aprovacao_por=None)
        p.etapa_atual = p.Etapa.COTACAO
        p.status = p.Status.EM_COTACAO
        mensagem = "Processo retornado da compatibilização para cotação."
    else:
        raise ValidationError("Não existe etapa anterior disponível para retorno neste momento.")
    p.save(update_fields=["etapa_atual", "status", "atualizado_em"])
    registrar_evento(p, "PROCESSO_RETORNOU_ETAPA", usuario, mensagem)
    return p


@transaction.atomic
def concluir_negociacao(processo, usuario):
    """Compatibilidade com chamadas antigas: envia individualmente todas as propostas já liberadas."""
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    cotacoes = list(p.cotacoes.filter(enviada_negociacao_em__isnull=False, enviada_aprovacao_em__isnull=True))
    if not cotacoes:
        raise ValidationError("Não há fornecedor em negociação para enviar à aprovação.")
    for cotacao in cotacoes:
        enviar_cotacao_para_aprovacao(cotacao, usuario)
    return ProcessoCompra.objects.get(pk=p.pk)


def _criar_adjudicacoes_da_aprovacao(*, processo, usuario, selecoes):
    """Converte a escolha do gestor em adjudicações internas."""
    selecoes = list(selecoes or [])
    if not selecoes:
        raise ValidationError("Selecione ao menos uma proposta para aprovar.")

    # O gestor escolhe diretamente os itens no mapa. A quantidade aprovada
    # é sempre a quantidade já ofertada/compatibilizada; não existe edição
    # manual de quantidade na etapa de aprovação.
    totais = {}
    for selecao in selecoes:
        item = selecao["item_cotado"]
        quantidade = Decimal(str(item.quantidade or 0))
        if item.cotacao.processo_id != processo.pk:
            raise ValidationError("Uma das propostas selecionadas não pertence a este processo.")
        if not item.cotacao.enviada_aprovacao_em:
            raise ValidationError(f"A proposta de {item.cotacao.fornecedor.nome} ainda não foi enviada individualmente para aprovação.")
        if not item_tecnicamente_aprovado(item):
            raise ValidationError(
                f"A proposta de {item.cotacao.fornecedor.nome} para {item.necessidade.descricao} não possui aprovação técnica válida."
            )
        if quantidade <= 0:
            raise ValidationError(
                f"A proposta de {item.cotacao.fornecedor.nome} para {item.necessidade.descricao} não possui quantidade válida."
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
        quantidade = Decimal(str(item.quantidade or 0))

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
            f"Gestor selecionou {item.necessidade.descricao} com {item.cotacao.fornecedor.nome} no mapa de cotação ({quantidade} {item.necessidade.unidade}).",
            {"adjudicacao_id": adj.pk, "item_cotado_id": item.pk},
        )
    return criadas


@transaction.atomic
def decidir_aprovacao(processo, usuario, decisao, observacao="", selecoes=None):
    """
    Registra a decisão do gestor.

    APROVADO: o gestor escolhe as propostas; o sistema cria adjudicações internas,
    gera pedidos automaticamente e finaliza o mapa.
    AJUSTE_SOLICITADO: retorna para Negociação, preservando os ajustes comerciais para edição.
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
        # A ressalva do gestor reabre a etapa comercial. Não apagamos a
        # negociação existente: o comprador precisa enxergar os valores já
        # negociados e poder editá-los antes de reenviar ao gestor.
        p.cotacoes.filter(enviada_aprovacao_em__isnull=False).update(
            enviada_aprovacao_em=None,
            enviada_aprovacao_por=None,
        )
        p.status = p.Status.EM_NEGOCIACAO
        p.etapa_atual = p.Etapa.NEGOCIACAO
        p.data_negociacao_concluida = None
        p.save(update_fields=[
            "status", "etapa_atual", "data_negociacao_concluida", "atualizado_em",
        ])
        registrar_evento(
            p, "AJUSTE_SOLICITADO_GESTOR", usuario,
            "Gestor aprovou com ressalva/solicitou ajuste. Processo retornou para Negociação.",
            {"ciclo": ciclo, "observacao": observacao},
        )
        return aprovacao

    if decisao == AprovacaoCompra.Decisao.REPROVADO:
        aprovacao = AprovacaoCompra.objects.create(
            processo=p, ciclo=ciclo, alcada=None, usuario=usuario, decisao=decisao, observacao=observacao
        )

        # A reprovação do gestor encerra o processo sem fornecedor aprovado.
        # Cancela qualquer adjudicação ativa que possa ter ficado de ciclo anterior/legado,
        # evitando que outras telas interpretem a proposta como aprovada pelo gestor.
        agora = timezone.now()
        AdjudicacaoCompra.objects.filter(processo=p, cancelada=False).update(
            cancelada=True,
            cancelada_por=usuario,
            cancelada_em=agora,
            motivo_cancelamento=(
                f"Seleção cancelada automaticamente no ciclo {ciclo}: "
                "processo reprovado pelo gestor."
            ),
        )

        p.status = p.Status.REPROVADO
        p.etapa_atual = p.Etapa.APROVACAO
        p.save(update_fields=["status", "etapa_atual", "atualizado_em"])
        registrar_evento(
            p,
            "PROCESSO_REPROVADO",
            usuario,
            "Compra reprovada pelo gestor e processo encerrado sem fornecedor aprovado.",
            {"ciclo": ciclo, "observacao": observacao},
        )
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
