from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from financeiro.models import AprovacaoTituloFinanceiro, Pagamento, ProgramacaoPagamento, TituloPagar
from financeiro.services.auditoria import registrar_evento


def _validar_aprovacao_vigente(titulo):
    if titulo.status != TituloPagar.Status.APROVADO or (
        titulo.ciclo_aprovacao and not titulo.aprovacoes.filter(
            ciclo=titulo.ciclo_aprovacao, decisao=AprovacaoTituloFinanceiro.Decisao.APROVADO,
        ).exists()
    ):
        raise ValidationError("O título precisa ter aprovação financeira vigente.")


@transaction.atomic
def programar_pagamento(titulo, *, data_programada, usuario, motivo=""):
    titulo = TituloPagar.objects.select_for_update().get(pk=titulo.pk)
    _validar_aprovacao_vigente(titulo)
    if titulo.esta_pago or titulo.valor_liquido <= 0:
        raise ValidationError("A programação exige uma conta aprovada e disponível para pagamento.")
    programacao = ProgramacaoPagamento.objects.filter(titulo=titulo).first()
    anterior = programacao.data_programada if programacao else None
    if programacao and programacao.ativa and programacao.ciclo_aprovacao == titulo.ciclo_aprovacao and anterior == data_programada:
        return programacao

    programacao, _ = ProgramacaoPagamento.objects.update_or_create(
        titulo=titulo,
        defaults={"data_programada": data_programada, "ciclo_aprovacao": titulo.ciclo_aprovacao, "ativa": True},
    )
    registrar_evento(titulo, "PAGAMENTO_PROGRAMADO", motivo or "Programação de pagamento registrada.", usuario, {
        "programacao_id": programacao.pk,
        "data_anterior": anterior.isoformat() if anterior else None,
        "data_nova": data_programada.isoformat(),
        "ciclo_aprovacao": titulo.ciclo_aprovacao,
    })
    return programacao


@transaction.atomic
def registrar_pagamento(*, titulo, data_pagamento=None, forma=None, usuario, comprovante=None, referencia_bancaria="", observacao=""):
    """Confirma o pagamento integral de um título exatamente uma vez."""
    titulo = TituloPagar.objects.select_for_update().get(pk=titulo.pk)

    _validar_aprovacao_vigente(titulo)

    pagamento_existente = Pagamento.objects.filter(titulo=titulo).first()
    if (pagamento_existente and pagamento_existente.status == Pagamento.Status.EFETIVADO) or titulo.status == TituloPagar.Status.PAGO:
        raise ValidationError("Este título já possui pagamento registrado.")

    data_pagamento = data_pagamento or timezone.localdate()
    forma = forma or Pagamento.Forma.OUTRO

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
    ProgramacaoPagamento.objects.filter(titulo=titulo, ativa=True).update(ativa=False)
    registrar_evento(
        titulo,
        "PAGAMENTO",
        f"Pagamento integral de R$ {valor:,.2f} registrado.",
        usuario,
        {"pagamento_id": pagamento.pk, "valor_anterior": "0.00", "valor_novo": str(valor),
         "data_pagamento": data_pagamento.isoformat(), "forma": forma,
         "comprovante": pagamento.comprovante.name or ""},
    )
    if titulo.origem == TituloPagar.Origem.GRANDE_FORNECEDOR and titulo.referencia_externa:
        try:
            from compras.models import ParcelaGrandeFornecedor, RateioParcelaGrandeFornecedor
            ref = titulo.referencia_externa
            parcela = None
            if ref.startswith("GF_RATEIO:"):
                rateio = RateioParcelaGrandeFornecedor.objects.select_related("parcela").filter(pk=ref.split(":", 1)[1]).first()
                parcela = rateio.parcela if rateio else None
            elif ref.startswith("GF_PARCELA:") or ref.startswith("GF_SALDO:"):
                parcela = ParcelaGrandeFornecedor.objects.filter(pk=ref.split(":", 1)[1]).first()
            if parcela:
                refs = [f"GF_PARCELA:{parcela.pk}", f"GF_SALDO:{parcela.pk}"] + [f"GF_RATEIO:{pk}" for pk in parcela.rateios.values_list("pk", flat=True)]
                pendentes = TituloPagar.objects.filter(referencia_externa__in=refs).exclude(status__in=[TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO]).exists()
                if not pendentes:
                    parcela.status = ParcelaGrandeFornecedor.Status.PAGO
                    parcela.save(update_fields=["status"])
        except Exception:
            # Pagamento financeiro não deve falhar por uma inconsistência de espelhamento operacional.
            pass
    return pagamento


@transaction.atomic
def estornar_pagamento(pagamento, *, usuario, motivo):
    titulo = TituloPagar.objects.select_for_update().get(pk=pagamento.titulo_id)
    pagamento = Pagamento.objects.select_for_update().get(pk=pagamento.pk)
    if pagamento.status == Pagamento.Status.ESTORNADO:
        return pagamento

    pagamento.status = Pagamento.Status.ESTORNADO
    pagamento.estornado_em = timezone.now()
    pagamento.estornado_por = usuario
    pagamento.motivo_estorno = motivo
    pagamento.save(update_fields=["status", "estornado_em", "estornado_por", "motivo_estorno"])

    titulo.status = TituloPagar.Status.APROVADO
    titulo.save(update_fields=["status", "atualizado_em"])
    registrar_evento(titulo, "ESTORNO", motivo or "Pagamento estornado.", usuario, {
        "pagamento_id": pagamento.pk, "valor_anterior": str(pagamento.valor), "valor_novo": "0.00",
        "data_pagamento": pagamento.data_pagamento.isoformat(), "forma": pagamento.forma,
        "comprovante": pagamento.comprovante.name or "", "motivo": motivo,
    })
    return pagamento
