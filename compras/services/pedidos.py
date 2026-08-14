from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from compras.models import PedidoCompra, PedidoCompraItem, ProcessoCompra
from .auditoria import registrar_evento
from .integracao_planejamento import sincronizar_data_real
from .numeracao import gerar_numero


@transaction.atomic
def gerar_pedidos(processo, usuario, local_entrega=""):
    p = ProcessoCompra.objects.select_for_update().get(pk=processo.pk)
    if p.status not in [p.Status.APROVADO, p.Status.EM_CONTRATACAO]:
        raise ValidationError("O processo precisa estar aprovado para contratação.")

    for nec in p.necessidades.filter(situacao="ATIVA"):
        adjudicado = nec.adjudicacoes.filter(cancelada=False).aggregate(v=Sum("quantidade"))["v"] or Decimal("0")
        if adjudicado < nec.quantidade_incluida:
            raise ValidationError(f"A necessidade '{nec.descricao}' ainda possui saldo não adjudicado.")

    grupos = defaultdict(list)
    for adj in p.adjudicacoes.filter(cancelada=False).select_related("cotacao__fornecedor", "necessidade"):
        grupos[adj.cotacao.fornecedor_id].append(adj)

    if not grupos:
        raise ValidationError("Não há adjudicações para gerar pedidos.")

    criados = []
    for fornecedor_id, adjudicacoes in grupos.items():
        if p.pedidos.filter(fornecedor_id=fornecedor_id).exclude(status=PedidoCompra.Status.CANCELADO).exists():
            raise ValidationError("Já existe pedido ativo para um dos fornecedores desta contratação.")

        formalizacao = p.contratacoes.filter(fornecedor_id=fornecedor_id, cancelada=False).first()
        if not formalizacao:
            raise ValidationError("Formalize todos os fornecedores adjudicados antes de gerar os pedidos.")

        fornecedor = adjudicacoes[0].cotacao.fornecedor
        subtotal = sum((a.valor_total for a in adjudicacoes), Decimal("0"))
        pedido = PedidoCompra.objects.create(
            numero=gerar_numero("PEDIDO"),
            processo=p,
            obra=p.obra,
            fornecedor=fornecedor,
            subtotal=subtotal,
            valor_total=subtotal,
            condicao_pagamento=formalizacao.condicao_pagamento or adjudicacoes[0].condicao_pagamento_final,
            previsao_entrega_original=formalizacao.previsao_entrega,
            previsao_entrega_atual=formalizacao.previsao_entrega,
            local_entrega=formalizacao.local_entrega or local_entrega,
            responsavel=usuario,
        )
        for a in adjudicacoes:
            PedidoCompraItem.objects.create(
                pedido=pedido,
                necessidade=a.necessidade,
                descricao=a.necessidade.descricao,
                especificacao=a.necessidade.especificacao,
                unidade=a.necessidade.unidade,
                quantidade=a.quantidade,
                valor_unitario=a.valor_unitario_final,
                valor_total=a.valor_total,
            )
        criados.append(pedido)
        registrar_evento(
            p,
            "PEDIDO_CRIADO",
            usuario,
            f"Pedido {pedido.numero} criado para {fornecedor.nome}.",
            {"pedido_id": pedido.pk},
        )

    p.data_contratacao_concluida = timezone.now()
    p.status = p.Status.CONTRATADO
    p.etapa_atual = p.Etapa.CONTRATADO
    p.save(update_fields=["data_contratacao_concluida", "status", "etapa_atual", "atualizado_em"])
    sincronizar_data_real(p, "CONTRATACAO", usuario)
    registrar_evento(p, "CONTRATACAO_CONCLUIDA", usuario, "Contratação concluída e pedidos gerados.")
    return criados
