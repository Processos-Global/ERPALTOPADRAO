from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections

from cadastros.migrations._documentos_fornecedor import contar_duplicados, resumo_duplicados, verificar_collation
from cadastros.models import Fornecedor


class Command(BaseCommand):
    help = "Identifica duplicidade de CPF/CNPJ de fornecedores por contagens, sem alterar dados."

    def add_arguments(self, parser):
        parser.add_argument("--database", default=DEFAULT_DB_ALIAS, choices=tuple(connections))

    def handle(self, *args, **options):
        using = options["database"]
        try:
            verificar_collation(Fornecedor, connections[using])
        except RuntimeError as erro:
            raise CommandError(str(erro)) from erro
        grupos, fornecedores = contar_duplicados(Fornecedor, using)
        resumo = resumo_duplicados(grupos, fornecedores)
        if grupos:
            raise CommandError(resumo)
        self.stdout.write(resumo)
