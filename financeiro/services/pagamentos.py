from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from financeiro.models import Pagamento, TituloPagar
from financeiro.services.auditoria import registrar_evento


@transaction.atomic
def registrar_pagamento(*, titulo, data_pagamento, forma, usuario, comprovante=None, referencia_bancaria="", observacao=""):
    """Confirma o pagamento integral de um título exatamente uma vez."""
    titulo = TituloPagar.objects.select_for_update().get(pk=titulo.pk)

    if titulo.status != TituloPagar.Status.APROVADO:
        raise ValidationError("O título precisa estar aprovado antes do pagamento.")

    pagamento_existente = Pagamento.objects.filter(titulo=titulo).first()
    if (pagamento_existente and pagamento_existente.status == Pagamento.Status.EFETIVADO) or titulo.status == TituloPagar.Status.PAGO:
        raise ValidationError("Este título já possui pagamento registrado.")

    valor = titulo.valor_liquido
    if valor <= 0:
        raise ValidationError("O título não possui valor válido para pagamento.")

    if pagamento_existente and pagamento_existente.status == Pagamento.Status.ESTORNADO:
        pagamento = pagamento_existente
        pagamento.data_pagamento = data_pagamento
        pagamento.valor = valor
        pagamento.forma = forma
        if comprovante:
            pagamento.comprovante = comprovante
        pagamento.referencia_bancaria = referencia_bancaria
        pagamento.observacao = observacao
        pagamento.registrado_por = usuario
        pagamento.status = Pagamento.Status.EFETIVADO
        pagamento.estornado_em = None
        pagamento.estornado_por = None
        pagamento.motivo_estorno = ""
        pagamento.save()
    else:
        pagamento = Pagamento.objects.create(
            titulo=titulo,
            data_pagamento=data_pagamento,
            valor=valor,
            forma=forma,
            comprovante=comprovante,
            referencia_bancaria=referencia_bancaria,
            observacao=observacao,
            registrado_por=usuario,
        )

    titulo.status = TituloPagar.Status.PAGO
    titulo.save(update_fields=["status", "atualizado_em"])
    registrar_evento(
        titulo,
        "PAGAMENTO",
        f"Pagamento integral de R$ {valor:,.2f} registrado.",
        usuario,
        {"pagamento_id": pagamento.pk},
    )
    return pagamento


@transaction.atomic
def estornar_pagamento(pagamento, *, usuario, motivo):
    if pagamento.status == Pagamento.Status.ESTORNADO:
        return pagamento

    pagamento.status = Pagamento.Status.ESTORNADO
    pagamento.estornado_em = timezone.now()
    pagamento.estornado_por = usuario
    pagamento.motivo_estorno = motivo
    pagamento.save(update_fields=["status", "estornado_em", "estornado_por", "motivo_estorno"])

    titulo = pagamento.titulo
    titulo.status = TituloPagar.Status.APROVADO
    titulo.save(update_fields=["status", "atualizado_em"])
    registrar_evento(titulo, "ESTORNO", motivo or "Pagamento estornado.", usuario, {"pagamento_id": pagamento.pk})
    return pagamento
