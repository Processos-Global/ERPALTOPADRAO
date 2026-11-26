from decimal import Decimal

from django.db.models import F, Q, Sum

from compras.models import PedidoCompra, PedidoCompraItem, ReservaEstoqueCompra
from obras.services.estoque import saldo_fisico_compativel


ZERO = Decimal("0")


def obter_cobertura(*, obra, material, unidade, especificacao, quantidade, processo=None, excluir_reserva=None):
    """Consulta estoque e mostra pedidos relacionados sem presumir que atendem a mesma demanda."""
    fisico = saldo_fisico_compativel(obra, material, unidade, especificacao)
    reservas = ReservaEstoqueCompra.objects.filter(
        obra=obra, material=material, unidade__iexact=unidade,
        especificacao=especificacao,
        status=ReservaEstoqueCompra.Status.ATIVA,
    )
    if excluir_reserva:
        reservas = reservas.exclude(pk=excluir_reserva)
    reservado = reservas.aggregate(total=Sum("quantidade_disponivel"))["total"] or ZERO
    disponivel = max(fisico["saldo_compativel"] - reservado, ZERO)

    pendente_potencial = ZERO
    if processo and processo.item_cronograma_id:
        itens = PedidoCompraItem.objects.filter(
            pedido__obra=obra,
            necessidade__processo__item_cronograma_id=processo.item_cronograma_id,
            necessidade__material=material,
            unidade__iexact=unidade,
            especificacao=especificacao,
        ).exclude(pedido__status=PedidoCompra.Status.CANCELADO).exclude(
            pedido__processo=processo
        ).values_list("quantidade", "quantidade_recebida")
        # Um item do cronograma pode originar processos independentes. A coincidência
        # de obra/material/especificação não prova que o pedido cobre esta demanda.
        pendente_potencial = sum((max(qtd - recebida, ZERO) for qtd, recebida in itens), ZERO)

    necessidade = Decimal(str(quantidade))
    reservavel = min(necessidade, disponivel)
    descoberta = max(necessidade - disponivel, ZERO)
    return {
        "necessidade": necessidade,
        "saldo_fisico": fisico["saldo_fisico"],
        "saldo_compativel": fisico["saldo_compativel"],
        "especificacao_ambigua": fisico["ambiguidade"],
        "reservado": reservado,
        "disponivel": disponivel,
        "pendente_potencial": pendente_potencial,
        "reservavel": reservavel,
        "descoberta": descoberta,
    }


def _quantidades_pedido(necessidade):
    itens = PedidoCompraItem.objects.filter(
        necessidade=necessidade, pedido__obra_id=necessidade.processo.obra_id,
        pedido__processo_id=necessidade.processo_id,
        unidade__iexact=necessidade.unidade, especificacao=necessidade.especificacao,
    ).order_by().annotate(
        recebido=Sum("recebimentos__quantidade", filter=Q(recebimentos__recebimento__pedido_id=F("pedido_id"))),
    ).values_list("pedido__status", "quantidade", "recebido")
    contratado = recebido = pendente = ZERO
    for status, quantidade, quantidade_recebida in itens:
        quantidade_recebida = quantidade_recebida or ZERO
        recebido += quantidade_recebida
        if status != PedidoCompra.Status.CANCELADO:
            contratado += quantidade
            pendente += max(quantidade - quantidade_recebida, ZERO)
    return contratado, recebido, pendente


def _reserva_historica(necessidade):
    reserva = ReservaEstoqueCompra.objects.select_related("material").filter(
        necessidade=necessidade, obra_id=necessidade.processo.obra_id,
    ).first()
    if not reserva:
        return None, ZERO
    if reserva.status == ReservaEstoqueCompra.Status.LIBERADA:
        movimentos = reserva.movimentos.filter(obra_origem_id=reserva.obra_id).aggregate(total=Sum("quantidade"))
        return reserva, min(reserva.quantidade_original, movimentos["total"] or ZERO)
    return reserva, max(reserva.quantidade_original - reserva.quantidade_disponivel, ZERO)


def _estoque_para_atender(cobertura, reserva_propria, recebido):
    outras_reservas = max(cobertura["reservado"] - reserva_propria, ZERO)
    reserva_coberta = min(reserva_propria, max(cobertura["saldo_compativel"] - outras_reservas, ZERO))
    # O saldo livre pode incluir as mesmas entradas já contadas no recebimento.
    # Sem atribuição de lotes nas saídas, este é o limite sem dupla contagem.
    livre_adicional = max(cobertura["disponivel"] - recebido, ZERO)
    return reserva_coberta + livre_adicional


def resumir_cobertura_necessidade(necessidade):
    """Apura o atendimento histórico e a capacidade de cobertura ainda disponível."""
    processo = necessidade.processo
    cobertura = obter_cobertura(
        obra=processo.obra, material=necessidade.material, unidade=necessidade.unidade,
        especificacao=necessidade.especificacao, quantidade=necessidade.quantidade_necessaria,
    )
    contratado, recebido, pendente = _quantidades_pedido(necessidade)
    reserva, consumido_historico = _reserva_historica(necessidade)
    reserva_propria = consumido = ZERO
    if (
        reserva is not None
        and reserva.material_id == necessidade.material_id
        and reserva.unidade.casefold() == necessidade.unidade.casefold()
        and reserva.especificacao == necessidade.especificacao
    ):
        if reserva.status != ReservaEstoqueCompra.Status.LIBERADA:
            reserva_propria = reserva.quantidade_disponivel
        consumido = consumido_historico
    atendida = min(cobertura["necessidade"], consumido + recebido)
    restante = max(cobertura["necessidade"] - atendida - pendente, ZERO)
    descoberta = max(restante - _estoque_para_atender(cobertura, reserva_propria, recebido), ZERO)
    return {
        **cobertura, "reserva_propria": reserva_propria, "reserva_consumida": consumido,
        "reserva_historica": reserva, "reserva_consumida_historica": consumido_historico,
        "contratado": contratado, "recebido": recebido, "pendente_proprio": pendente,
        "atendida": atendida, "descoberta": descoberta,
    }
