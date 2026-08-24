from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from compras.models import SolicitacaoCotacaoFornecedor
from .auditoria import registrar_evento


@transaction.atomic
def garantir_solicitacao(*, processo, fornecedor):
    solicitacao, _ = SolicitacaoCotacaoFornecedor.objects.get_or_create(
        processo=processo,
        fornecedor=fornecedor,
    )
    return solicitacao


@transaction.atomic
def marcar_solicitacao_enviada(*, solicitacao, usuario, meio_envio="", observacao=""):
    processo = solicitacao.processo

    if processo.etapa_atual not in {
        processo.Etapa.COTACAO,
        processo.Etapa.COMPATIBILIZACAO,
        processo.Etapa.NEGOCIACAO,
    }:
        raise ValidationError(
            "O mapa comercial já foi fechado e não permite novos envios de solicitação de cotação."
        )
    if processo.status in {
        processo.Status.CANCELADO,
        processo.Status.REPROVADO,
        processo.Status.AGUARDANDO_APROVACAO,
        processo.Status.APROVADO,
        processo.Status.EM_CONTRATACAO,
        processo.Status.CONTRATADO,
    }:
        raise ValidationError("Este processo não permite novos envios de solicitação de cotação.")

    if solicitacao.status == SolicitacaoCotacaoFornecedor.Status.RESPONDIDA:
        raise ValidationError("Este fornecedor já possui proposta recebida.")

    if meio_envio and meio_envio not in SolicitacaoCotacaoFornecedor.MeioEnvio.values:
        raise ValidationError("Forma de envio inválida.")

    solicitacao.status = SolicitacaoCotacaoFornecedor.Status.ENVIADA
    solicitacao.meio_envio = meio_envio or ""
    solicitacao.observacao_envio = (observacao or "").strip()
    solicitacao.enviada_em = timezone.now()
    solicitacao.enviada_por = usuario
    solicitacao.save(
        update_fields=[
            "status",
            "meio_envio",
            "observacao_envio",
            "enviada_em",
            "enviada_por",
            "atualizado_em",
        ]
    )

    registrar_evento(
        processo,
        "SOLICITACAO_COTACAO_ENVIADA_FORNECEDOR",
        usuario,
        f"Solicitação de cotação enviada para {solicitacao.fornecedor.nome}.",
        {
            "solicitacao_id": solicitacao.pk,
            "fornecedor_id": solicitacao.fornecedor_id,
            "meio_envio": solicitacao.meio_envio,
        },
    )
    return solicitacao


@transaction.atomic
def marcar_solicitacao_respondida(*, processo, fornecedor, usuario=None, data=None):
    solicitacao = garantir_solicitacao(processo=processo, fornecedor=fornecedor)
    if solicitacao.status != SolicitacaoCotacaoFornecedor.Status.RESPONDIDA:
        solicitacao.status = SolicitacaoCotacaoFornecedor.Status.RESPONDIDA
        solicitacao.respondida_em = data or timezone.now()
        solicitacao.save(update_fields=["status", "respondida_em", "atualizado_em"])
    return solicitacao


@transaction.atomic
def restaurar_solicitacao_apos_exclusao_proposta(*, processo, fornecedor):
    solicitacao = garantir_solicitacao(processo=processo, fornecedor=fornecedor)
    solicitacao.respondida_em = None
    solicitacao.status = (
        SolicitacaoCotacaoFornecedor.Status.ENVIADA
        if solicitacao.enviada_em
        else SolicitacaoCotacaoFornecedor.Status.PENDENTE_ENVIO
    )
    solicitacao.save(update_fields=["status", "respondida_em", "atualizado_em"])
    return solicitacao
