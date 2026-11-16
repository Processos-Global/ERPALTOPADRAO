"""Notificações internas (sininho do ERP) da concretagem."""
import logging

from django.contrib.auth import get_user_model
from django.urls import reverse

from usuarios.models import ModuloNotificacao, ModuloSistema, PermissaoAcao, TipoNotificacao
from usuarios.services.notificacoes import criar_notificacao

from .permissoes import ACAO_CONCRETAGEM

logger = logging.getLogger(__name__)


def gerentes():
    """Quem tem a permissão Concretagem (não há mais gerente separado)."""
    ids = PermissaoAcao.objects.filter(
        modulo=ModuloSistema.OBRAS, acao=ACAO_CONCRETAGEM, permitido=True,
    ).values_list("usuario_id", flat=True)
    return get_user_model().objects.filter(pk__in=ids, is_active=True)


def _notificar(usuarios, conc, titulo, mensagem, evento, tipo=TipoNotificacao.INFORMACAO):
    url = reverse("obras:concretagem_detalhe", args=[conc.pk])
    vistos = set()
    for usuario in usuarios:
        if usuario is None or usuario.pk in vistos or not usuario.is_active:
            continue
        vistos.add(usuario.pk)
        try:
            criar_notificacao(
                usuario=usuario, titulo=titulo[:160], mensagem=mensagem[:500],
                modulo=ModuloNotificacao.SISTEMA, tipo=tipo, evento=evento, url=url,
                chave_unica=f"{evento}:{conc.pk}",
            )
        except Exception:
            logger.exception("Falha ao notificar usuário %s sobre %s", usuario.pk, conc.codigo)


def responsaveis(conc):
    return [u for u in (conc.engenheiro, conc.criado_por) if u is not None]


def solicitacao_enviada(conc):
    _notificar(
        gerentes(), conc,
        f"Concretagem {conc.codigo} aguardando a concreteira",
        f"{conc.obra.nome}: solicitação enviada. Se a concreteira confirmar por fora do link, "
        "aceite manualmente na concretagem.",
        "concretagem.solicitada",
    )


def resposta_concreteira(conc, request=None):
    """Sininho para engenheiro/criador; no aceite, também e-mail ao engenheiro responsável."""
    if conc.confirmacao_cliente == "ACEITO":
        from .mensagem import enviar_email_aceite
        enviar_email_aceite(conc, request)
    resposta = conc.get_confirmacao_cliente_display() or "respondeu"
    tipo = TipoNotificacao.SUCESSO if conc.confirmacao_cliente == "ACEITO" else TipoNotificacao.ATENCAO
    _notificar(
        responsaveis(conc), conc,
        f"Concretagem {conc.codigo}: {resposta.lower()}",
        f"{conc.obra.nome}: a concreteira {resposta.lower()} a solicitação.",
        "concretagem.resposta", tipo=tipo,
    )
