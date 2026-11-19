from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from compras.models import PedidoCompra, PedidoCompraItem, ReservaEstoqueCompra
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


def revalidar_necessidade(necessidade):
    """Revalida solicitações cobertas, sem reinterpretar registros anteriores à regra."""
    processo = necessidade.processo
    if not processo.historico.filter(
        tipo__in=["COBERTURA_ESTOQUE_AVALIADA", "EXCECAO_ESTOQUE"],
        dados__necessidade_id=necessidade.pk,
    ).exists():
        return
    if processo.historico.filter(tipo="EXCECAO_ESTOQUE", dados__necessidade_id=necessidade.pk).exists():
        return
    reserva = ReservaEstoqueCompra.objects.filter(necessidade=necessidade).first()
    cobertura = obter_cobertura(
        obra=processo.obra, material=necessidade.material,
        unidade=necessidade.unidade, especificacao=necessidade.especificacao,
        quantidade=necessidade.quantidade_necessaria, processo=processo,
        excluir_reserva=reserva.pk if reserva else None,
    )
    consumido_proprio = (
        max(reserva.quantidade_original - reserva.quantidade_disponivel, ZERO)
        if reserva and reserva.status != reserva.Status.LIBERADA else ZERO
    )
    quantidade_a_atender = max(necessidade.quantidade_necessaria - consumido_proprio, ZERO)
    pendente_compra = max(quantidade_a_atender - cobertura["disponivel"], ZERO)
    if necessidade.quantidade_incluida != pendente_compra:
        raise ValidationError(
            f"A cobertura de {necessidade.descricao} mudou. Revise o estoque e a quantidade solicitada antes da aprovação."
        )
