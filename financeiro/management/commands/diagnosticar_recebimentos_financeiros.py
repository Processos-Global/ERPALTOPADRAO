import csv

from django.core.management.base import BaseCommand
from django.db.models import Count, Exists, OuterRef, Prefetch, Q

from compras.models import RecebimentoPedido
from financeiro.management.commands._csv import celula_csv
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar


class Command(BaseCommand):
    help = "Emite CSV dos vínculos entre recebimentos, liberações, títulos e pagamentos em modo somente leitura."

    def add_arguments(self, parser):
        parser.add_argument("--pedido", help="Número de pedido a consultar.")
        parser.add_argument("--somente-pendencias", action="store_true")

    def handle(self, *args, **options):
        recebimentos = RecebimentoPedido.objects.select_related("pedido", "liberacao_financeira")
        if options["pedido"]:
            recebimentos = recebimentos.filter(pedido__numero=options["pedido"])
        outra_conta = TituloPagar.objects.filter(pedido_id=OuterRef("pedido_id"), recebimento__isnull=True).filter(
            Q(referencia_externa__startswith="COMPRA_PEDIDO:") | Q(referencia_externa__startswith="COMPRA_PARCELA:"),
        ).exclude(status=TituloPagar.Status.CANCELADO)
        notas_em_outros_pedidos = RecebimentoPedido.objects.filter(
            pedido__fornecedor_id=OuterRef("pedido__fornecedor_id"), numero_nota_fiscal=OuterRef("numero_nota_fiscal"),
        ).exclude(pk=OuterRef("pk")).exclude(Q(numero_nota_fiscal__isnull=True) | Q(numero_nota_fiscal=""))
        titulos = TituloPagar.objects.select_related("pagamento").order_by("pk")
        recebimentos = recebimentos.annotate(
            conta_sem_recebimento=Exists(outra_conta), nota_repetida=Exists(notas_em_outros_pedidos),
            quantidade_itens=Count("itens"),
        ).prefetch_related(Prefetch("titulos_financeiros", queryset=titulos, to_attr="contas_vinculadas")).order_by("pk")

        relatorio = csv.writer(self.stdout, delimiter=";")
        relatorio.writerow((
            "pedido", "recebimento_id", "nota_fiscal", "valor_documentado", "itens", "liberacao_id", "status_liberacao",
            "valor_esperado", "valor_compensado", "titulos", "pagamentos", "pendencias",
        ))
        for recebimento in recebimentos.iterator(chunk_size=500):
            liberacao = getattr(recebimento, "liberacao_financeira", None)
            contas = recebimento.contas_vinculadas
            pendencias = []
            if not liberacao and not contas:
                pendencias.append("Sem vínculo financeiro. Revisar duplicidade antes de qualquer regularização.")
            if recebimento.conta_sem_recebimento:
                pendencias.append("Há conta anterior vinculada ao pedido e sem recebimento.")
            if recebimento.nota_repetida:
                pendencias.append("Mesmo número de nota em mais de um recebimento do fornecedor. Conferir o documento.")
            if liberacao:
                if liberacao.status == LiberacaoFinanceiraPedido.Status.PENDENTE:
                    pendencias.append("Liberação anterior pendente.")
                if liberacao.divergencia:
                    pendencias.append(liberacao.divergencia)
                pendencias.extend(liberacao.divergencias_comerciais)
                if liberacao.titulo_id and liberacao.titulo_id not in {conta.pk for conta in contas}:
                    pendencias.append("Título principal da liberação sem vínculo direto com o recebimento.")
            if contas and not liberacao:
                pendencias.append("Título vinculado diretamente ao recebimento, sem liberação.")
            if options["somente_pendencias"] and not pendencias:
                continue
            pagamentos = [
                f"{conta.numero} ({conta.pagamento.status}, {conta.pagamento.valor})" for conta in contas
                if isinstance(getattr(conta, "pagamento", None), Pagamento)
            ]
            valores = (
                recebimento.pedido.numero, recebimento.pk, recebimento.numero_nota_fiscal, recebimento.valor_total_nota,
                recebimento.quantidade_itens, liberacao.pk if liberacao else None, liberacao.status if liberacao else "",
                liberacao.valor_esperado if liberacao else None, liberacao.valor_compensado if liberacao else None,
                " | ".join(f"{conta.numero} ({conta.status}, {conta.valor_original})" for conta in contas),
                " | ".join(pagamentos), " ".join(pendencias),
            )
            relatorio.writerow(celula_csv(valor) for valor in valores)
