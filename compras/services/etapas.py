from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compras.models import AprovacaoCompra, AdjudicacaoCompra, NegociacaoItem, ProcessoCompra

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
    if p.status in {p.Status.CANCELADO, p.Status.REPROVADO, p.Status.CONTRATADO}:
        raise ValidationError("Este processo não pode mais ser alterado.")

    necessidades = list(p.necessidades.filter(situacao="ATIVA").order_by("descricao", "id"))
    if not necessidades:
        raise ValidationError("O processo não possui itens ativos para análise técnica.")

    from compras.models import CompatibilizacaoItem, CotacaoFornecedorItem

    itens = list(
        CotacaoFornecedorItem.objects
        .filter(cotacao__processo=p, necessidade__situacao="ATIVA")
        .select_related("cotacao__fornecedor", "necessidade")
        .prefetch_related("compatibilizacoes")
        .order_by("necessidade__descricao", "cotacao__fornecedor__nome", "id")
    )

    # Toda oferta precisa possuir uma decisão técnica atual. Enquanto existir
    # qualquer oferta pendente, a análise permanece aberta e nenhuma transição
    # de etapa é realizada.
    ofertas_pendentes = []
    aprovadas_por_necessidade = set()

    inicio_ciclo_tecnico = p.data_cotacao_concluida

    for item in itens:
        atual = item.compatibilizacoes.first()

        # Em um novo ciclo iniciado após retorno do gestor para Cotação,
        # uma decisão técnica antiga continua no histórico, mas não vale como
        # decisão do ciclo atual. Cada oferta precisa ser analisada novamente.
        if (
            atual is None
            or inicio_ciclo_tecnico is None
            or atual.data < inicio_ciclo_tecnico
        ):
            ofertas_pendentes.append(item)
            continue

        if atual.resultado in {
            CompatibilizacaoItem.Resultado.APROVADO,
            CompatibilizacaoItem.Resultado.APROVADO_COM_RESSALVA,
        }:
            aprovadas_por_necessidade.add(item.necessidade_id)

    if ofertas_pendentes:
        exemplos = ", ".join(
            f"{item.necessidade.descricao} / {item.cotacao.fornecedor.nome}"
            for item in ofertas_pendentes[:5]
        )
        complemento = (
            ""
            if len(ofertas_pendentes) <= 5
            else f" e mais {len(ofertas_pendentes) - 5} oferta(s)"
        )
        raise ValidationError(
            "Existem ofertas sem decisão técnica: " + exemplos + complemento + "."
        )

    # Todas as ofertas já foram analisadas. Se alguma necessidade ficou sem
    # nenhuma alternativa aprovada, a análise técnica terminou com necessidade
    # de nova cotação. O processo retorna para COTAÇÃO, preservando todas as
    # decisões técnicas já registradas para manter o histórico.
    sem_solucao = [n for n in necessidades if n.pk not in aprovadas_por_necessidade]
    if sem_solucao:
        nomes = ", ".join(n.descricao for n in sem_solucao[:5])
        complemento = (
            ""
            if len(sem_solucao) <= 5
            else f" e mais {len(sem_solucao) - 5} item(ns)"
        )

        p.etapa_atual = p.Etapa.COTACAO
        p.status = p.Status.AJUSTE_SOLICITADO
        p.data_cotacao_concluida = None
        p.data_compatibilizacao_concluida = None
        p.save(
            update_fields=[
                "etapa_atual",
                "status",
                "data_cotacao_concluida",
                "data_compatibilizacao_concluida",
                "atualizado_em",
            ]
        )

        registrar_evento(
            p,
            "COMPATIBILIZACAO_RETORNOU_COTACAO",
            usuario,
            (
                "Análise técnica concluída sem alternativa aprovada para: "
                + nomes
                + complemento
                + ". Processo retornado para cotação para inclusão ou correção de proposta."
            ),
            {
                "necessidades_sem_solucao": [n.pk for n in sem_solucao],
            },
        )
        return p

    # Todas as necessidades possuem ao menos uma alternativa tecnicamente válida.
    # O fluxo normal segue para negociação.
    p.data_compatibilizacao_concluida = timezone.now()
    p.etapa_atual = p.Etapa.NEGOCIACAO
    p.status = p.Status.EM_NEGOCIACAO
    p.save(
        update_fields=[
            "data_compatibilizacao_concluida",
            "etapa_atual",
            "status",
            "atualizado_em",
        ]
    )
    sincronizar_data_real(p, "COMPATIBILIZACAO", usuario)
    registrar_evento(
        p,
        "COMPATIBILIZACAO_CONCLUIDA",
        usuario,
        "Análise técnica concluída. Processo enviado para negociação.",
    )
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
    """
    Registra a decisão final do gestor.

    - APROVADO: gera pedidos automaticamente.
    - AJUSTE_SOLICITADO: reinicia o ciclo a partir da Cotação.
    - REPROVADO: encerra definitivamente o processo.
    """
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
        # A solicitação de ajuste do gestor reinicia o ciclo comercial inteiro.
        # As propostas permanecem cadastradas para que possam ser corrigidas ou
        # complementadas, mas as escolhas comerciais ativas deixam de valer.
        agora = timezone.now()
        AdjudicacaoCompra.objects.filter(
            processo=p,
            cancelada=False,
        ).update(
            cancelada=True,
            cancelada_por=usuario,
            cancelada_em=agora,
            motivo_cancelamento=(
                f"Seleção cancelada automaticamente no ciclo {ciclo}: "
                "gestor solicitou ajuste e o processo retornou para cotação."
            ),
        )

        # A condição negociada atual também não deve ser reaproveitada
        # automaticamente no novo ciclo. O histórico de negociação permanece
        # preservado em HistoricoNegociacaoItem.
        NegociacaoItem.objects.filter(
            item_cotado__cotacao__processo=p
        ).delete()

        p.status = p.Status.AJUSTE_SOLICITADO
        p.etapa_atual = p.Etapa.COTACAO
        p.data_cotacao_concluida = None
        p.data_compatibilizacao_concluida = None
        p.data_negociacao_concluida = None
        p.save(
            update_fields=[
                "status",
                "etapa_atual",
                "data_cotacao_concluida",
                "data_compatibilizacao_concluida",
                "data_negociacao_concluida",
                "atualizado_em",
            ]
        )
        registrar_evento(
            p,
            "AJUSTE_SOLICITADO_GESTOR",
            usuario,
            (
                "Gestor solicitou ajuste. Processo retornou para Cotação e deverá "
                "passar novamente por Cotação, Análise Técnica, Negociação e Aprovação."
            ),
            {"ciclo": ciclo, "observacao": observacao},
        )
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
