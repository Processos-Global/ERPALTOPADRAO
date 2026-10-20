"""Notificações de Pós-Obra.

Envio automático após commit da ação que criou a notificação.
Sem worker externo, o envio é síncrono após a transação; falhas ficam para retentativa.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

from pos_obra.models import AgendamentoOS, NotificacaoOS

logger = logging.getLogger(__name__)
MAX_TENTATIVAS = 5


def _destinatario(chamado):
    return (getattr(chamado.cliente, 'email', '') or '').strip()


def _email_html(notificacao):
    portal = (getattr(settings, 'SITE_URL', '') or '').rstrip('/') + '/pos-obra/portal/'
    # URL é apenas navegação; portal deve exigir autenticação e autorização.
    texto = escape(notificacao.mensagem).replace('\n', '<br>')
    return (
        '<div style="font-family:Arial,sans-serif;max-width:640px;margin:auto;line-height:1.6">'
        '<h2 style="color:#6c513e">SAARI ERP · Pós-Obra</h2>'
        f'<p>{texto}</p><p><a href="{escape(portal, quote=True)}">Acessar meu portal</a></p>'
        '<hr><small>Mensagem automática. Consulte os detalhes no portal.</small></div>'
    )


def enviar_notificacao(pk):
    """Processa uma notificação com lock, evitando dois envios concorrentes.

    O lock dura durante o SMTP; use EMAIL_TIMEOUT nas configurações.
    Exceções de SMTP são registradas, sem desfazer a ação de negócio.
    """
    with transaction.atomic():
        obj = NotificacaoOS.objects.select_for_update().filter(pk=pk).first()
        if not obj or obj.situacao == 'ENVIADO' or obj.tentativas >= MAX_TENTATIVAS:
            return False, False
        obj.tentativas += 1
        obj.save(update_fields=['tentativas'])
        try:
            mensagem = EmailMultiAlternatives(
                subject=obj.assunto,
                body=obj.mensagem,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[obj.destinatario],
            )
            mensagem.attach_alternative(_email_html(obj), 'text/html')
            mensagem.send(fail_silently=False)
        except Exception as exc:
            logger.exception('Falha ao enviar notificação %s do Pós-Obra', pk)
            obj.situacao = 'ERRO'
            obj.ultimo_erro = str(exc)[:1500]
            obj.save(update_fields=['situacao', 'ultimo_erro'])
            return False, True
        obj.situacao = 'ENVIADO'
        obj.ultimo_erro = ''
        obj.enviado_em = timezone.now()
        obj.save(update_fields=['situacao', 'ultimo_erro', 'enviado_em'])
        return True, False


def _enviar_automaticamente(pk):
    if not getattr(settings, 'POS_OBRA_EMAIL_AUTOMATICO', True):
        return
    try:
        enviar_notificacao(pk)
    except Exception:
        # Erro não deve transformar uma abertura/finalização concluída em erro HTTP.
        # A linha permanece pendente/erro para próxima execução agendada.
        logger.exception('Erro inesperado no processamento automático da notificação %s', pk)


def enfileirar(chamado, evento, identificador, assunto, mensagem):
    endereco = _destinatario(chamado)
    if not endereco or '@' not in endereco:
        return None
    chave = f'os:{chamado.pk}:{evento}:{identificador}'[:160]
    obj, _ = NotificacaoOS.objects.get_or_create(
        chave=chave,
        defaults={
            'chamado': chamado, 'evento': evento, 'destinatario': endereco,
            'assunto': assunto, 'mensagem': mensagem,
        },
    )
    # Enviar depois do commit (nunca antes); não reenviar notificações já enviadas.
    if obj.situacao != 'ENVIADO' and obj.tentativas == 0:
        transaction.on_commit(lambda pk=obj.pk: _enviar_automaticamente(pk))
    return obj


def enviar_pendentes(limite=50):
    enviados = erros = 0
    ids = list(
        NotificacaoOS.objects.filter(
            situacao__in=['PENDENTE', 'ERRO'], tentativas__lt=MAX_TENTATIVAS,
        ).order_by('criado_em').values_list('pk', flat=True)[:limite]
    )
    for pk in ids:
        try:
            enviado, erro = enviar_notificacao(pk)
            enviados += int(enviado)
            erros += int(erro)
        except Exception:
            logger.exception('Erro inesperado ao reenviar notificação %s', pk)
            erros += 1
    return enviados, erros


def preparar_lembretes():
    """Enfileira lembrete único para atendimentos confirmados nas próximas 24 h."""
    agora = timezone.now()
    total = 0
    agenda = AgendamentoOS.objects.filter(
        situacao='CONFIRMADO', inicio__gt=agora,
        inicio__lte=agora + timedelta(hours=24),
    ).select_related('chamado__cliente').iterator()
    for agendamento in agenda:
        aviso = enfileirar(
            agendamento.chamado, 'LEMBRETE', agendamento.pk,
            f'SAARI | Lembrete {agendamento.chamado.numero}',
            f'Seu atendimento está confirmado para '
            f'{timezone.localtime(agendamento.inicio):%d/%m/%Y às %H:%M}. Consulte o portal.',
        )
        total += int(aviso is not None)
    return total
