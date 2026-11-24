from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import F, Q, Sum
from django.utils import timezone

from compras.models import NecessidadeCompra, PedidoCompra, PedidoCompraItem, ReservaEstoqueCompra
from obras.services.estoque import saldo_fisico_compativel
from usuarios.models import AcaoCompra

from .auditoria import registrar_evento
from .permissoes import possui_acao_compras


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


def avaliar_solicitacao(*, processo, material, quantidade, usuario, excecao_estoque=False,
                       justificativa_excecao="", excluir_reserva=None):
    quantidade = Decimal(str(quantidade))
    cobertura = obter_cobertura(
        obra=processo.obra, material=material, unidade=material.unidade.sigla,
        especificacao=material.especificacao, quantidade=quantidade,
        processo=processo, excluir_reserva=excluir_reserva,
    )
    if excecao_estoque:
        if not possui_acao_compras(usuario, AcaoCompra.EXCECAO_ESTOQUE):
            raise ValidationError("Sem permissão para exceção de estoque.")
        justificativa_excecao = (justificativa_excecao or "").strip()
        if not justificativa_excecao:
            raise ValidationError("Informe a justificativa da exceção de estoque.")
        return cobertura, quantidade, ZERO, justificativa_excecao

    if cobertura["descoberta"] <= ZERO:
        raise ValidationError(
            "A necessidade está coberta pelo estoque disponível. Não é necessária outra compra."
        )
    return cobertura, cobertura["descoberta"], cobertura["reservavel"], ""


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


def _quantidades_reserva(necessidade):
    reserva = ReservaEstoqueCompra.objects.filter(
        necessidade=necessidade, obra_id=necessidade.processo.obra_id,
        material_id=necessidade.material_id, unidade__iexact=necessidade.unidade,
        especificacao=necessidade.especificacao,
    ).first()
    if not reserva:
        return ZERO, ZERO
    if reserva.status == ReservaEstoqueCompra.Status.LIBERADA:
        movimentos = reserva.movimentos.filter(obra_origem_id=reserva.obra_id).aggregate(total=Sum("quantidade"))
        return ZERO, min(reserva.quantidade_original, movimentos["total"] or ZERO)
    return reserva.quantidade_disponivel, max(reserva.quantidade_original - reserva.quantidade_disponivel, ZERO)


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
    reserva_propria, consumido = _quantidades_reserva(necessidade)
    atendida = min(cobertura["necessidade"], consumido + recebido)
    restante = max(cobertura["necessidade"] - atendida - pendente, ZERO)
    descoberta = max(restante - _estoque_para_atender(cobertura, reserva_propria, recebido), ZERO)
    return {
        **cobertura, "reserva_propria": reserva_propria, "reserva_consumida": consumido,
        "contratado": contratado, "recebido": recebido, "pendente_proprio": pendente,
        "atendida": atendida, "descoberta": descoberta,
    }


def liberar_reservas_ativas(*, processo):
    """Libera o que sobrou de um processo encerrado, mantendo movimentos e a origem."""
    return ReservaEstoqueCompra.objects.filter(
        necessidade__processo=processo, obra_id=processo.obra_id,
        status=ReservaEstoqueCompra.Status.ATIVA,
    ).update(status=ReservaEstoqueCompra.Status.LIBERADA, quantidade_disponivel=ZERO, atualizado_em=timezone.now())


def registrar_cobertura(*, processo, necessidade, usuario, cobertura, quantidade_reservada,
                        justificativa_excecao=""):
    ReservaEstoqueCompra.objects.filter(necessidade=necessidade).update(
        status=ReservaEstoqueCompra.Status.LIBERADA, quantidade_disponivel=ZERO,
    )
    if quantidade_reservada > ZERO:
        ReservaEstoqueCompra.objects.update_or_create(
            necessidade=necessidade,
            defaults={
                "obra": processo.obra, "material": necessidade.material,
                "unidade": necessidade.unidade, "especificacao": necessidade.especificacao,
                "quantidade_original": quantidade_reservada,
                "quantidade_disponivel": quantidade_reservada, "criado_por": usuario,
                "status": ReservaEstoqueCompra.Status.ATIVA,
            },
        )
    dados = {
        "necessidade_id": necessidade.pk,
        "material_id": necessidade.material_id,
        "quantidade_necessaria": str(necessidade.quantidade_necessaria),
        "quantidade_compra": str(necessidade.quantidade_incluida),
        "saldo_fisico": str(cobertura["saldo_fisico"]),
        "reservado_anterior": str(cobertura["reservado"]),
        "pedido_pendente_potencial": str(cobertura["pendente_potencial"]),
        "quantidade_reservada": str(quantidade_reservada),
    }
    if justificativa_excecao:
        dados["justificativa"] = justificativa_excecao
        registrar_evento(
            processo, "EXCECAO_ESTOQUE", usuario,
            f"Exceção de estoque para {necessidade.descricao}: {justificativa_excecao}", dados,
        )
    else:
        registrar_evento(processo, "COBERTURA_ESTOQUE_AVALIADA", usuario,
                        f"Cobertura conferida para {necessidade.descricao}.", dados)


def revalidar_necessidade(necessidade, *, quantidade_compra=None):
    """Valida a quantidade a emitir, preservando os recebimentos sobre vínculos oficiais."""
    processo = necessidade.processo
    if necessidade.situacao == NecessidadeCompra.Situacao.CANCELADA:
        raise ValidationError(f"A necessidade {necessidade.descricao} está cancelada.")
    quantidade_compra = necessidade.quantidade_incluida if quantidade_compra is None else quantidade_compra
    _, recebido, pendente = _quantidades_pedido(necessidade)
    reserva_propria, consumido = _quantidades_reserva(necessidade)
    restante = max(necessidade.quantidade_necessaria - recebido - consumido - pendente, ZERO)
    if quantidade_compra > restante:
        raise ValidationError(
            f"A quantidade a emitir para {necessidade.descricao} excede o saldo da necessidade. "
            "Revise a contratação considerando o que já foi atendido e os pedidos em aberto."
        )

    ultima_avaliacao = processo.historico.filter(
        tipo__in=["COBERTURA_ESTOQUE_AVALIADA", "EXCECAO_ESTOQUE"],
        dados__necessidade_id=necessidade.pk,
    ).values_list("tipo", flat=True).first()
    if ultima_avaliacao != "COBERTURA_ESTOQUE_AVALIADA":
        return

    cobertura = obter_cobertura(
        obra=processo.obra, material=necessidade.material,
        unidade=necessidade.unidade, especificacao=necessidade.especificacao,
        quantidade=necessidade.quantidade_necessaria,
    )
    pendente_compra = max(restante - _estoque_para_atender(cobertura, reserva_propria, recebido), ZERO)
    if quantidade_compra != pendente_compra:
        raise ValidationError(
            f"A cobertura de {necessidade.descricao} mudou. Revise o estoque e a quantidade antes de continuar."
        )
