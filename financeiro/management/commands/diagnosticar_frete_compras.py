import csv
from collections import defaultdict
from decimal import Decimal
from itertools import batched

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db.models.functions import Coalesce

from compras.models import PedidoCompra
from compras.services.valores import calcular_total_proposta
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar


ZERO = Decimal("0.00")


def _titulos_por_pedido(pedidos):
    ids = [pedido.pk for pedido in pedidos]
    vinculados = TituloPagar.objects.filter(
        Q(pedido_id__in=ids)
        | Q(pedido__isnull=True, recebimento__pedido_id__in=ids)
        | Q(pedido__isnull=True, recebimento__isnull=True, previsao_origem__pedido_id__in=ids)
        | Q(
            pedido__isnull=True, recebimento__isnull=True, previsao_origem__pedido__isnull=True,
            previsao_origem__parcela_pedido__pedido_id__in=ids,
        )
    ).annotate(pedido_vinculado=Coalesce(
        "pedido_id", "recebimento__pedido_id", "previsao_origem__pedido_id",
        "previsao_origem__parcela_pedido__pedido_id",
    )).select_related("pagamento").order_by("pk")
    por_pedido = defaultdict(list)
    for titulo in vinculados:
        por_pedido[titulo.pedido_vinculado].append(titulo)
    return por_pedido


class Command(BaseCommand):
    help = "Emite CSV de conferência dos pedidos com frete registrado, usando somente leitura."

    def add_arguments(self, parser):
        parser.add_argument("--pedido", help="Número do pedido a conferir.")
        parser.add_argument("--somente-divergencias", action="store_true")

    def handle(self, *args, **options):
        pedidos = PedidoCompra.objects.filter(frete__gt=ZERO).select_related("fornecedor").order_by("pk")
        if options["pedido"]:
            pedidos = pedidos.filter(numero=options["pedido"])
        relatorio = csv.writer(self.stdout, delimiter=";")
        relatorio.writerow((
            "pedido", "fornecedor", "status_pedido", "valor_material_bruto", "descontos", "frete",
            "valor_contratado", "total_esperado", "total_financeiro", "diferenca_financeiro_contratado",
            "diferenca_financeiro_esperado", "total_pago", "titulos", "conferencia",
        ))
        for lote in batched(pedidos.iterator(chunk_size=500), 500):
            titulos_por_pedido = _titulos_por_pedido(lote)
            em_liberacao = set(LiberacaoFinanceiraPedido.objects.filter(
                pedido_id__in=[pedido.pk for pedido in lote],
                status__in=[LiberacaoFinanceiraPedido.Status.AUTORIZADA, LiberacaoFinanceiraPedido.Status.COMPENSADA],
            ).values_list("pedido_id", flat=True))
            for pedido in lote:
                titulos = titulos_por_pedido[pedido.pk]
                esperado = calcular_total_proposta(subtotal=pedido.subtotal, desconto=pedido.descontos, frete=pedido.frete)
                financeiro = sum((t.valor_original for t in titulos if t.status != TituloPagar.Status.CANCELADO), ZERO)
                pago = sum((
                    t.pagamento.valor for t in titulos
                    if getattr(t, "pagamento", None) and t.pagamento.status == Pagamento.Status.EFETIVADO
                ), ZERO)
                diferenca = financeiro - pedido.valor_total
                if options["somente_divergencias"] and not (diferenca or esperado != pedido.valor_total):
                    continue
                motivos = []
                if esperado != pedido.valor_total:
                    motivos.append("Componentes gravados divergem do valor contratado.")
                if not titulos:
                    motivos.append("Sem títulos com vínculo explícito.")
                if diferenca:
                    if pedido.status == PedidoCompra.Status.CANCELADO:
                        motivos.append("Pedido cancelado, conferir histórico e obrigações remanescentes.")
                    elif diferenca < ZERO and pedido.pk in em_liberacao:
                        motivos.append("Há liberação financeira registrada, conferir saldo ainda não titulado.")
                    elif diferenca == -pedido.frete:
                        motivos.append("Diferença coincide com o frete registrado, conferir a documentação.")
                    else:
                        motivos.append("Conferir parcelas, liberações e vínculos históricos.")
                relatorio.writerow((
                    pedido.numero, pedido.fornecedor.nome_exibicao, pedido.status, pedido.subtotal, pedido.descontos,
                    pedido.frete, pedido.valor_total, esperado, financeiro, diferenca, financeiro - esperado, pago,
                    " | ".join(f"{t.numero} ({t.status}, {t.valor_original:.2f})" for t in titulos),
                    " ".join(motivos) or "Valores conciliados.",
                ))
