from django.core.management.base import BaseCommand, CommandError

from planejamento.services.cronograma_suprimentos import (
    ImportacaoCronogramaSuprimentosError,
    importar_cronograma_suprimentos,
)


class Command(BaseCommand):
    help = "Importa a planilha mestre do Cronograma de Suprimentos do Google Drive."

    def add_arguments(self, parser):
        parser.add_argument(
            "--forcar",
            action="store_true",
            help="Reimporta mesmo quando o hash da planilha já estiver ativo.",
        )

    def handle(self, *args, **options):
        try:
            resultado = importar_cronograma_suprimentos(
                forcar=options["forcar"],
            )
        except ImportacaoCronogramaSuprimentosError as exc:
            raise CommandError(str(exc)) from exc

        estilo = self.style.SUCCESS if resultado.importado else self.style.WARNING
        self.stdout.write(estilo(resultado.mensagem))
