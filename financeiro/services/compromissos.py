"""Leitura gerencial de compromissos, sem criar ou alterar obrigações."""

from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest

from compras.models import ContratoCompra, PedidoCompra, RecebimentoPedido, RecebimentoPedidoItem
from financeiro.models import LiberacaoFinanceiraPedido, Pagamento, TituloPagar


MOEDA = DecimalField(max_digits=18, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MOEDA)


def pedidos_comprometidos(*, obra_id=None, fornecedor_id=None, busca="", status=""):
    """Cada linha é um pedido; filhos são agregados em subconsultas independentes."""
    recebimentos = (
        RecebimentoPedidoItem.objects
        .filter(recebimento__pedido_id=OuterRef("pk"))
        .order_by()
        .values("recebimento__pedido_id")
        .annotate(valor=Sum("valor_recebido"), sem_valor=Count("pk", filter=Q(valor_recebido__isnull=True)))
    )
    notas = (
        RecebimentoPedido.objects.filter(pedido_id=OuterRef("pk"), valor_total_nota__isnull=False)
        .exclude(Q(numero_nota_fiscal__isnull=True) | Q(numero_nota_fiscal="") | Q(arquivo_nota_fiscal=""))
        .order_by().values("pedido_id")
        .annotate(
            valor=Sum("valor_total_nota"),
            frete=Sum("valor_frete_nota", filter=Q(liberacao_financeira__status__in=[
                LiberacaoFinanceiraPedido.Status.PENDENTE,
                LiberacaoFinanceiraPedido.Status.AUTORIZADA,
                LiberacaoFinanceiraPedido.Status.COMPENSADA,
            ])),
        )
    )
    pagamentos = (
        Pagamento.objects
        .filter(titulo__pedido_id=OuterRef("pk"), status=Pagamento.Status.EFETIVADO)
        .order_by()
        .values("titulo__pedido_id")
        .annotate(valor=Sum("valor"))
    )
    liberacoes = (
        LiberacaoFinanceiraPedido.objects
        .filter(pedido_id=OuterRef("pk"), status=LiberacaoFinanceiraPedido.Status.AUTORIZADA)
        .order_by().values("pedido_id").annotate(valor=Sum("valor"))
    )
    titulos_ativos = (
        TituloPagar.objects
        .filter(pedido_id=OuterRef("pk"))
        .exclude(status=TituloPagar.Status.CANCELADO)
        .order_by().values("pedido_id")
        .annotate(valor=Sum(Greatest(
            F("valor_original") + F("juros") + F("multa")
            + F("outros_acrescimos") - F("desconto"), ZERO,
        )))
    )
    # O cancelamento integral em Compras preserva pedido, recebimentos e títulos.
    # Excluí-lo ocultaria pagamentos já efetivados e o saldo não entregue.
    qs = PedidoCompra.objects.all()
    if obra_id:
        qs = qs.filter(obra_id=obra_id)
    if fornecedor_id:
        qs = qs.filter(fornecedor_id=fornecedor_id)
    if status in PedidoCompra.Status.values:
        qs = qs.filter(status=status)
    if busca:
        qs = qs.filter(Q(numero__icontains=busca) | Q(processo__numero__icontains=busca))
    return (
        qs.select_related("obra", "fornecedor", "processo")
        .annotate(
            recebido_identificado=Coalesce(Subquery(recebimentos.values("valor")[:1], output_field=MOEDA), ZERO),
            valor_documentado=Coalesce(Subquery(notas.values("valor")[:1], output_field=MOEDA), ZERO),
            frete_documentado=Coalesce(Subquery(notas.values("frete")[:1], output_field=MOEDA), ZERO),
            itens_recebidos_sem_valor=Coalesce(Subquery(recebimentos.values("sem_valor")[:1]), Value(0)),
            pago_efetivado=Coalesce(Subquery(pagamentos.values("valor")[:1], output_field=MOEDA), ZERO),
            liberado_financeiramente=Coalesce(Subquery(liberacoes.values("valor")[:1], output_field=MOEDA), ZERO),
            obrigacao_em_titulos=Coalesce(Subquery(titulos_ativos.values("valor")[:1], output_field=MOEDA), ZERO),
        )
        .alias(recebido_com_frete=F("recebido_identificado") + F("frete_documentado"))
        .annotate(
            saldo_cancelado=Case(
                When(
                    ~Q(motivo_cancelamento=""),
                    status=PedidoCompra.Status.CANCELADO,
                    cancelado_em__isnull=False,
                    itens_recebidos_sem_valor=0,
                    obrigacao_em_titulos__lte=F("recebido_com_frete"),
                    then=Greatest(F("valor_total") - F("frete") - F("recebido_identificado"), ZERO),
                ),
                default=ZERO,
                output_field=MOEDA,
            ),
        )
        .annotate(
            valor_vigente=Greatest(F("valor_total") - F("saldo_cancelado"), ZERO),
            saldo_receber=Case(
                When(status__in=[PedidoCompra.Status.CANCELADO, PedidoCompra.Status.ENTREGUE], then=ZERO),
                default=Greatest(F("valor_total") - F("frete") - F("recebido_identificado"), ZERO),
                output_field=MOEDA,
            ),
            saldo_cancelamento_pendente=Case(
                When(status=PedidoCompra.Status.CANCELADO,
                     then=Greatest(F("valor_total") - F("recebido_com_frete") - F("saldo_cancelado"), ZERO)),
                default=ZERO, output_field=MOEDA,
            ),
            excedente_pago=Greatest(F("pago_efetivado") - F("valor_total"), ZERO),
            pago_sem_recebimento=Case(
                When(status=PedidoCompra.Status.CANCELADO,
                     then=Greatest(F("pago_efetivado") - F("recebido_com_frete"), ZERO)),
                default=ZERO, output_field=MOEDA,
            ),
            liberado_sem_recebimento=Case(
                When(status=PedidoCompra.Status.CANCELADO,
                     then=Greatest(F("liberado_financeiramente") - F("recebido_com_frete"), ZERO)),
                default=ZERO, output_field=MOEDA,
            ),
        )
        .annotate(
            saldo_financeiro=Greatest(F("valor_vigente") - F("pago_efetivado"), ZERO),
            saldo_liberar=Greatest(F("valor_vigente") - Greatest(F("liberado_financeiramente"), F("pago_efetivado")), ZERO),
        )
        .order_by("-criado_em", "-pk")
    )


def totais_pedidos(qs):
    # SQLite não agrega corretamente algumas anotações correlacionadas deste
    # queryset. Projetar apenas números e somar em fluxo evita linhas duplicadas
    # por joins e mantém os mesmos valores da tabela em todos os bancos.
    monetarios = (
        "valor_total", "frete", "descontos", "valor_vigente", "recebido_identificado", "pago_efetivado",
        "valor_documentado", "frete_documentado", "saldo_receber", "saldo_liberar",
        "saldo_financeiro", "saldo_cancelado", "excedente_pago",
        "saldo_cancelamento_pendente",
        "pago_sem_recebimento", "liberado_sem_recebimento",
        "liberado_financeiramente",
    )
    totais = {campo if campo != "valor_total" else "contratado": Decimal("0") for campo in monetarios}
    totais["itens_recebidos_sem_valor"] = 0
    for linha in qs.order_by().values_list(*monetarios, "itens_recebidos_sem_valor").iterator(chunk_size=1000):
        for campo, valor in zip(monetarios, linha[:-1]):
            totais["contratado" if campo == "valor_total" else campo] += valor or Decimal("0")
        totais["itens_recebidos_sem_valor"] += linha[-1] or 0
    return totais


def contratos_assinados_separados(*, obra_id=None, fornecedor_id=None, busca=""):
    """Contratos assinados ficam fora dos totais de pedidos, mesmo com processo comum."""
    qs = ContratoCompra.objects.filter(status=ContratoCompra.Status.ASSINADO).select_related(
        "obra", "fornecedor", "processo"
    )
    if obra_id:
        qs = qs.filter(obra_id=obra_id)
    if fornecedor_id:
        qs = qs.filter(fornecedor_id=fornecedor_id)
    if busca:
        qs = qs.filter(Q(numero__icontains=busca) | Q(processo__numero__icontains=busca))
    return qs.order_by("-assinado_em", "-pk")
