from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from pos_obra.models import AgendamentoOS
from pos_obra.services.notificacoes import enfileirar
class Command(BaseCommand):
    help='Cria lembretes para agendamentos confirmados nas próximas 24 horas.'
    def handle(self,*args,**kwargs):
        agora=timezone.now();total=0
        for a in AgendamentoOS.objects.filter(situacao='CONFIRMADO',inicio__gt=agora,inicio__lte=agora+timedelta(hours=24)).select_related('chamado__cliente').iterator():
            total+=bool(enfileirar(a.chamado,'LEMBRETE',a.pk,f'SAARI | Lembrete {a.chamado.numero}',f'Seu atendimento está confirmado para {timezone.localtime(a.inicio):%d/%m/%Y às %H:%M}. Consulte o portal.'))
        self.stdout.write(f'Lembretes processados: {total}')
