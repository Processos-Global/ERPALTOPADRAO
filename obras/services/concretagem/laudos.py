"""Laudos de resistência e alerta de reprovação.

Aprovação: resistência >= fck de projeto x percentual da idade
(7 dias 60%, 14 dias 71,7%, 28 dias 95% — `obras.models.LIMITES_FCK`).
Um laudo por idade: relançar a mesma idade atualiza o existente.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from obras.models import Concretagem, LaudoConcretagem
from usuarios.models import TipoNotificacao

from . import drive, notificacoes
from .fluxo import A, FluxoError, registrar_historico
from .mensagem import url_absoluta

logger = logging.getLogger(__name__)
S = Concretagem.Status
IDADES_INTERMEDIARIAS = (7, 14)


def pode_lancar(conc):
    return conc.status == S.AGUARDANDO_LAUDOS


def laudos_por_idade(conc):
    return {l.idade_dias: l for l in conc.laudos.all()}


def pendencias_conclusao(conc):
    idades = set(conc.laudos.values_list("idade_dias", flat=True))
    faltas = []
    if 28 not in idades:
        faltas.append("laudo de 28 dias")
    if not idades.intersection(IDADES_INTERMEDIARIAS):
        faltas.append("laudo de 7 ou 14 dias")
    return faltas


@transaction.atomic
def lancar(conc, idade, resistencia, usuario, enviado_por_nome="", observacao="", arquivo=None):
    if not pode_lancar(conc):
        raise FluxoError("Os laudos são lançados com a concretagem aguardando laudos.")
    if idade not in LaudoConcretagem.Idade.values:
        raise FluxoError("Idade inválida.")
    if resistencia is None or resistencia <= 0:
        raise FluxoError("Informe a resistência obtida.")
    laudo = LaudoConcretagem.objects.filter(concretagem=conc, idade_dias=idade).first()
    novo = laudo is None
    if novo and not arquivo:
        raise FluxoError("Anexe o laudo do laboratório.")
    if novo:
        laudo = LaudoConcretagem(concretagem=conc, idade_dias=idade, lancado_por=usuario)
    laudo.resistencia_mpa = resistencia
    laudo.enviado_por_nome = (enviado_por_nome or conc.cps_enviados_por_nome or "")[:200]
    laudo.observacao = (observacao or "")[:300]
    laudo.save()
    if arquivo:
        laudo.anexos.filter(ativo=True).update(ativo=False)
        drive.criar_anexo(conc, "LAUDO", arquivo, usuario, laudo=laudo)
    situacao = "aprovado" if laudo.aprovado else "REPROVADO"
    registrar_historico(
        conc, usuario, A.OUTRO,
        f"Laudo de {idade} dias {'lançado' if novo else 'atualizado'}: {laudo.resistencia_mpa} MPa "
        f"({laudo.percentual_fck}% do fck; mínimo {laudo.limite_minimo_mpa} MPa) — {situacao}.",
    )
    if not laudo.aprovado:
        transaction.on_commit(lambda: alertar_reprovacao(laudo))
    return laudo


def alertar_reprovacao(laudo, request=None):
    """Notificação (engenheiro + gerentes) e e-mail ao engenheiro responsável."""
    conc = laudo.concretagem
    titulo = f"Laudo reprovado: {conc.codigo} ({laudo.idade_dias} dias)"
    texto = (
        f"{conc.obra.nome}: {laudo.resistencia_mpa} MPa aos {laudo.idade_dias} dias "
        f"= {laudo.percentual_fck}% do fck {conc.fck_projeto} MPa (mínimo {laudo.limite_minimo_mpa} MPa)."
    )
    notificacoes._notificar(
        [*notificacoes.responsaveis(conc), *notificacoes.gerentes()], conc, titulo, texto,
        f"concretagem.laudo_reprovado.{laudo.idade_dias}", tipo=TipoNotificacao.ATENCAO,
    )
    destino = (getattr(conc.engenheiro, "email", "") or "").strip()
    if not destino:
        logger.warning("Laudo reprovado em %s sem e-mail do engenheiro.", conc.codigo)
        return False
    link = url_absoluta(reverse("obras:concretagem_detalhe", args=[conc.pk]), request)
    try:
        email = EmailMultiAlternatives(
            subject=titulo, body=f"{texto}\n\nAbrir no ERP: {link}",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None), to=[destino],
        )
        email.attach_alternative(
            render_to_string("obras/concretagem/email/laudo_reprovado.html", {"conc": conc, "laudo": laudo, "link": link}),
            "text/html",
        )
        email.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Falha ao enviar e-mail de reprovação do laudo %s", laudo.pk)
        return False
