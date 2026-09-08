from django.core.exceptions import ValidationError
from django.db import transaction

from financeiro.models import AprovacaoTituloFinanceiro, TituloPagar
from financeiro.services.auditoria import registrar_evento


@transaction.atomic
def enviar_para_aprovacao(titulo, *, usuario):
    if not titulo.vencimento:
        raise ValidationError("Informe o vencimento antes de enviar para aprovação.")
    if titulo.conferencia == TituloPagar.Conferencia.DIVERGENCIA:
        raise ValidationError("Resolva ou justifique a divergência antes da aprovação.")
    if titulo.status in {TituloPagar.Status.PAGO, TituloPagar.Status.CANCELADO}:
        raise ValidationError("Este título não pode ser enviado para aprovação.")

    titulo.ciclo_aprovacao += 1
    titulo.status = TituloPagar.Status.AGUARDANDO_APROVACAO
    titulo.save(update_fields=["ciclo_aprovacao", "status", "atualizado_em"])
    registrar_evento(titulo, "ENVIADO_APROVACAO", "Título enviado para aprovação financeira.", usuario)
    return titulo


@transaction.atomic
def decidir_titulo(titulo, *, usuario, decisao, observacao=""):
    if titulo.status != TituloPagar.Status.AGUARDANDO_APROVACAO:
        raise ValidationError("O título não está aguardando aprovação.")

    if titulo.aprovacoes.filter(ciclo=titulo.ciclo_aprovacao).exists():
        raise ValidationError("Este ciclo de aprovação já possui uma decisão registrada.")

    if decisao not in {
        AprovacaoTituloFinanceiro.Decisao.APROVADO,
        AprovacaoTituloFinanceiro.Decisao.REJEITADO,
    }:
        raise ValidationError("Decisão de aprovação inválida.")

    AprovacaoTituloFinanceiro.objects.create(
        titulo=titulo,
        ciclo=titulo.ciclo_aprovacao,
        usuario=usuario,
        decisao=decisao,
        observacao=observacao,
    )

    if decisao == AprovacaoTituloFinanceiro.Decisao.REJEITADO:
        titulo.status = TituloPagar.Status.REJEITADO
        evento = "REJEITADO"
        descricao = observacao or "Pagamento rejeitado."
    else:
        titulo.status = TituloPagar.Status.APROVADO
        evento = "APROVADO"
        descricao = observacao or "Pagamento aprovado."

    titulo.save(update_fields=["status", "atualizado_em"])
    registrar_evento(titulo, evento, descricao, usuario)
    return titulo
