"""Rotina única para tarefa agendada: lembretes e retentativas."""
from django.core.management.base import BaseCommand
from pos_obra.services.notificacoes import enviar_pendentes, preparar_lembretes


class Command(BaseCommand):
    help = 'Enfileira lembretes e reprocessa falhas/pedidos pendentes do Pós-Obra.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        criados = preparar_lembretes()
        enviados, erros = enviar_pendentes(max(1, options['limit']))
        self.stdout.write(
            f'Lembretes verificados: {criados}; enviados: {enviados}; falhas: {erros}'
        )
