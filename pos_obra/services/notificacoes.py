"""Notificações de Pós-Obra.

Envio automático após commit da ação que criou a notificação.
Sem worker externo, o envio é síncrono após a transação; falhas ficam para retentativa.
"""
import logging
from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import escape

from pos_obra.models import AgendamentoOS, NotificacaoOS

logger = logging.getLogger(__name__)
MAX_TENTATIVAS = 5


EVENTOS_EMAIL = {
    'ABERTURA': {
        'eyebrow': 'Solicitação recebida',
        'titulo': 'Recebemos seu chamado',
        'descricao': 'Sua solicitação foi registrada com sucesso e já está em acompanhamento pela equipe de Pós-Obra.',
        'tag': 'Abertura',
    },
    'AGENDAMENTO': {
        'eyebrow': 'Novo agendamento',
        'titulo': 'Há um atendimento aguardando sua confirmação',
        'descricao': 'Confira os detalhes do agendamento e confirme o atendimento pelo portal do cliente.',
        'tag': 'Agendamento',
    },
    'REAGENDAMENTO': {
        'eyebrow': 'Atualização de agenda',
        'titulo': 'Há uma nova proposta de atendimento',
        'descricao': 'O horário do atendimento foi atualizado. Confira os detalhes no portal.',
        'tag': 'Reagendamento',
    },
    'RESPOSTA_AGENDAMENTO': {
        'eyebrow': 'Resposta registrada',
        'titulo': 'Sua resposta ao agendamento foi registrada',
        'descricao': 'Recebemos sua confirmação ou solicitação de ajuste de horário com sucesso.',
        'tag': 'Agenda',
    },
    'ALTERACAO_AGENDAMENTO': {
        'eyebrow': 'Agenda atualizada',
        'titulo': 'O agendamento do seu atendimento foi atualizado',
        'descricao': 'Houve uma atualização no status do agendamento. Consulte o portal para ver os detalhes.',
        'tag': 'Agenda',
    },
    'CONCLUSAO': {
        'eyebrow': 'Atendimento concluído',
        'titulo': 'Sua ordem de serviço foi concluída',
        'descricao': 'Os documentos e o histórico do atendimento já estão disponíveis no portal do cliente.',
        'tag': 'Conclusão',
    },
    'PESQUISA': {
        'eyebrow': 'Sua opinião é importante',
        'titulo': 'Avalie o atendimento realizado',
        'descricao': 'Sua avaliação ajuda a melhorar continuamente a experiência do Pós-Obra SAARI.',
        'tag': 'Pesquisa',
    },
    'LEMBRETE': {
        'eyebrow': 'Lembrete de atendimento',
        'titulo': 'Seu atendimento está próximo',
        'descricao': 'Este é um lembrete do atendimento confirmado. Consulte os detalhes e orientações no portal.',
        'tag': 'Lembrete',
    },
}


def _destinatario(chamado):
    return (getattr(chamado.cliente, 'email', '') or '').strip()


def _site_url():
    return (getattr(settings, 'SITE_URL', '') or '').rstrip('/')


def _portal_url():
    site_url = _site_url()
    return f'{site_url}/pos-obra/portal/' if site_url else '#'


def _logo_url():
    site_url = _site_url()
    logo_path = 'static/img/saari/saari-simbolo-gold.png'
    return urljoin(f'{site_url}/', logo_path) if site_url else ''


def _dados_evento(notificacao):
    base = {
        'eyebrow': 'Atualização do Pós-Obra',
        'titulo': 'Sua ordem de serviço recebeu uma atualização',
        'descricao': 'Acompanhe as informações mais recentes do seu atendimento no portal do cliente.',
        'tag': 'Pós-Obra',
    }
    base.update(EVENTOS_EMAIL.get(notificacao.evento, {}))
    return base


def _resumo_os(notificacao):
    chamado = notificacao.chamado
    cliente = getattr(chamado, 'cliente', None)
    empreendimento = getattr(chamado, 'empreendimento', None)
    return [
        ('Protocolo', chamado.numero),
        ('Status atual', chamado.get_status_display() if hasattr(chamado, 'get_status_display') else chamado.status),
        ('Cliente', getattr(cliente, 'nome', '') or getattr(cliente, 'razao_social', '') or '-'),
        ('Empreendimento', getattr(empreendimento, 'nome', '') or str(empreendimento or '-')),
    ]


def _email_context(notificacao):
    portal = _portal_url()
    dados_evento = _dados_evento(notificacao)
    mensagem_formatada = escape(notificacao.mensagem).replace('\n', '<br>')
    return {
        'notificacao': notificacao,
        'chamado': notificacao.chamado,
        'portal_url': portal,
        'logo_url': _logo_url(),
        'mensagem_html': mensagem_formatada,
        'resumo_os': _resumo_os(notificacao),
        'cta_label': 'Acessar Portal do Cliente',
        **dados_evento,
    }


def _email_html(notificacao):
    return render_to_string('pos_obra/emails/notificacao.html', _email_context(notificacao))


def enviar_notificacao(pk):
    """Processa uma notificação com lock, evitando dois envios concorrentes.

    O lock dura durante o SMTP; use EMAIL_TIMEOUT nas configurações.
    Exceções de SMTP são registradas, sem desfazer a ação de negócio.
    """
    with transaction.atomic():
        obj = NotificacaoOS.objects.select_for_update().select_related(
            'chamado__cliente', 'chamado__empreendimento'
        ).filter(pk=pk).first()
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
