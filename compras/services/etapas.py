from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compras.models import AprovacaoCompra, ProcessoCompra

from .adjudicacoes import validar_adjudicacao_completa
from .alcadas import resolver_alcada_aprovacao
from .auditoria import registrar_evento
from .comercial import queryset_itens_tecnicamente_aprovados, total_aprovacao_processo
from .integracao_planejamento import sincronizar_data_real


@transaction.atomic
def concluir_cotacao(processo, usuario):
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual != p.Etapa.COTACAO:
        raise ValidationError("O processo não está na etapa de cotação.")
    if p.status in {p.Status.CANCELADO, p.Status.REPROVADO, p.Status.CONTRATADO}:
        raise ValidationError("Este processo não pode mais ser alterado.")

    necessidades = p.necessidades.filter(situacao="ATIVA")
    if not necessidades.exists():
        raise ValidationError("Inclua ao menos uma necessidade antes de concluir a cotação.")
    if not p.cotacoes.filter(itens__isnull=False).exists():
        raise ValidationError("Inclua ao menos uma proposta com item cotado.")

    # Toda necessidade precisa ter pelo menos uma proposta para não avançar com lacunas.
    sem_proposta = necessidades.exclude(itens_cotados__cotacao__processo=p).distinct()
    if sem_proposta.exists():
        nomes = ", ".join(sem_proposta.values_list("descricao", flat=True)[:5])
        raise ValidationError(f"Existem necessidades sem proposta comercial: {nomes}.")

    p.data_cotacao_concluida = timezone.now()
    p.etapa_atual = p.Etapa.COMPATIBILIZACAO
    p.status = p.Status.AGUARDANDO_COMPATIBILIZACAO
    p.save(update_fields=["data_cotacao_concluida", "etapa_atual", "status", "atualizado_em"])
    sincronizar_data_real(p, "COTACAO", usuario)
    registrar_evento(p, "COTACAO_CONCLUIDA", usuario, "Cotação concluída e enviada para análise técnica.")
    return p


@transaction.atomic
def concluir_compatibilizacao(processo, usuario):
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual != p.Etapa.COMPATIBILIZACAO:
        raise ValidationError("O processo não está na etapa de análise técnica.")

    necessidades = list(p.necessidades.filter(situacao="ATIVA"))
    if not necessidades:
        raise ValidationError("O processo não possui itens ativos para análise técnica.")

    # Filtra os itens cotados pela ÚLTIMA decisão técnica.
    from compras.models import CotacaoFornecedorItem
    itens_validos = queryset_itens_tecnicamente_aprovados(
        CotacaoFornecedorItem.objects.filter(cotacao__processo=p)
    )
    necessidades_validas = set(itens_validos.values_list("necessidade_id", flat=True))
    pendentes = [n for n in necessidades if n.pk not in necessidades_validas]
    if pendentes:
        nomes = ", ".join(n.descricao for n in pendentes[:5])
        raise ValidationError(f"Existe item obrigatório sem solução técnica válida: {nomes}.")

    p.data_compatibilizacao_concluida = timezone.now()
    p.etapa_atual = p.Etapa.NEGOCIACAO
    p.status = p.Status.EM_NEGOCIACAO
    p.save(update_fields=["data_compatibilizacao_concluida", "etapa_atual", "status", "atualizado_em"])
    sincronizar_data_real(p, "COMPATIBILIZACAO", usuario)
    registrar_evento(p, "COMPATIBILIZACAO_CONCLUIDA", usuario, "Análise técnica concluída. Processo enviado para negociação.")
    return p


@transaction.atomic
def concluir_negociacao(processo, usuario):
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual != p.Etapa.NEGOCIACAO:
        raise ValidationError("O processo não está na etapa de negociação.")
    if not p.adjudicacoes.filter(cancelada=False).exists():
        raise ValidationError("Selecione ao menos um fornecedor antes de concluir a negociação.")

    validar_adjudicacao_completa(p)
    p.data_negociacao_concluida = timezone.now()
    p.etapa_atual = p.Etapa.APROVACAO
    p.status = p.Status.AGUARDANDO_APROVACAO
    p.save(update_fields=["data_negociacao_concluida", "etapa_atual", "status", "atualizado_em"])
    sincronizar_data_real(p, "NEGOCIACAO", usuario)
    registrar_evento(p, "NEGOCIACAO_CONCLUIDA", usuario, "Negociação concluída e enviada para aprovação.")
    return p


@transaction.atomic
def decidir_aprovacao(processo, usuario, decisao, observacao=""):
    """Aprova, reprova ou devolve para negociação. Aprovação gera pedidos automaticamente."""
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.etapa_atual != p.Etapa.APROVACAO:
        raise ValidationError("O processo não está aguardando aprovação.")
    if decisao not in AprovacaoCompra.Decisao.values:
        raise ValidationError("Decisão de aprovação inválida.")

    observacao = (observacao or "").strip()
    if decisao in {AprovacaoCompra.Decisao.AJUSTE_SOLICITADO, AprovacaoCompra.Decisao.REPROVADO} and not observacao:
        raise ValidationError("Informe o motivo da decisão.")

    validar_adjudicacao_completa(p)
    total = total_aprovacao_processo(p)
    alcada = resolver_alcada_aprovacao(p, usuario, total) if decisao == AprovacaoCompra.Decisao.APROVADO else None
    ciclo = (p.aprovacoes.order_by("-ciclo").values_list("ciclo", flat=True).first() or 0) + 1

    aprovacao = AprovacaoCompra.objects.create(
        processo=p,
        ciclo=ciclo,
        alcada=alcada,
        usuario=usuario,
        decisao=decisao,
        observacao=observacao,
    )

    if decisao == AprovacaoCompra.Decisao.AJUSTE_SOLICITADO:
        p.status = p.Status.AJUSTE_SOLICITADO
        p.etapa_atual = p.Etapa.NEGOCIACAO
        p.data_negociacao_concluida = None
        p.save(update_fields=["status", "etapa_atual", "data_negociacao_concluida", "atualizado_em"])
        registrar_evento(p, "APROVACAO", usuario, "Ajuste solicitado. Processo retornou para negociação.", {"ciclo": ciclo})
        return aprovacao

    if decisao == AprovacaoCompra.Decisao.REPROVADO:
        p.status = p.Status.REPROVADO
        p.etapa_atual = p.Etapa.APROVACAO
        p.save(update_fields=["status", "etapa_atual", "atualizado_em"])
        registrar_evento(p, "PROCESSO_REPROVADO", usuario, "Compra reprovada e processo encerrado.", {"ciclo": ciclo})
        return aprovacao

    # APROVADO: mantém APROVADO enquanto gera; gerar_pedidos fecha como CONTRATADO.
    p.status = p.Status.APROVADO
    p.save(update_fields=["status", "atualizado_em"])
    registrar_evento(
        p,
        "APROVACAO",
        usuario,
        f"Compra aprovada no valor de R$ {total:,.2f}. Pedidos serão gerados automaticamente.",
        {"ciclo": ciclo, "alcada_id": getattr(alcada, "pk", None), "valor": str(total)},
    )

    from .pedidos import gerar_pedidos
    pedidos = gerar_pedidos(p, usuario)
    registrar_evento(p, "PEDIDOS_GERADOS_APROVACAO", usuario, f"{len(pedidos)} pedido(s) disponível(is) após aprovação.")
    return aprovacao
