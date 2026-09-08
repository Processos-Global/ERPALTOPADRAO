from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from compras.models import PedidoCompra, RecebimentoPedido
from financeiro.services.previsoes import gerar_previsoes_recorrentes, sincronizar_previsoes_pedido
from financeiro.services.titulos import criar_ou_atualizar_titulo_recebimento


class Command(BaseCommand):
    help = "Sincroniza previsões de pedidos, recorrências e títulos originados de recebimentos/NF."

    def handle(self, *args, **options):
        previsoes = 0
        titulos = 0
        for pedido in PedidoCompra.objects.prefetch_related("parcelas_previstas").all():
            previsoes += sincronizar_previsoes_pedido(pedido).count()
        for recebimento in RecebimentoPedido.objects.select_related("pedido", "pedido__fornecedor", "pedido__obra").all():
            if criar_ou_atualizar_titulo_recebimento(recebimento):
                titulos += 1
        hoje = timezone.localdate()
        recorrentes = gerar_previsoes_recorrentes(hoje, hoje + timedelta(days=180))
        self.stdout.write(self.style.SUCCESS(
            f"Sincronização concluída: {previsoes} previsões de compras, {recorrentes} recorrências novas e {titulos} títulos de NF processados."
        ))
