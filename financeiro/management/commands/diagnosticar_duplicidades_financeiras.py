import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from financeiro.management.commands._csv import celula_csv
from financeiro.services.diagnostico_duplicidades import linhas_diagnostico_duplicidades


COLUNAS = (
    "codigo_fin", "id", "obra", "beneficiario", "valor", "valor_liquido", "status", "criado_em",
    "vencimento", "pagamento", "registros_relacionados", "classificacao", "motivo", "recomendacao",
    "origem", "usuario_id", "descricao", "documento_numero", "parcela", "aprovacoes", "anexos",
    "referencia_externa", "solicitacao_id", "pagamento_id",
)


class Command(BaseCommand):
    help = "Diagnostica possíveis duplicidades em solicitações avulsas e escreve CSV em modo somente leitura."

    def add_arguments(self, parser):
        parser.add_argument("--saida", type=Path, help="Caminho para um novo arquivo CSV. Sem a opção, escreve na saída padrão.")

    def handle(self, *args, **options):
        saida = options["saida"]
        if saida is None:
            self._escrever_csv(self.stdout)
            return
        try:
            with saida.open("x", encoding="utf-8-sig", newline="") as arquivo:
                self._escrever_csv(arquivo)
        except OSError as erro:
            raise CommandError(f"Não foi possível escrever o CSV em {saida}: {erro}") from erro

    @staticmethod
    def _escrever_csv(saida):
        csv_saida = csv.writer(saida)
        csv_saida.writerow(COLUNAS)
        csv_saida.writerows((celula_csv(celula) for celula in linha) for linha in linhas_diagnostico_duplicidades())
