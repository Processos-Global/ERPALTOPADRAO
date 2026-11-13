from django.core.management.base import BaseCommand

from financeiro.services.previsoes import sincronizar_todas_integracoes


class Command(BaseCommand):
    help = "Cria/atualiza Contas a Pagar a partir de Compras e Grandes Fornecedores."

    def handle(self, *args, **options):
        resultado = sincronizar_todas_integracoes()
        self.stdout.write(self.style.SUCCESS(
            f"Financeiro v2 sincronizado: {resultado['compras']} conta(s) de Compras e "
            f"{resultado['grandes_fornecedores']} conta(s) de Grandes Fornecedores."
        ))
