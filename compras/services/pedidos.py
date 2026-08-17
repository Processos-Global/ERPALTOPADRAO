from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from compras.models import (
    HistoricoPrevisaoPedido,
    PedidoCompra,
    PedidoCompraItem,
    ProcessoCompra,
    RecebimentoPedido,
    RecebimentoPedidoItem,
)

from .auditoria import registrar_evento
from .comercial import (
    condicao_pagamento_final_fornecedor,
    frete_final_fornecedor,
    prazo_final_fornecedor,
    quantizar_moeda,
)
from .integracao_planejamento import sincronizar_data_real
from .numeracao import gerar_numero

ZERO = Decimal("0")


def _previsao_por_prazo(prazo_dias):
    if prazo_dias is None:
        return None
    return timezone.localdate() + timedelta(days=int(prazo_dias))


@transaction.atomic
def gerar_pedidos(processo, usuario, local_entrega=""):
    """
    Gera um pedido por fornecedor adjudicado.

    A operação é idempotente: se já existir pedido ativo para determinado
    fornecedor/processo, ele é reutilizado e não é duplicado.
    Formalização contratual é opcional e, quando existir, prevalece nos campos
    de condição/prazo/local.
    """
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.status not in {p.Status.APROVADO, p.Status.EM_CONTRATACAO, p.Status.CONTRATADO}:
        raise ValidationError("O processo precisa estar aprovado para gerar pedidos.")

    adjudicacoes = list(
        p.adjudicacoes
        .filter(cancelada=False)
        .select_related("cotacao__fornecedor", "necessidade", "item_cotado")
        .order_by("cotacao__fornecedor_id", "id")
    )
    if not adjudicacoes:
        raise ValidationError("Não existem itens adjudicados para gerar pedidos.")

    grupos = defaultdict(list)
    for adjudicacao in adjudicacoes:
        grupos[adjudicacao.cotacao.fornecedor_id].append(adjudicacao)

    pedidos_resultado = []
    for fornecedor_id, grupo in grupos.items():
        existente = (
            PedidoCompra.objects
            .filter(processo=p, fornecedor_id=fornecedor_id)
            .exclude(status=PedidoCompra.Status.CANCELADO)
            .first()
        )
        if existente:
            pedidos_resultado.append(existente)
            continue

        fornecedor = grupo[0].cotacao.fornecedor
        formalizacao = p.contratacoes.filter(fornecedor_id=fornecedor_id, cancelada=False).first()

        subtotal = quantizar_moeda(sum((a.valor_bruto for a in grupo), ZERO))
        descontos = quantizar_moeda(sum((a.desconto_final or ZERO for a in grupo), ZERO))
        frete = frete_final_fornecedor(p, fornecedor_id)
        total = quantizar_moeda(max(subtotal - descontos + frete, ZERO))

        condicao = (
            (formalizacao.condicao_pagamento or "").strip()
            if formalizacao
            else ""
        ) or condicao_pagamento_final_fornecedor(p, fornecedor_id)

        prazo = formalizacao.prazo_entrega_dias if formalizacao else prazo_final_fornecedor(p, fornecedor_id)
        previsao = formalizacao.previsao_entrega if formalizacao else _previsao_por_prazo(prazo)
        destino = ((formalizacao.local_entrega or "").strip() if formalizacao else "") or (local_entrega or "").strip()

        pedido = PedidoCompra.objects.create(
            numero=gerar_numero("PEDIDO"),
            processo=p,
            obra=p.obra,
            fornecedor=fornecedor,
            subtotal=subtotal,
            descontos=descontos,
            frete=frete,
            valor_total=total,
            condicao_pagamento=condicao,
            previsao_entrega_original=previsao,
            previsao_entrega_atual=previsao,
            local_entrega=destino,
            responsavel=usuario,
        )

        PedidoCompraItem.objects.bulk_create([
            PedidoCompraItem(
                pedido=pedido,
                necessidade=a.necessidade,
                descricao=a.necessidade.descricao,
                especificacao=a.necessidade.especificacao,
                unidade=a.necessidade.unidade,
                quantidade=a.quantidade,
                valor_unitario=a.valor_unitario_final,
                desconto=a.desconto_final or ZERO,
                valor_total=quantizar_moeda(a.valor_total),
            )
            for a in grupo
        ])
        pedidos_resultado.append(pedido)
        registrar_evento(
            p,
            "PEDIDO_CRIADO",
            usuario,
            f"Pedido {pedido.numero} criado para {fornecedor.nome}.",
            {"pedido_id": pedido.pk, "valor_total": str(total)},
        )

    # Só encerra depois que todos os fornecedores possuem pedido ativo.
    fornecedores_com_pedido = set(
        p.pedidos.exclude(status=PedidoCompra.Status.CANCELADO).values_list("fornecedor_id", flat=True)
    )
    if set(grupos) <= fornecedores_com_pedido:
        p.status = p.Status.CONTRATADO
        p.etapa_atual = p.Etapa.CONTRATADO
        if not p.data_contratacao_concluida:
            p.data_contratacao_concluida = timezone.now()
        p.save(update_fields=["status", "etapa_atual", "data_contratacao_concluida", "atualizado_em"])
        sincronizar_data_real(p, "CONTRATACAO", usuario)
        registrar_evento(p, "CONTRATACAO_CONCLUIDA", usuario, "Pedidos gerados e processo comercial concluído.")

    return pedidos_resultado


TRANSICOES_STATUS = {
    PedidoCompra.Status.PEDIDO_EMITIDO: {PedidoCompra.Status.CONFIRMADO, PedidoCompra.Status.CANCELADO},
    PedidoCompra.Status.CONFIRMADO: {PedidoCompra.Status.EM_PRODUCAO, PedidoCompra.Status.PRONTO_EXPEDICAO, PedidoCompra.Status.EM_TRANSPORTE, PedidoCompra.Status.CANCELADO},
    PedidoCompra.Status.EM_PRODUCAO: {PedidoCompra.Status.PRONTO_EXPEDICAO, PedidoCompra.Status.EM_TRANSPORTE, PedidoCompra.Status.CANCELADO},
    PedidoCompra.Status.PRONTO_EXPEDICAO: {PedidoCompra.Status.EM_TRANSPORTE, PedidoCompra.Status.CANCELADO},
    PedidoCompra.Status.EM_TRANSPORTE: {PedidoCompra.Status.ENTREGA_PARCIAL, PedidoCompra.Status.ENTREGUE, PedidoCompra.Status.CANCELADO},
    PedidoCompra.Status.ENTREGA_PARCIAL: {PedidoCompra.Status.EM_TRANSPORTE, PedidoCompra.Status.ENTREGUE, PedidoCompra.Status.CANCELADO},
    PedidoCompra.Status.ENTREGUE: set(),
    PedidoCompra.Status.CANCELADO: set(),
}


@transaction.atomic
def atualizar_status_pedido(*, pedido, novo_status, usuario, observacao=""):
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    if novo_status not in PedidoCompra.Status.values:
        raise ValidationError("Status de pedido inválido.")
    if novo_status not in TRANSICOES_STATUS.get(p.status, set()):
        raise ValidationError(f"Não é permitido alterar de {p.get_status_display()} para {PedidoCompra.Status(novo_status).label}.")
    if novo_status == PedidoCompra.Status.CANCELADO:
        return cancelar_pedido(pedido=p, usuario=usuario, motivo=observacao)
    p.status = novo_status
    p.save(update_fields=["status", "atualizado_em"])
    registrar_evento(p.processo, "STATUS_PEDIDO", usuario, f"Pedido {p.numero}: {p.get_status_display()}.", {"pedido_id": p.pk})
    return p


@transaction.atomic
def atualizar_previsao_entrega(*, pedido, previsao_nova, usuario, motivo=""):
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    if p.status in {PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE}:
        raise ValidationError("A previsão não pode ser alterada neste status.")
    if not previsao_nova:
        raise ValidationError("Informe a nova previsão de entrega.")
    anterior = p.previsao_entrega_atual
    HistoricoPrevisaoPedido.objects.create(
        pedido=p,
        previsao_anterior=anterior,
        previsao_nova=previsao_nova,
        motivo=(motivo or "").strip(),
        alterado_por=usuario,
    )
    if p.previsao_entrega_original is None:
        p.previsao_entrega_original = previsao_nova
    p.previsao_entrega_atual = previsao_nova
    p.save(update_fields=["previsao_entrega_original", "previsao_entrega_atual", "atualizado_em"])
    registrar_evento(p.processo, "PREVISAO_PEDIDO", usuario, f"Previsão do pedido {p.numero} alterada para {previsao_nova:%d/%m/%Y}.")
    return p


@transaction.atomic
def registrar_recebimento(*, pedido, quantidades, usuario, observacao=""):
    """quantidades: dict {pedido_item_id: quantidade_recebida_nesta_entrega}."""
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    if p.status in {PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE}:
        raise ValidationError("Este pedido não aceita novos recebimentos.")

    recebimento = RecebimentoPedido.objects.create(pedido=p, usuario=usuario, observacao=(observacao or "").strip())
    houve = False
    for item in p.itens.select_for_update().all():
        quantidade = Decimal(str(quantidades.get(item.pk, ZERO) or ZERO))
        if quantidade < 0:
            raise ValidationError("Quantidade recebida não pode ser negativa.")
        if quantidade == 0:
            continue
        if quantidade > item.saldo_receber:
            raise ValidationError(f"Recebimento de {item.descricao} excede o saldo de {item.saldo_receber} {item.unidade}.")
        item.quantidade_recebida += quantidade
        item.save(update_fields=["quantidade_recebida"])
        RecebimentoPedidoItem.objects.create(recebimento=recebimento, item_pedido=item, quantidade=quantidade)
        houve = True

    if not houve:
        raise ValidationError("Informe ao menos uma quantidade recebida maior que zero.")

    completo = not p.itens.filter(quantidade_recebida__lt=models.F("quantidade")).exists()
    if completo:
        p.status = PedidoCompra.Status.ENTREGUE
        p.recebido_em = timezone.now()
        p.recebido_por = usuario
        p.save(update_fields=["status", "recebido_em", "recebido_por", "atualizado_em"])
    else:
        p.status = PedidoCompra.Status.ENTREGA_PARCIAL
        p.save(update_fields=["status", "atualizado_em"])

    registrar_evento(p.processo, "RECEBIMENTO_PEDIDO", usuario, f"Recebimento registrado no pedido {p.numero}.", {"pedido_id": p.pk, "recebimento_id": recebimento.pk})
    return recebimento


@transaction.atomic
def cancelar_pedido(*, pedido, usuario, motivo):
    p = PedidoCompra.objects.select_for_update().get(pk=pedido.pk)
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento do pedido.")
    if p.status == PedidoCompra.Status.ENTREGUE:
        raise ValidationError("Pedido entregue não pode ser cancelado.")
    if p.status == PedidoCompra.Status.CANCELADO:
        return p
    p.status = PedidoCompra.Status.CANCELADO
    p.cancelado_por = usuario
    p.cancelado_em = timezone.now()
    p.motivo_cancelamento = motivo
    p.save(update_fields=["status", "cancelado_por", "cancelado_em", "motivo_cancelamento", "atualizado_em"])
    registrar_evento(p.processo, "PEDIDO_CANCELADO", usuario, f"Pedido {p.numero} cancelado: {motivo}", {"pedido_id": p.pk})
    return p
