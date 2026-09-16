from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from financeiro.services.previsoes import gerar_previsoes_recorrentes, sincronizar_todas_integracoes


class Command(BaseCommand):
    help = "Sincroniza Contas a Pagar de Compras/Grandes Fornecedores e previsões recorrentes."

    def handle(self, *args, **options):
        resultado = sincronizar_todas_integracoes()
        hoje = timezone.localdate()
        recorrentes = gerar_previsoes_recorrentes(hoje, hoje + timedelta(days=180))
        self.stdout.write(self.style.SUCCESS(
            f"Sincronização concluída: {resultado['compras']} conta(s) de Compras, "
            f"{resultado['grandes_fornecedores']} conta(s) de Grandes Fornecedores e "
            f"{recorrentes} previsão(ões) recorrente(s) nova(s)."
        ))
