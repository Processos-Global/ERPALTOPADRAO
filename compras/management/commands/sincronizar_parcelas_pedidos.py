from django.core.management.base import BaseCommand

from compras.models import PedidoCompra
from compras.services.pedidos import sincronizar_parcelas_previstas_condicao


class Command(BaseCommand):
    help = "Cria/ajusta parcelas estruturadas dos pedidos normais a partir da condição de pagamento já salva em Compras."

    def handle(self, *args, **options):
        pedidos = PedidoCompra.objects.exclude(status=PedidoCompra.Status.CANCELADO).order_by("id")
        total = 0
        parcelados = 0
        protegidos = 0
        for pedido in pedidos.iterator():
            # Não reestrutura automaticamente obrigações antigas que já entraram
            # em aprovação ou pagamento. Isso evita duplicar histórico financeiro.
            if pedido.titulos_financeiros.filter(
                status__in=["AGUARDANDO_APROVACAO", "APROVADO", "PAGO"]
            ).exists():
                protegidos += 1
                continue
            parcelas = sincronizar_parcelas_previstas_condicao(pedido)
            # Dispara o signal já existente do Financeiro após as parcelas estarem prontas.
            pedido.save(update_fields=["atualizado_em"])
            total += 1
            if parcelas:
                parcelados += 1
        self.stdout.write(self.style.SUCCESS(
            f"Parcelamento sincronizado em {total} pedido(s); {parcelados} pedido(s) possuem múltiplas parcelas; "
            f"{protegidos} pedido(s) antigos foram preservados por já estarem em aprovação/pagamento."
        ))
