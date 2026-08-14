from django.db import transaction

from compras.models import HistoricoNegociacaoItem, NegociacaoItem
from .auditoria import registrar_evento


@transaction.atomic
def registrar_negociacao(
    *, item_cotado, usuario, valor_unitario_negociado=None, frete_negociado=None,
    prazo_entrega_dias_negociado=None, condicao_pagamento_negociada="", observacoes=""
):
    negociacao, _ = NegociacaoItem.objects.update_or_create(
        item_cotado=item_cotado,
        defaults={
            "valor_unitario_negociado": valor_unitario_negociado,
            "frete_negociado": frete_negociado,
            "prazo_entrega_dias_negociado": prazo_entrega_dias_negociado,
            "condicao_pagamento_negociada": condicao_pagamento_negociada,
            "observacoes": observacoes,
            "atualizado_por": usuario,
        },
    )
    HistoricoNegociacaoItem.objects.create(
        item_cotado=item_cotado,
        valor_unitario_negociado=valor_unitario_negociado,
        frete_negociado=frete_negociado,
        prazo_entrega_dias_negociado=prazo_entrega_dias_negociado,
        condicao_pagamento_negociada=condicao_pagamento_negociada,
        observacoes=observacoes,
        usuario=usuario,
    )
    registrar_evento(
        item_cotado.cotacao.processo,
        "NEGOCIACAO_ITEM",
        usuario,
        f"Negociação registrada para {item_cotado.cotacao.fornecedor.nome} / {item_cotado.necessidade.descricao}.",
        {"item_cotado_id": item_cotado.pk},
    )
    return negociacao
