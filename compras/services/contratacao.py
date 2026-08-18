from django.core.exceptions import ValidationError
from django.db import transaction

from compras.models import ContratacaoCompra, PedidoCompra
from .auditoria import registrar_evento


@transaction.atomic
def formalizar_fornecedor(
    *, processo, fornecedor, usuario, tipo_formalizacao, condicao_pagamento="",
    prazo_entrega_dias=None, previsao_entrega=None, local_entrega="",
    referencia_contrato="", documento=None, observacoes=""
):
    """Registra/atualiza a formalização sem alterar a etapa comercial do processo."""
    if processo.status not in {
        processo.Status.APROVADO,
        processo.Status.EM_CONTRATACAO,
        processo.Status.CONTRATADO,
    }:
        raise ValidationError("O processo precisa estar aprovado antes da formalização.")

    if not processo.adjudicacoes.filter(cancelada=False, cotacao__fornecedor=fornecedor).exists():
        raise ValidationError("Este fornecedor não possui itens adjudicados no processo.")

    contratacao = processo.contratacoes.filter(fornecedor=fornecedor, cancelada=False).first()
    dados = {
        "tipo_formalizacao": tipo_formalizacao,
        "condicao_pagamento": condicao_pagamento,
        "prazo_entrega_dias": prazo_entrega_dias,
        "previsao_entrega": previsao_entrega,
        "local_entrega": local_entrega,
        "referencia_contrato": referencia_contrato,
        "observacoes": observacoes,
        "formalizado_por": usuario,
    }
    if documento is not None:
        dados["documento"] = documento

    if contratacao:
        for campo, valor in dados.items():
            setattr(contratacao, campo, valor)
        contratacao.save()
    else:
        contratacao = ContratacaoCompra.objects.create(
            processo=processo,
            fornecedor=fornecedor,
            **dados,
        )

    # Se o pedido já foi gerado, sincroniza os metadados operacionais.
    pedido = processo.pedidos.filter(fornecedor=fornecedor).exclude(status=PedidoCompra.Status.CANCELADO).first()
    if pedido:
        campos = []
        if condicao_pagamento:
            pedido.condicao_pagamento = condicao_pagamento
            campos.append("condicao_pagamento")
        if previsao_entrega:
            if pedido.previsao_entrega_original is None:
                pedido.previsao_entrega_original = previsao_entrega
                campos.append("previsao_entrega_original")
            pedido.previsao_entrega_atual = previsao_entrega
            campos.append("previsao_entrega_atual")
        if local_entrega:
            pedido.local_entrega = local_entrega
            campos.append("local_entrega")
        if campos:
            pedido.save(update_fields=[*set(campos), "atualizado_em"])

    registrar_evento(
        processo,
        "CONTRATACAO_FORMALIZADA",
        usuario,
        f"Formalização registrada/atualizada para {fornecedor.nome}.",
        {"contratacao_id": contratacao.pk},
    )
    return contratacao


@transaction.atomic
def anexar_documento_fornecedor(*, processo, fornecedor, usuario, documento):
    """Anexa ou substitui somente o documento complementar do fornecedor."""
    if processo.status not in {
        processo.Status.APROVADO,
        processo.Status.EM_CONTRATACAO,
        processo.Status.CONTRATADO,
    }:
        raise ValidationError("O processo precisa estar aprovado antes de anexar documentos.")

    if not documento:
        raise ValidationError("Selecione um documento para anexar.")

    if not processo.adjudicacoes.filter(
        cancelada=False,
        cotacao__fornecedor=fornecedor,
    ).exists():
        raise ValidationError("Este fornecedor não possui itens adjudicados no processo.")

    contratacao, _ = ContratacaoCompra.objects.get_or_create(
        processo=processo,
        fornecedor=fornecedor,
        cancelada=False,
        defaults={
            "tipo_formalizacao": ContratacaoCompra.TipoFormalizacao.PEDIDO,
            "formalizado_por": usuario,
        },
    )
    contratacao.documento = documento
    contratacao.formalizado_por = usuario
    contratacao.save(update_fields=["documento", "formalizado_por"])

    registrar_evento(
        processo,
        "DOCUMENTO_CONTRATACAO_ANEXADO",
        usuario,
        f"Documento complementar anexado para {fornecedor.nome}.",
        {"contratacao_id": contratacao.pk},
    )
    return contratacao
