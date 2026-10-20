from django.core.management.base import BaseCommand
from pos_obra.services.notificacoes import enviar_pendentes
class Command(BaseCommand):
    help='Envia notificações pendentes de Pós-Obra; configurar cron no PythonAnywhere.'
    def add_arguments(self, parser):parser.add_argument('--limit',type=int,default=50)
    def handle(self,*args,**opts):
        enviados,erros=enviar_pendentes(opts['limit'])
        self.stdout.write(f'Enviados: {enviados}; falhas: {erros}')
