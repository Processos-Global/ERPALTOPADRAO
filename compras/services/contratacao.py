from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from compras.models import ContratacaoCompra
from .auditoria import registrar_evento


@transaction.atomic
def formalizar_fornecedor(
    *, processo, fornecedor, usuario, tipo_formalizacao, condicao_pagamento="",
    prazo_entrega_dias=None, previsao_entrega=None, local_entrega="",
    referencia_contrato="", documento=None, observacoes=""
):
    if processo.status not in [processo.Status.APROVADO, processo.Status.EM_CONTRATACAO]:
        raise ValidationError("O processo precisa estar aprovado antes da formalização.")
    adjudicacoes = processo.adjudicacoes.filter(
        cancelada=False,
        cotacao__fornecedor=fornecedor,
    )
    if not adjudicacoes.exists():
        raise ValidationError("Este fornecedor não possui itens adjudicados no processo.")
    processo.status = processo.Status.EM_CONTRATACAO
    processo.etapa_atual = processo.Etapa.CONTRATACAO
    processo.save(update_fields=["status", "etapa_atual", "atualizado_em"])

    contratacao, criada = ContratacaoCompra.objects.get_or_create(
        processo=processo,
        fornecedor=fornecedor,
        cancelada=False,
        defaults={
            "tipo_formalizacao": tipo_formalizacao,
            "condicao_pagamento": condicao_pagamento,
            "prazo_entrega_dias": prazo_entrega_dias,
            "previsao_entrega": previsao_entrega,
            "local_entrega": local_entrega,
            "referencia_contrato": referencia_contrato,
            "documento": documento,
            "observacoes": observacoes,
            "formalizado_por": usuario,
        },
    )
    if not criada:
        raise ValidationError("Já existe formalização ativa para este fornecedor.")
    registrar_evento(
        processo,
        "CONTRATACAO_FORMALIZADA",
        usuario,
        f"Formalização registrada para {fornecedor.nome}.",
        {"contratacao_id": contratacao.pk},
    )
    return contratacao
