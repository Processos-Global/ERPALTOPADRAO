from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from compras.models import AdjudicacaoCompra

from .auditoria import registrar_evento
from .comercial import calcular_desconto_adjudicacao, item_tecnicamente_aprovado


# ============================================================
# HELPERS
# ============================================================


def _quantidade_adjudicada(necessidade):
    """
    Retorna a quantidade total já adjudicada para uma necessidade,
    desconsiderando adjudicações canceladas.
    """

    return (
        necessidade.adjudicacoes
        .filter(
            cancelada=False
        )
        .aggregate(
            v=Sum("quantidade")
        )["v"]
        or Decimal("0")
    )


# ============================================================
# SALDOS DAS NECESSIDADES
# ============================================================


def obter_saldos_adjudicacao(processo):
    """
    Retorna o saldo comercial das necessidades ativas
    do processo.

    Cada item retornado contém:

    - necessidade
    - quantidade_incluida
    - quantidade_adjudicada
    - saldo

    Importante:
    NecessidadeCompra não possui mais relacionamento com
    InsumoPlanejamento. A origem atual do item é representada
    principalmente por atividade_origem e pelos próprios campos
    da necessidade.
    """

    resultados = []

    necessidades = (
        processo
        .necessidades
        .filter(
            situacao="ATIVA"
        )
        .select_related(
            "atividade_origem",
        )
        .order_by(
            "descricao",
            "id",
        )
    )

    for necessidade in necessidades:

        adjudicado = (
            _quantidade_adjudicada(
                necessidade
            )
        )

        incluido = (
            necessidade.quantidade_incluida
            or Decimal("0")
        )

        saldo = max(
            incluido - adjudicado,
            Decimal("0"),
        )

        resultados.append(
            {
                "necessidade": necessidade,
                "quantidade_incluida": incluido,
                "quantidade_adjudicada": adjudicado,
                "saldo": saldo,
            }
        )

    return resultados


# ============================================================
# VALIDAÇÃO DA NEGOCIAÇÃO
# ============================================================


def validar_adjudicacao_completa(processo):
    """
    Impede que a negociação seja concluída enquanto existir
    alguma necessidade ativa com quantidade ainda não
    adjudicada.
    """

    pendencias = [
        item
        for item in obter_saldos_adjudicacao(
            processo
        )
        if item["saldo"] > Decimal("0")
    ]

    if not pendencias:
        return True

    detalhes = []

    for item in pendencias:

        necessidade = (
            item["necessidade"]
        )

        detalhes.append(
            (
                f"{necessidade.descricao}: "
                f"necessário "
                f"{item['quantidade_incluida']} "
                f"{necessidade.unidade}, "
                f"adjudicado "
                f"{item['quantidade_adjudicada']} "
                f"{necessidade.unidade}, "
                f"saldo "
                f"{item['saldo']} "
                f"{necessidade.unidade}"
            )
        )

    raise ValidationError(
        [
            (
                "Não é possível enviar o processo para aprovação "
                "enquanto houver necessidade com saldo "
                "não adjudicado."
            ),
            *detalhes,
        ]
    )


# ============================================================
# ADJUDICAÇÃO / SELEÇÃO DO FORNECEDOR
# ============================================================


@transaction.atomic
def adjudicar(
    *,
    processo,
    item_cotado,
    quantidade,
    usuario,
):
    """
    Registra a seleção comercial de determinada quantidade
    de um item cotado.

    A adjudicação representa quanto da necessidade será
    efetivamente comprado daquele fornecedor.
    """

    necessidade = (
        item_cotado.necessidade
    )

    quantidade = Decimal(
        str(quantidade)
    )

    # --------------------------------------------------------
    # ETAPA
    # --------------------------------------------------------

    if (
        processo.etapa_atual
        != processo.Etapa.NEGOCIACAO
    ):
        raise ValidationError(
            (
                "Adjudicações só podem ser registradas "
                "durante a etapa de negociação."
            )
        )

    # --------------------------------------------------------
    # PERTENCIMENTO AO PROCESSO
    # --------------------------------------------------------

    if (
        item_cotado.cotacao.processo_id
        != processo.id
    ):
        raise ValidationError(
            (
                "O item cotado não pertence "
                "a este processo."
            )
        )

    if (
        necessidade.processo_id
        != processo.id
    ):
        raise ValidationError(
            (
                "A necessidade não pertence "
                "a este processo."
            )
        )

    # --------------------------------------------------------
    # VALIDAÇÃO TÉCNICA
    # --------------------------------------------------------

    tecnicamente_aprovado = item_tecnicamente_aprovado(item_cotado)

    if not tecnicamente_aprovado:
        raise ValidationError(
            "Somente itens cuja ÚLTIMA análise técnica esteja aprovada ou aprovada com ressalva podem ser selecionados para compra."
        )

    # --------------------------------------------------------
    # BLOQUEIO DA NECESSIDADE
    #
    # Evita duas operações concorrentes consumirem
    # simultaneamente o mesmo saldo.
    # --------------------------------------------------------

    necessidade = (
        necessidade
        .__class__
        .objects
        .select_for_update()
        .get(
            pk=necessidade.pk
        )
    )

    usado = (
        _quantidade_adjudicada(
            necessidade
        )
    )

    incluido = (
        necessidade.quantidade_incluida
        or Decimal("0")
    )

    saldo = (
        incluido - usado
    )

    # --------------------------------------------------------
    # QUANTIDADE
    # --------------------------------------------------------

    if quantidade <= 0:
        raise ValidationError(
            (
                "A quantidade selecionada deve ser "
                "maior que zero."
            )
        )

    if quantidade > saldo:
        raise ValidationError(
            (
                f"A quantidade informada excede o saldo "
                f"da necessidade. "
                f"Saldo disponível: "
                f"{saldo} {necessidade.unidade}."
            )
        )

    # --------------------------------------------------------
    # CONDIÇÃO NEGOCIADA
    # --------------------------------------------------------

    negociacao = getattr(
        item_cotado,
        "negociacao",
        None,
    )

    valor = (
        negociacao.valor_final_unitario
        if negociacao
        else item_cotado.valor_unitario_cotado
    )

    prazo_entrega = (
        negociacao.prazo_entrega_dias_negociado
        if negociacao
        else item_cotado.cotacao.prazo_entrega_dias
    )

    condicao_pagamento = (
        negociacao.condicao_pagamento_negociada
        if (
            negociacao
            and negociacao.condicao_pagamento_negociada
        )
        else item_cotado.cotacao.condicao_pagamento
    )

    desconto_final = calcular_desconto_adjudicacao(
        item_cotado,
        quantidade,
        valor,
    )

    # --------------------------------------------------------
    # CRIAÇÃO
    # --------------------------------------------------------

    adj = (
        AdjudicacaoCompra.objects.create(
            processo=processo,
            necessidade=necessidade,
            cotacao=(
                item_cotado.cotacao
            ),
            item_cotado=item_cotado,
            quantidade=quantidade,
            valor_unitario_final=valor,
            desconto_final=desconto_final,
            prazo_entrega_dias_final=(
                prazo_entrega
            ),
            condicao_pagamento_final=(
                condicao_pagamento
            ),
            selecionado_por=usuario,
        )
    )

    # --------------------------------------------------------
    # AUDITORIA
    # --------------------------------------------------------

    registrar_evento(
        processo,
        "ADJUDICACAO",
        usuario,
        (
            f"{quantidade} "
            f"{necessidade.unidade} "
            f"adjudicado(s) a "
            f"{item_cotado.cotacao.fornecedor.nome}."
        ),
        {
            "adjudicacao_id": adj.pk,
        },
    )

    return adj


# ============================================================
# CANCELAMENTO DA ADJUDICAÇÃO
# ============================================================


@transaction.atomic
def cancelar_adjudicacao(
    *,
    processo,
    adjudicacao,
    usuario,
    motivo,
):
    """
    Cancela uma adjudicação durante a negociação.

    Ao cancelar, a quantidade volta automaticamente
    a compor o saldo disponível da necessidade.
    """

    motivo = (
        motivo
        or ""
    ).strip()

    # --------------------------------------------------------
    # ETAPA
    # --------------------------------------------------------

    if (
        processo.etapa_atual
        != processo.Etapa.NEGOCIACAO
    ):
        raise ValidationError(
            (
                "A adjudicação só pode ser corrigida "
                "ou cancelada durante a negociação."
            )
        )

    # --------------------------------------------------------
    # BLOQUEIO DO REGISTRO
    # --------------------------------------------------------

    adj = (
        AdjudicacaoCompra.objects
        .select_for_update()
        .select_related(
            "necessidade",
            "cotacao__fornecedor",
        )
        .get(
            pk=adjudicacao.pk
        )
    )

    # --------------------------------------------------------
    # VALIDAÇÕES
    # --------------------------------------------------------

    if (
        adj.processo_id
        != processo.id
    ):
        raise ValidationError(
            (
                "A adjudicação não pertence "
                "a este processo."
            )
        )

    if adj.cancelada:
        raise ValidationError(
            (
                "Esta adjudicação já está "
                "cancelada."
            )
        )

    if not motivo:
        raise ValidationError(
            (
                "Informe o motivo do cancelamento "
                "da adjudicação."
            )
        )

    # --------------------------------------------------------
    # CANCELAMENTO
    # --------------------------------------------------------

    adj.cancelada = True

    adj.cancelada_por = (
        usuario
    )

    adj.cancelada_em = (
        timezone.now()
    )

    adj.motivo_cancelamento = (
        motivo
    )

    adj.save(
        update_fields=[
            "cancelada",
            "cancelada_por",
            "cancelada_em",
            "motivo_cancelamento",
        ]
    )

    # --------------------------------------------------------
    # AUDITORIA
    # --------------------------------------------------------

    registrar_evento(
        processo,
        "ADJUDICACAO_CANCELADA",
        usuario,
        (
            f"Adjudicação de "
            f"{adj.quantidade} "
            f"{adj.necessidade.unidade} "
            f"para "
            f"{adj.cotacao.fornecedor.nome} "
            f"cancelada. "
            f"Motivo: {motivo}"
        ),
        {
            "adjudicacao_id": adj.pk,
        },
    )

    return adj