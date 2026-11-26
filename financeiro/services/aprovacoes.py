from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse

from compras.models import ParcelaPrevistaPedido
from financeiro.models import AprovacaoTituloFinanceiro, LiberacaoFinanceiraPedido, TituloPagar
from financeiro.services.agenda import _inteiro_positivo
from financeiro.services.auditoria import registrar_evento
from financeiro.services.notificacoes import notificar_aprovadores
from financeiro.services.permissoes import possui_acao_financeiro
from financeiro.services.titulos import bloquear_titulo
from usuarios.models import TipoNotificacao
from usuarios.services.notificacoes import criar_notificacao


class CicloAprovacaoDesatualizado(ValidationError):
    pass


def interpretar_ciclo(valor):
    texto = str(valor if valor is not None else "")
    if not (texto.isascii() and texto.isdecimal() and len(texto) <= 10):
        return None
    ciclo = int(texto)
    return ciclo if ciclo <= 2**31 - 1 else None


def titulo_tem_divergencia(titulo, liberacao):
    return titulo.conferencia == TituloPagar.Conferencia.DIVERGENCIA or bool(
        liberacao and liberacao.divergencias_comerciais,
    )


def previsao_aguarda_recebimento(titulo):
    if (
        titulo.status != TituloPagar.Status.PREVISTA
        or titulo.origem != TituloPagar.Origem.COMPRA
        or titulo.recebimento_id
    ):
        return False
    prefixo, _, referencia = (titulo.referencia_externa or "").partition(":")
    if prefixo not in {"COMPRA_PEDIDO", "COMPRA_PARCELA"}:
        return False
    if titulo.pedido_id and titulo.pedido.processo.fluxo_grande_fornecedor:
        return False
    if prefixo == "COMPRA_PARCELA" and titulo.pedido_id:
        gatilho = ParcelaPrevistaPedido.Gatilho
        return not titulo.pedido.parcelas_previstas.filter(
            pk=_inteiro_positivo(referencia),
            evento_gatilho__in=(gatilho.ASSINATURA, gatilho.FABRICACAO, gatilho.INSTALACAO),
        ).exists()
    return True


def validar_origem_para_aprovacao(titulo, liberacao):
    if not titulo.recebimento_id:
        return
    if titulo.recebimento.pedido_id != titulo.pedido_id or titulo.pedido.obra_id != titulo.obra_id:
        raise ValidationError("O recebimento, o pedido e a obra da conta não correspondem.")
    if liberacao and liberacao.valor_esperado is not None:
        if liberacao.status != LiberacaoFinanceiraPedido.Status.AUTORIZADA:
            raise ValidationError("Conclua a conferência fiscal do recebimento antes de encaminhar a conta.")
        if not titulo.vencimento or not titulo.plano_financeiro_id:
            raise ValidationError("Defina o vencimento e a apropriação antes da aprovação.")


def _notificar_solicitante(titulo, evento, descricao):
    if not titulo.criado_por_id or not titulo.criado_por.is_active:
        return
    correcao = evento == "CORRECAO_SOLICITADA"
    criar_notificacao(
        usuario=titulo.criado_por,
        titulo="Correção solicitada" if correcao else "Conta a Pagar reprovada",
        mensagem=f"{titulo.numero} · {descricao}"[:500],
        modulo="FINANCEIRO",
        tipo=TipoNotificacao.ACAO if correcao else TipoNotificacao.ATENCAO,
        evento=f"FINANCEIRO_{evento}",
        url=reverse("financeiro:titulo_detalhe", args=[titulo.pk]),
        chave_unica=f"financeiro:decisao:{titulo.pk}:ciclo:{titulo.ciclo_aprovacao}",
        dados={"titulo_id": titulo.pk, "ciclo": titulo.ciclo_aprovacao},
    )


@transaction.atomic
def enviar_para_aprovacao(titulo, *, usuario):
    titulo, liberacao = bloquear_titulo(titulo)
    if titulo.status in {TituloPagar.Status.AGUARDANDO_APROVACAO, TituloPagar.Status.APROVADO}:
        return titulo
    if previsao_aguarda_recebimento(titulo):
        raise ValidationError("Aguarde o recebimento de Compras para encaminhar a solicitação financeira.")
    validar_origem_para_aprovacao(titulo, liberacao)
    if not titulo.vencimento:
        raise ValidationError("Informe o vencimento antes de enviar para aprovação.")
    if not (titulo.especificacao_pagamento or "").strip():
        raise ValidationError("Informe o que está sendo pago antes de enviar para aprovação.")
    if not titulo.plano_financeiro_id:
        raise ValidationError("Defina a apropriação financeira antes de enviar para aprovação.")
    if not titulo.beneficiario_exibicao or titulo.beneficiario_exibicao == "Beneficiário não definido":
        raise ValidationError("Defina o beneficiário antes de enviar para aprovação.")
    if titulo.esta_pago or titulo.status == TituloPagar.Status.CANCELADO:
        raise ValidationError("Esta Conta a Pagar não pode ser enviada para aprovação.")

    titulo.ciclo_aprovacao += 1
    titulo.status = TituloPagar.Status.AGUARDANDO_APROVACAO
    titulo.save(update_fields=["ciclo_aprovacao", "status", "atualizado_em"])
    registrar_evento(titulo, "ENVIADO_APROVACAO", "Conta a Pagar enviada para aprovação.", usuario)
    notificar_aprovadores(titulo)
    return titulo


@transaction.atomic
def decidir_titulo(titulo, *, usuario, decisao, ciclo_esperado, observacao="", ciencia_divergencia=False, em_lote=False):
    if not possui_acao_financeiro(usuario, "APROVAR"):
        raise PermissionDenied("Permissão financeira de aprovação necessária.")
    titulo, liberacao = bloquear_titulo(titulo)
    if ciclo_esperado != titulo.ciclo_aprovacao:
        raise CicloAprovacaoDesatualizado("A análise está desatualizada. Atualize a página e confira os dados do ciclo vigente.")
    if titulo.status != TituloPagar.Status.AGUARDANDO_APROVACAO or titulo.esta_pago:
        raise ValidationError("A Conta a Pagar não está aguardando aprovação.")

    if titulo.aprovacoes.filter(ciclo=titulo.ciclo_aprovacao).exists():
        raise ValidationError("Este ciclo de aprovação já possui uma decisão registrada.")

    if decisao not in AprovacaoTituloFinanceiro.Decisao.values:
        raise ValidationError("Decisão de aprovação inválida.")

    observacao = (observacao or "").strip()
    if len(observacao) > 500:
        raise ValidationError("A justificativa deve ter no máximo 500 caracteres.")
    divergente = titulo_tem_divergencia(titulo, liberacao)
    if decisao == AprovacaoTituloFinanceiro.Decisao.APROVADO:
        validar_origem_para_aprovacao(titulo, liberacao)
        if divergente and em_lote:
            raise ValidationError("A divergência requer análise individual.")
        if divergente and (not ciencia_divergencia or not observacao):
            raise ValidationError("Confirme a ciência da divergência e informe uma justificativa para aprovar.")
    if decisao == AprovacaoTituloFinanceiro.Decisao.CORRECAO_SOLICITADA and not observacao:
        raise ValidationError("Informe o que precisa ser corrigido.")

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
        descricao = observacao or "Conta a Pagar reprovada."
    elif decisao == AprovacaoTituloFinanceiro.Decisao.CORRECAO_SOLICITADA:
        titulo.status = TituloPagar.Status.CORRECAO_SOLICITADA
        evento = "CORRECAO_SOLICITADA"
        descricao = observacao
    else:
        titulo.status = TituloPagar.Status.APROVADO
        evento = "APROVADO"
        descricao = observacao or "Conta a Pagar aprovada."

    titulo.save(update_fields=["status", "atualizado_em"])
    registrar_evento(titulo, evento, descricao, usuario, {
        "ciclo": titulo.ciclo_aprovacao,
        "ciencia_divergencia": bool(divergente and ciencia_divergencia and evento == "APROVADO"),
    })
    if evento != "APROVADO":
        _notificar_solicitante(titulo, evento, descricao)
    return titulo
